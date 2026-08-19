# -*- coding: utf-8 -*-
"""tag_v2.py — 基于 gpt-5.5 自由描述，按新分级体系批量打标（纯文本，不重新看图）

新分级（数据驱动，从描述分析归纳）：
  情绪(单选): 撒娇卖萌/发呆装傻/疲惫困倦/无语无奈/委屈哭/生气嫌弃/得意坏笑/开心兴奋/搞怪沙雕/中性
  画风(单选): Q版/正常比例/抽象/真人/其他
  涩情等级: 0(无)/1(轻微)/2(明显)/3(露骨)
  文字梗: 有/无
  萌系: 是/否
输出 outputs/贴纸标签v2.csv
"""
import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
SRC = 'research/sticker_desc.jsonl'
OUT = 'outputs/贴纸标签v2.csv'

TAXO = """根据贴纸描述，为这张QQ表情包贴纸打标签，输出JSON：
{"emotion":"...","style":"...","ero":0,"meme":"有/无","moe":"是/否"}
emotion 只能选一个：撒娇卖萌/发呆装傻/疲惫困倦/无语无奈/委屈哭/生气嫌弃/得意坏笑/开心兴奋/搞怪沙雕/中性
style 只能选一个：Q版/正常比例/抽象/真人/其他
ero 是涩情等级整数：0无/1轻微/2明显/3露骨
meme 指是否有文字梗：有/无
moe 画风是否萌系：是/否
只输出JSON。"""


def call_api(desc_text, retries=3):
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': TAXO + '\n\n贴纸描述：' + json.dumps(desc_text, ensure_ascii=False)}],
        'max_tokens': 120,
        'temperature': 0,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'error': content[:100]}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    recs = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    print(f'待打标: {len(recs)}')

    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(call_api, r['desc']): r['rank'] for r in recs}
        for fut in as_completed(futs):
            rank = futs[fut]
            results[rank] = fut.result()
            done += 1
            if done % 40 == 0 or done == len(recs):
                print(f'进度 {done}/{len(recs)}')

    from collections import Counter
    emo_c = Counter(); style_c = Counter(); ero_c = Counter(); meme_c = Counter(); moe_c = Counter()
    errs = []
    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rank', 'url', 'count', 'summary', 'emotion', 'style', 'ero', 'meme', 'moe', 'desc_content'])
        for r in recs:
            t = results.get(r['rank'], {})
            if 'error' in t or not t.get('emotion'):
                errs.append((r['rank'], t.get('error', '?')))
                continue
            emo_c[t['emotion']] += 1; style_c[t['style']] += 1
            ero_c[t['ero']] += 1; meme_c[t['meme']] += 1; moe_c[t['moe']] += 1
            w.writerow([r['rank'], r['url'], r['count'], r['summary'], t['emotion'], t['style'],
                        t['ero'], t['meme'], t['moe'], (r['desc'].get('content') or '')[:80]])
    print(f'\n[完成] 成功 {len(recs) - len(errs)}/{len(recs)}')
    print('情绪:', dict(emo_c))
    print('画风:', dict(style_c))
    print('涩情:', dict(ero_c))
    print('文字梗:', dict(meme_c))
    print('萌系:', dict(moe_c))
    if errs:
        print('失败:', errs[:10])


if __name__ == '__main__':
    main()
