# -*- coding: utf-8 -*-
"""harvest_cache.py — 收割 QQ 客户端 Pic 缓存中与消息匹配的图片

复制到 data/media/harvest/<md5>.<ext>，并输出 url->local 映射 research/harvest_map.jsonl
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

pic = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic')
cache = {}
for root, dirs, files in os.walk(pic):
    for fn in files:
        base = os.path.splitext(fn)[0].lower()
        if len(base) == 32:
            cache.setdefault(base, os.path.join(root, fn))

OUT = 'data/media/harvest'
os.makedirs(OUT, exist_ok=True)

# 已标签的 url（避免重复）
known_urls = set()
for csvf in ('outputs/贴纸标签v2.csv', 'outputs/贴纸待标清单.csv'):
    if os.path.exists(csvf):
        with open(csvf, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('url'):
                    known_urls.add(r['url'])

n_copied = 0
n_new = 0
mapping = []
for base, (url, f, summary) in file2meta.items():
    src = cache.get(base)
    if not src:
        continue
    ext = os.path.splitext(src)[1] or os.path.splitext(f)[1] or '.jpg'
    dst = os.path.join(OUT, base + ext)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        n_copied += 1
    mapping.append({'md5': base, 'url': url, 'file': f, 'summary': summary, 'local': dst})
    if url not in known_urls:
        n_new += 1

with open('research/harvest_map.jsonl', 'w', encoding='utf-8') as f:
    for m in mapping:
        f.write(json.dumps(m, ensure_ascii=False) + '\n')

print(f'匹配 {len(mapping)} 个，复制 {n_copied} 个新文件到 {OUT}')
print(f'其中未标注过的新 URL: {n_new} 个（可进入贴纸打标管线）')
print(f'映射表: research/harvest_map.jsonl')
