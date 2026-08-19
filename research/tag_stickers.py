# -*- coding: utf-8 -*-
"""tag_stickers.py — 用中转站视觉模型批量给贴纸打标签（主类×情绪+萌系）

读取 outputs/贴纸待标清单.csv，对每张本地贴纸调用 gpt-5.4-mini 视觉理解，
回填 主类/情绪/萌系 列。并发 4，失败重试 3 次。
用法: set RELAY_KEY=sk-... ; python research/tag_stickers.py
"""
import base64
import csv
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.4-mini'
CSV_PATH = 'outputs/贴纸待标清单.csv'
IMG_DIR = 'data/sticker_tags'

PROMPT = """你是表情包分类器。看这张贴纸图片，输出 JSON：{"main":"主类","emotion":"情绪","moe":"是/否"}
主类只能从这些选：动漫少女、动漫其他、动物、抽象、真人、文字梗、其他
情绪只能从这些选：害羞可爱、生气、搞笑、哭、中性
moe 表示画风是否萌系可爱，只能是 是 或 否
只输出 JSON，不要其他文字。"""


def load_image_b64(fn):
    from PIL import Image
    im = Image.open(fn)
    im.seek(0)
    im = im.convert('RGB')
    im.thumbnail((512, 512))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def call_api(b64img, retries=3):
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64img}'}},
        ]}],
        'max_tokens': 120,
        'temperature': 0,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            # 提取 JSON
            s = content.find('{')
            e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'raw': content}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY 环境变量'); return
    rows = []
    with open(CSV_PATH, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)

    todo = [(r, i) for i, r in enumerate(rows) if os.path.exists(os.path.join(IMG_DIR, f'rank_{int(r["rank"]):03d}') + '.gif')]
    print(f'待标注: {len(todo)} 个')

    results = {}

    def work(item):
        r, i = item
        fn = os.path.join(IMG_DIR, f'rank_{int(r["rank"]):03d}.gif')
        b64 = load_image_b64(fn)
        return r['rank'], call_api(b64)

    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            rank, tag = fut.result()
            results[rank] = tag
            done += 1
            if done % 20 == 0 or done == len(todo):
                print(f'进度 {done}/{len(todo)}')

    # 回填 CSV
    from collections import Counter
    main_c = Counter(); emo_c = Counter(); moe_c = Counter(); errs = []
    for r in rows:
        tag = results.get(r['rank'], {})
        main = tag.get('main', '')
        emo = tag.get('emotion', '')
        moe = tag.get('moe', '')
        if 'error' in tag or not main:
            errs.append((r['rank'], tag.get('error', tag.get('raw', '?')[:60])))
            continue
        r['主类'] = main; r['情绪'] = emo; r['萌系'] = moe
        main_c[main] += 1; emo_c[emo] += 1; moe_c[moe] += 1

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['rank', 'url', 'count', 'summary', 'local_path', '主类', '情绪', '萌系'])
        w.writeheader()
        w.writerows(rows)

    print(f'\n标注完成: 成功 {len(rows) - len(errs)}/{len(rows)}')
    print('主类分布:', dict(main_c))
    print('情绪分布:', dict(emo_c))
    print('萌系分布:', dict(moe_c))
    if errs:
        print('失败项(前10):')
        for rank, e in errs[:10]:
            print(f'  rank {rank}: {e}')


if __name__ == '__main__':
    main()
