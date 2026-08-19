# -*- coding: utf-8 -*-
"""cache_match.py — 测试 file(md5) → QQ Pic 缓存映射，统计长尾贴纸可命中数"""
import json
import os
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 收集长尾需要的 url -> file(md5)
needed = {}
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json IS NOT NULL"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if isinstance(s, dict) and s.get('type') == 'image':
            d = s.get('data') or {}
            url = d.get('url') or ''
            f = d.get('file') or ''
            if url and f:
                needed.setdefault(url, f)
conn.close()
print(f'含 file 字段的贴纸 url: {len(needed)}')

pic = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic')
# 建立缓存文件名索引（md5 名）
cache = {}
for root, dirs, files in os.walk(pic):
    for f in files:
        base = os.path.splitext(f)[0]
        if len(base) == 32:
            cache.setdefault(base, os.path.join(root, f))

hit = 0
miss = []
for url, f in needed.items():
    base = os.path.splitext(f)[0]
    if base in cache:
        hit += 1
    else:
        miss.append((url, f))
print(f'缓存命中: {hit}/{len(needed)}，未命中: {len(miss)}')
print('未命中样本:', miss[:5])
