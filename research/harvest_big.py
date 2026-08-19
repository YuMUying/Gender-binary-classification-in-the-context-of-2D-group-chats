# -*- coding: utf-8 -*-
"""harvest_big.py — 全量收割：Pic + Emoji 缓存 vs 全部消息 file(md5) 匹配

复制命中文件到 data/media/qce-harvest/，输出 research/harvest_map_big.jsonl
"""
import csv
import json
import os
import shutil
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
file2meta = {}
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json LIKE '%image%'"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if isinstance(s, dict) and s.get('type') == 'image':
            d = s.get('data') or {}
            f = d.get('file') or ''
            u = d.get('url') or ''
            if f and u:
                base = os.path.splitext(f)[0].lower()
                file2meta.setdefault(base, (u, f, d.get('summary') or ''))
conn.close()
print(f'消息 file(md5) 总数: {len(file2meta)}')

base = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data')
cache = {}
for sub in ('Pic', 'Emoji'):
    p = os.path.join(base, sub)
    if not os.path.isdir(p):
        continue
    for root, dirs, files in os.walk(p):
        for fn in files:
            b = os.path.splitext(fn)[0].lower()
            if len(b) == 32:
                cache.setdefault(b, os.path.join(root, fn))
print(f'缓存 md5 文件: {len(cache)}')

OUT = 'data/media/qce-harvest'
os.makedirs(OUT, exist_ok=True)
hit = 0
mapping = []
for b, (url, f, sm) in file2meta.items():
    src = cache.get(b)
    if not src:
        continue
    ext = os.path.splitext(src)[1] or os.path.splitext(f)[1] or '.jpg'
    dst = os.path.join(OUT, b + ext)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    mapping.append({'md5': b, 'url': url, 'file': f, 'summary': sm, 'local': dst})
    hit += 1

with open('research/harvest_map_big.jsonl', 'w', encoding='utf-8') as f:
    for m in mapping:
        f.write(json.dumps(m, ensure_ascii=False) + '\n')

# 未标注长尾覆盖统计
known = set()
for csvf in ('outputs/贴纸标签v2.csv', 'outputs/贴纸待标清单.csv'):
    if os.path.exists(csvf):
        with open(csvf, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('url'):
                    known.add(r['url'])
new_urls = [m for m in mapping if m['url'] not in known]
print(f'\n命中并复制: {hit} 个 → {OUT}')
print(f'其中未标注新 URL: {len(new_urls)} 个（可打标）')
print(f'映射表: research/harvest_map_big.jsonl')
