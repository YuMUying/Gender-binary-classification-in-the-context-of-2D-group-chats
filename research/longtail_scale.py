# -*- coding: utf-8 -*-
"""longtail_scale.py — 统计补标规模"""
import csv
import json
import sqlite3
from collections import Counter, defaultdict

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

known = set()
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r.get('emotion'):
            known.add(r['url'])
print(f'已有标签贴纸: {len(known)}')

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
conn.close()

todo_users = []
for uid, cnt in user_stickers.items():
    total_uses = sum(cnt.values())
    known_uses = sum(v for u, v in cnt.items() if u in known)
    n_known = sum(1 for u in cnt if u in known)
    if total_uses == 0:
        continue
    if n_known < 5 or known_uses / total_uses < 0.3:
        todo_users.append(uid)

need = Counter()
for uid in todo_users:
    for url, c in user_stickers[uid].items():
        if url not in known:
            need[url] += c

print(f'需补标用户: {len(todo_users)}')
for uid in sorted(todo_users):
    cnt = user_stickers[uid]
    total_uses = sum(cnt.values())
    n_known = sum(1 for u in cnt if u in known)
    known_uses = sum(v for u, v in cnt.items() if u in known)
    print(f'  {uid} {labels[uid]}: 去重={len(cnt)} 已知={n_known} 覆盖={known_uses/total_uses:.0%}')
print(f'\n待补贴纸: {len(need)} 个（覆盖 {sum(need.values())} 次使用）')
print('使用次数分布: top10 =', need.most_common(10))
