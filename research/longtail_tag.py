# -*- coding: utf-8 -*-
"""longtail_tag.py — 标注用户长尾贴纸补标（少样本用户单独处理）

对"覆盖不足"的已标注用户（标签贴纸<5 或覆盖率<30%），枚举其全部去重贴纸，
下载缺失 → gpt-5.5 视觉描述 → 文本打标（沿用 v2 体系），追加到 outputs/贴纸标签v2.csv
用法: $env:RELAY_KEY='sk-...'; python research/longtail_tag.py [--limit N]
"""
import base64
import csv
import io
import json
import os
import sqlite3
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
VISION_MODEL = 'gpt-5.5'
TAG_CSV = 'outputs/贴纸标签v2.csv'
LT_DIR = 'data/sticker_longtail'

DESC_PROMPT = """这是一个QQ表情包/贴纸图片。请仔细观察后用中文输出 JSON（不要其他文字）：
{
 "content": "画面内容：角色类型/数量/装扮/动作，具体一些",
 "style": "画风：Q版/正常比例/抽象扭曲/像素/真人/动物拟人等，以及线条色彩特点",
 "emotion": "面部表情与情绪，尽可能细分（如：害羞/发呆装傻/坏笑/疲惫/无语/得意/生气/哭/撒娇等）",
 "atmosphere": "氛围与场合",
 "erotic": "是否带有涩情/色气/性暗示成分：回答 是/否，是的话说明程度（轻微/明显/露骨）",
 "text": "图中是否有文字，有则写出内容（没有写无）",
 "overall": "用一句话概括"
}"""

TAXO_PROMPT = """根据贴纸描述，为这张QQ表情包贴纸打标签，输出JSON：
{"emotion":"...","style":"...","ero":0,"meme":"有/无","moe":"是/否"}
emotion 只能选一个：撒娇卖萌/发呆装傻/疲惫困倦/无语无奈/委屈哭/生气嫌弃/得意坏笑/开心兴奋/搞怪沙雕/中性
style 只能选一个：Q版/正常比例/抽象/真人/其他
ero 是涩情等级整数：0无/1轻微/2明显/3露骨
meme 指是否有文字梗：有/无
moe 画风是否萌系：是/否
只输出JSON。"""


def load_jpeg_b64(fn):
    from PIL import Image
    im = Image.open(fn)
    im.seek(0)
    im = im.convert('RGB')
    im.thumbnail((640, 640))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def call(messages, max_tokens, retries=3):
    body = {'model': VISION_MODEL, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0}
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
    if not KEY:
        print('请设置 RELAY_KEY'); return
    limit = None
    per_user = 30
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    if '--per-user' in sys.argv:
        per_user = int(sys.argv[sys.argv.index('--per-user') + 1])

    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    labels = {}
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
        labels[r['user_id']] = r['gender']

    # 已有标签（url -> tags）
    known = {}
    with open(TAG_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('emotion'):
                known[r['url']] = r

    # 每用户贴纸使用（去重 url）+ 总量
    user_stickers = defaultdict(Counter)
    for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
        uid = r['user_id']
        if uid not in labels:
            continue
        try:
            j = json.loads(r['raw_json'])
        except Exception:
            continue
        for s in (j.get('message') or []):
            if isinstance(s, dict) and s.get('type') == 'image':
                url = (s.get('data') or {}).get('url') or ''
                if url:
                    user_stickers[uid][url] += 1

    # 已下载映射
    downloaded = {}
    for m in conn.execute("SELECT url, local_path FROM media_files WHERE status='downloaded' AND local_path IS NOT NULL"):
        if m['url']:
            downloaded.setdefault(m['url'], m['local_path'])
    conn.close()

    # 需要补标的用户：已知标签覆盖 <30% 或 标签贴纸<5
    todo_users = []
    for uid, cnt in user_stickers.items():
        total_uses = sum(cnt.values())
        known_uses = sum(v for u, v in cnt.items() if u in known)
        n_known = sum(1 for u in cnt if u in known)
        if total_uses == 0:
            continue
        if n_known < 5 or known_uses / total_uses < 0.3:
            todo_users.append(uid)
    print(f'需要补标的用户: {len(todo_users)} 个')
    for uid in sorted(todo_users):
        print(f'  {uid} {labels[uid]}: 去重贴纸={len(user_stickers[uid])} 已知标签={sum(1 for u in user_stickers[uid] if u in known)}')

    # 收集待补贴纸：每用户 Top-N 高频未标签贴纸（女性优先）
    need = Counter()
    for uid in sorted(todo_users, key=lambda u: (labels[u] != 'female', len(user_stickers[u]))):
        top = user_stickers[uid].most_common(per_user)
        for url, c in top:
            if url not in known:
                need[url] += c
    if limit:
        need = Counter(dict(need.most_common(limit)))
    print(f'\n待补贴纸: {len(need)} 个（覆盖 {sum(need.values())} 次使用）')

    os.makedirs(LT_DIR, exist_ok=True)

    def prep(url, idx):
        """返回本地文件路径或 None"""
        if url in downloaded and os.path.exists(downloaded[url]):
            return downloaded[url]
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            ext = os.path.splitext(url.split('?')[0])[1] or '.gif'
            fn = os.path.join(LT_DIR, f'lt_{idx:04d}{ext}')
            with open(fn, 'wb') as fh:
                fh.write(data)
            return fn
        except Exception:
            return None

    # 1) 下载
    print('\n[1/3] 下载缺失贴纸...')
    url2fn = {}
    idx = 0
    for url in need:
        idx += 1
        fn = prep(url, idx)
        if fn:
            url2fn[url] = fn
    print(f'  可用 {len(url2fn)}/{len(need)}')

    # 2) 描述
    print('[2/3] 视觉描述...')
    descs = {}
    done = 0

    def desc_work(url):
        fn = url2fn[url]
        try:
            b64 = load_jpeg_b64(fn)
        except Exception:
            return url, {'error': 'img'}
        d = call([
            {'role': 'user', 'content': [
                {'type': 'text', 'text': DESC_PROMPT},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
            ]}], 700)
        return url, d

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(desc_work, u): u for u in url2fn}
        for fut in as_completed(futs):
            url, d = fut.result()
            descs[url] = d
            done += 1
            if done % 50 == 0 or done == len(url2fn):
                print(f'  描述进度 {done}/{len(url2fn)}')

    # 3) 打标
    print('[3/3] 文本打标...')
    tag_rows = []
    done = 0

    def tag_work(url):
        d = descs.get(url) or {}
        if 'error' in d or not d.get('content'):
            return url, None
        t = call([{'role': 'user', 'content': TAXO_PROMPT + '\n\n贴纸描述：' + json.dumps(d, ensure_ascii=False)}], 120)
        return url, t

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(tag_work, u): u for u in descs}
        for fut in as_completed(futs):
            url, t = fut.result()
            if t and t.get('emotion'):
                tag_rows.append((url, t))
            done += 1
            if done % 50 == 0 or done == len(descs):
                print(f'  打标进度 {done}/{len(descs)}')

    # 追加到标签表
    with open(TAG_CSV, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        for url, t in tag_rows:
            w.writerow(['LT', url, need[url], '', t['emotion'], t['style'], t['ero'], t['meme'], t['moe'], ''])
    print(f'\n[完成] 追加 {len(tag_rows)} 条长尾标签 → {TAG_CSV}')


if __name__ == '__main__':
    main()
