# -*- coding: utf-8 -*-
"""avatar_profile.py — 任务④：45个已标注用户的头像+主页信息

1. get_stranger_info 全量响应（兴趣标签/年龄/星座/地区等）→ profile_details 表
2. qlogo 头像下载 → data/avatars/<uin>.<ext>
3. gpt-5.5 视觉描述头像 → research/avatar_desc.jsonl（保留API接口，缓存本地）
用法: $env:RELAY_KEY='sk-...'; python research/avatar_profile.py
"""
import base64
import io
import json
import os
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
OUT = 'research/avatar_desc.jsonl'
AV_DIR = 'data/avatars'

DESC_PROMPT = """这是一个QQ用户的头像图片。请用中文输出JSON（不要其他文字）：
{
 "content": "画面内容：人物/动物/景物/动漫角色等，具体描述（性别外观/年龄感/装扮/表情）",
 "style": "画风：真人照片/动漫二次元/Q版/抽象/动物/风景/文字等，以及色调特点",
 "vibe": "整体氛围气质（如：可爱/酷/忧郁/沙雕/冷淡/软萌/御姐/中性等）",
 "overall": "一句话概括这个头像"
}"""


def call_api(messages, max_tokens, retries=3):
    body = {'model': MODEL, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'error': content[:120]}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(2 * (attempt + 1))


def main():
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    # 45 个已标注用户
    uids = [r['user_id'] for r in conn.execute(
        "SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')")]
    # profile_details 表
    conn.execute("""CREATE TABLE IF NOT EXISTS profile_details (
        user_id INTEGER PRIMARY KEY, data_json TEXT, fetched_at INTEGER)""")
    conn.close()

    # 1) 拉取主页信息
    print(f'[1/3] 拉取主页信息（{len(uids)} 人）...')
    conn = sqlite3.connect('data/qqchat.db')
    upsert_sql = """
        INSERT INTO profile_details (user_id, data_json, fetched_at) VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET data_json=excluded.data_json, fetched_at=excluded.fetched_at"""
    have = set(r[0] for r in conn.execute('SELECT user_id FROM profile_details'))
    todo_p = [u for u in uids if u not in have]
    for u in todo_p:
        try:
            req = urllib.request.Request('http://127.0.0.1:3000/get_stranger_info',
                                         data=json.dumps({'user_id': u}).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                j = json.loads(resp.read().decode())
            if j.get('status') == 'ok' and j.get('data'):
                conn.execute(upsert_sql, (u, json.dumps(j['data'], ensure_ascii=False), int(time.time())))
            else:
                print(f'  {u}: 无数据 {str(j)[:80]}')
        except Exception as e:
            print(f'  {u}: 失败 {e}')
        time.sleep(0.25)
    conn.commit()
    conn.close()
    print(f'  主页信息完成（{len(uids) - len(todo_p)} 已有 + {len(todo_p)} 新拉）')

    # 2) 头像下载（qlogo 公共 CDN）
    print('[2/3] 下载头像...')
    os.makedirs(AV_DIR, exist_ok=True)
    av_paths = {}
    for u in uids:
        for url in (f'https://q1.qlogo.cn/g?b=qq&nk={u}&s=640',
                    f'https://q2.qlogo.cn/headimg_dl?dst_uin={u}&spec=640'):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                if len(data) > 200:
                    ext = 'png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'jpg'
                    fn = os.path.join(AV_DIR, f'{u}.{ext}')
                    with open(fn, 'wb') as f:
                        f.write(data)
                    av_paths[u] = fn
                    break
            except Exception:
                continue
        time.sleep(0.1)
    print(f'  头像可用: {len(av_paths)}/{len(uids)}')

    # 3) 头像描述
    print('[3/3] gpt-5.5 视觉描述头像...')
    done = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            l = l.strip()
            if l:
                d = json.loads(l)
                done[d['uin']] = d
    todo = [(u, fn) for u, fn in av_paths.items() if u not in done]
    print(f'  待描述: {len(todo)}（已完成 {len(done)}）')

    def work(item):
        u, fn = item
        from PIL import Image
        try:
            im = Image.open(fn).convert('RGB')
            im.thumbnail((256, 256))
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            return u, {'error': str(e)}
        d = call_api([
            {'role': 'user', 'content': [
                {'type': 'text', 'text': DESC_PROMPT},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
            ]}], 500)
        return u, d

    n = 0
    with open(OUT, 'a', encoding='utf-8') as f:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(work, it): it for it in todo}
            for fut in as_completed(futs):
                u, d = fut.result()
                f.write(json.dumps({'uin': u, 'desc': d}, ensure_ascii=False) + '\n')
                f.flush()
                n += 1
                if n % 10 == 0 or n == len(todo):
                    print(f'  进度 {n}/{len(todo)}')
    print(f'[完成] 头像描述 → {OUT}（累计 {len(done) + n}）')


if __name__ == '__main__':
    main()
