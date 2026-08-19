# -*- coding: utf-8 -*-
"""desc_stickers.py — 用 gpt-5.5 对贴纸做自由式详细描述（JSON 结构化）

输出 research/sticker_desc.jsonl：每行 {rank, url, count, summary, desc{...}}
描述字段：content(画面内容) style(画风) emotion(表情情绪,细分) atmosphere(氛围)
         erotic(是否涩情/色气及程度) text(图中文字) overall(整体一句话)
用法: $env:RELAY_KEY='sk-...'; python research/desc_stickers.py [--limit N]
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
CSV_PATH = 'outputs/贴纸待标清单.csv'
IMG_DIR = 'data/sticker_tags'
OUT = 'research/sticker_desc.jsonl'

PROMPT = """这是一个QQ表情包/贴纸图片。请仔细观察后用中文输出 JSON（不要其他文字）：
{
 "content": "画面内容：角色类型/数量/装扮/动作，具体一些",
 "style": "画风：Q版/正常比例/抽象扭曲/像素/真人/动物拟人/厚涂/线稿等，以及线条色彩特点",
 "emotion": "面部表情与情绪，尽可能细分（如：害羞/发呆装傻/坏笑/疲惫/无语/得意/生气/哭/撒娇等）",
 "atmosphere": "氛围与场合（如：软萌治愈/沙雕搞笑/嘲讽/温馨/色气等）",
 "erotic": "是否带有涩情/色气/性暗示成分：回答 是/否，是的话说明程度（轻微/明显/露骨）",
 "text": "图中是否有文字，有则写出内容（没有写无）",
 "overall": "用一句话概括这张贴纸"
}"""


def load_jpeg_b64(fn):
    from PIL import Image
    im = Image.open(fn)
    im.seek(0)
    im = im.convert('RGB')
    im.thumbnail((640, 640))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def call_api(b64img, retries=3):
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64img}'}},
        ]}],
        'max_tokens': 700,
        'temperature': 0.2,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'raw': content[:200]}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])

    rows = []
    with open(CSV_PATH, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)

    # 已完成的
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            line = line.strip()
            if line:
                d = json.loads(line)
                done[d['rank']] = d

    todo = []
    for r in rows:
        rank = int(r['rank'])
        fn = os.path.join(IMG_DIR, f'rank_{rank:03d}.gif')
        if rank in done or not os.path.exists(fn):
            continue
        todo.append((r, rank, fn))
    if limit:
        todo = todo[:limit]
    print(f'待描述: {len(todo)} 个')

    def work(item):
        r, rank, fn = item
        return rank, call_api(load_jpeg_b64(fn))

    out_lines = []
    n = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            rank, desc = fut.result()
            r = next(r for r in rows if int(r['rank']) == rank)
            rec = {'rank': rank, 'url': r['url'], 'count': int(r['count']), 'summary': r['summary'], 'desc': desc}
            out_lines.append(rec)
            n += 1
            if n % 25 == 0 or n == len(todo):
                print(f'进度 {n}/{len(todo)}')

    with open(OUT, 'a', encoding='utf-8') as f:
        for rec in out_lines:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'[完成] 追加 {len(out_lines)} 条 → {OUT}（累计 {len(done) + len(out_lines)}）')


if __name__ == '__main__':
    main()
