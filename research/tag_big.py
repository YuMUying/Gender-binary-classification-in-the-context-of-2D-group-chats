# -*- coding: utf-8 -*-
"""tag_big.py — 收割图打标（按使用频次优先，可断点续跑）

读 research/harvest_map_big.jsonl，按 url 使用次数降序，
gpt-5.5 视觉描述 → v2 标签 → 追加 outputs/贴纸标签v2.csv
用法: $env:RELAY_KEY='sk-...'; python research/tag_big.py [--limit N]
"""
import base64
import csv
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
MAP = 'research/harvest_map_big.jsonl'
TAG_CSV = 'outputs/贴纸标签v2.csv'

DESC_PROMPT = """这是一个QQ聊天中的图片/表情包。请仔细观察后用中文输出 JSON（不要其他文字）：
{
 "content": "画面内容：角色类型/数量/装扮/动作/场景",
 "style": "画风：Q版/正常比例/抽象扭曲/像素/真人照片/动物拟人/文字图等",
 "emotion": "主要情绪（害羞/发呆装傻/坏笑/疲惫/无语/得意/生气/哭/撒娇/搞笑等，细分）",
 "atmosphere": "氛围（软萌/沙雕/嘲讽/温馨/色气/日常等）",
 "erotic": "是否涩情/色气/性暗示：是/否，是则说明程度（轻微/明显/露骨）",
 "text": "图中文字内容（无则写无）",
 "overall": "一句话概括"
}"""

TAXO_PROMPT = """根据描述，为这张图片打标签，输出JSON：
{"emotion":"...","style":"...","ero":0,"meme":"有/无","moe":"是/否"}
emotion 只能选一个：撒娇卖萌/发呆装傻/疲惫困倦/无语无奈/委屈哭/生气嫌弃/得意坏笑/开心兴奋/搞怪沙雕/中性
style 只能选一个：Q版/正常比例/抽象/真人/其他
ero 是涩情等级整数：0无/1轻微/2明显/3露骨
meme 指是否有文字梗：有/无
moe 画风是否萌系：是/否
只输出JSON。"""


def call(messages, max_tokens, retries=4):
    body = {'model': MODEL, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'error': content[:120]}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(3 * (attempt + 1))


def load_jpeg_b64(fn):
    from PIL import Image
    im = Image.open(fn)
    im.seek(0)
    im = im.convert('RGB')
    im.thumbnail((640, 640))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    entries = [json.loads(l) for l in open(MAP, encoding='utf-8') if l.strip()]
    done_urls = set()
    with open(TAG_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('url'):
                done_urls.add(r['url'])
    todo = [e for e in entries if e['url'] not in done_urls]
    # 按使用频次排序（从 messages 统计 url 使用次数）
    import sqlite3
    from collections import Counter
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    cnt = Counter()
    # --user 定向模式：只统计/标注指定用户的贴纸（少样本高密度用户按需标注）
    target_user = None
    if '--user' in sys.argv:
        target_user = int(sys.argv[sys.argv.index('--user') + 1])
        print(f'[定向模式] 用户 {target_user}')
    for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json LIKE '%image%'"):
        if target_user is not None and r['user_id'] != target_user:
            continue
        try:
            j = json.loads(r['raw_json'])
        except Exception:
            continue
        for s in (j.get('message') or []):
            if isinstance(s, dict) and s.get('type') == 'image':
                u = (s.get('data') or {}).get('url') or ''
                if u:
                    cnt[u] += 1
    conn.close()
    todo.sort(key=lambda e: -cnt.get(e['url'], 0))
    if target_user is not None:
        todo = [e for e in todo if cnt.get(e['url'], 0) > 0]
        print(f'[定向模式] 该用户未标注贴纸: {len(todo)} 个（按使用频次）')
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
        todo = todo[:limit]
    print(f'待打标: {len(todo)}（已完成 {len(entries) - len(todo)}）')

    def work(e):
        try:
            b64 = load_jpeg_b64(e['local'])
        except Exception:
            return e, None
        d = call([{'role': 'user', 'content': [
            {'type': 'text', 'text': DESC_PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
        ]}], 700)
        if 'error' in d:
            return e, None
        t = call([{'role': 'user', 'content': TAXO_PROMPT + '\n\n描述：' + json.dumps(d, ensure_ascii=False)}], 120)
        return e, t

    results = []
    done = 0
    ok = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(work, e): e for e in todo}
        for fut in as_completed(futs):
            e, t = fut.result()
            if t and t.get('emotion'):
                results.append((e, t))
                ok += 1
            done += 1
            if done % 100 == 0 or done == len(todo):
                print(f'进度 {done}/{len(todo)} (成功 {ok})')
            if len(results) >= 100:
                with open(TAG_CSV, 'a', encoding='utf-8', newline='') as f:
                    w = csv.writer(f)
                    for e, t in results:
                        w.writerow(['HB' + e['md5'][:8], e['url'], cnt.get(e['url'], 0), e.get('summary') or '',
                                    t['emotion'], t['style'], t['ero'], t['meme'], t['moe'], ''])
                results = []
    with open(TAG_CSV, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        for e, t in results:
            w.writerow(['HB' + e['md5'][:8], e['url'], cnt.get(e['url'], 0), e.get('summary') or '',
                        t['emotion'], t['style'], t['ero'], t['meme'], t['moe'], ''])
    print(f'[完成] 本次成功 {ok}/{len(todo)} → {TAG_CSV}')


if __name__ == '__main__':
    main()
