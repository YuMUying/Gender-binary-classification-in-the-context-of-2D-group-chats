# -*- coding: utf-8 -*-
"""seg_types.py — 消息段类型统计 + market_face 字段 + Top face ID"""
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

types = Counter()
mf_fields = Counter()
face_ids = Counter()
img_summary = Counter()
n = 0
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json IS NOT NULL"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    segs = j.get('message') or []
    if not isinstance(segs, list):
        continue
    n += 1
    for s in segs:
        t = s.get('type')
        types[t] += 1
        d = s.get('data') or {}
        if t == 'market_face':
            for k in d:
                mf_fields[k] += 1
        elif t == 'face':
            face_ids[str(d.get('id') or '?')] += 1
        elif t == 'image':
            img_summary[str(d.get('summary') or '(空)')[:20]] += 1

print(f'扫描 {n} 条消息\n')
print('=== 段类型分布 ===')
for t, c in types.most_common(20):
    print(f'  {t}: {c}')
print('\n=== market_face 段的字段 ===')
for k, c in mf_fields.most_common(15):
    print(f'  {k}: {c}')
print('\n=== image 段 summary 取值 ===')
for k, c in img_summary.most_common(10):
    print(f'  {k!r}: {c}')
print('\n=== Top30 face ID ===')
for k, c in face_ids.most_common(30):
    print(f'  {k}: {c}')
conn.close()
