# -*- coding: utf-8 -*-
"""diag_v8.py — 诊断 v8 异常：v7/v8 对比 + 头像描述质量"""
import csv
import json
import sqlite3

# 头像描述样本
print('=== 头像描述样本 ===')
desc = {}
for l in open('research/avatar_desc.jsonl', encoding='utf-8'):
    l = l.strip()
    if l:
        d = json.loads(l)
        desc[str(d['uin'])] = d['desc']
for u in ['2933474490', '185327596', '1757193004', '348105425', '3441452166', '1591798171', '2803093623']:
    d = desc.get(u, {})
    print(f'{u}: {str(d.get("overall", "?") or "?")[:70]} | style={str(d.get("style",""))[:30]}')

# v7 vs v8 对比
s7, s8 = {}, {}
for path, out in [('outputs/score-v7-all.csv', s7), ('outputs/score-v8-all.csv', s8)]:
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            out[int(r['user_id'])] = r

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
conn.close()

print('\n=== 已标注用户 v7 vs v8 对比（按 v8 女概率降序）===')
rows = []
for u, g in labels.items():
    a, b = s7.get(u), s8.get(u)
    if not a or not b:
        continue
    rows.append((u, g, float(a['prob_female_mean']), float(b['prob_female_mean']),
                 a['predicted'], b['predicted']))
rows.sort(key=lambda x: -x[3])
for u, g, p7, p8, pr7, pr8 in rows:
    flag = '✓' if pr8 == g else '✗'
    print(f'{u} 真={g} v7={p7:.3f}({pr7}) v8={p8:.3f}({pr8}) {flag}')
