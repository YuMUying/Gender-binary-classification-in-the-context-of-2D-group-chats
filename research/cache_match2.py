# -*- coding: utf-8 -*-
"""cache_match2.py — 重新匹配 Pic 缓存 vs 全部长尾贴纸 md5（当前状态）"""
import json
import os
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 全部消息的 image file 字段（md5 名）
file2url = {}
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
                file2url.setdefault(base, (u, f))
conn.close()
print(f'消息中的 file(md5) 总数: {len(file2url)}')

pic = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic')
cache = {}
for root, dirs, files in os.walk(pic):
    for fn in files:
        base = os.path.splitext(fn)[0].lower()
        if len(base) == 32:
            cache.setdefault(base, os.path.join(root, fn))
print(f'缓存 md5 文件数: {len(cache)}')

hit = []
for base, (url, f) in file2url.items():
    if base in cache:
        hit.append((base, url, f, cache[base]))
print(f'\n=== 缓存命中: {len(hit)} 个 ===')
for base, url, f, path in hit[:30]:
    print(f'  {base[:16]}... {url[-40:]} -> {path}')
print(f'（共 {len(hit)} 个可收割）')
