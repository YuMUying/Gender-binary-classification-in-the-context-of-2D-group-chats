# -*- coding: utf-8 -*-
"""v6v7_flip.py — v6 vs v7 分歧用户（当前唯一可信的双模型检查）"""
import csv
import json

thr6 = json.load(open('models/bert-v6/metrics.json', encoding='utf-8')).get('threshold', 0.5)
thr7 = json.load(open('models/bert-v7/metrics.json', encoding='utf-8')).get('threshold', 0.5)

rows = list(csv.DictReader(open('outputs/score-multi.csv', encoding='utf-8')))
flips = []
for r in rows:
    p6 = r.get('p_bert-v6')
    p7 = r.get('p_bert-v7')
    if not p6 or not p7:
        continue
    p6, p7 = float(p6), float(p7)
    pred6 = 'female' if p6 >= thr6 else 'male'
    pred7 = 'female' if p7 >= thr7 else 'male'
    if pred6 != pred7:
        flips.append((r['user_id'], pred6, pred7, p6, p7, r.get('label', '')))

flips.sort(key=lambda x: -abs(x[3] - x[4]))
print(f'v6-v7 分歧用户: {len(flips)} / {len(rows)}')
print(f'其中已标注: {sum(1 for f in flips if f[5])}')
print()
print('=== 分歧列表（含已标注的难例核对）===')
for uid, p6, p7, v6, v7, lab in flips:
    mark = ' ← 已标注' if lab else ''
    print(f'  {uid}: v6={p6}({p6}) v7={p7}({v7}) 标注={lab or "-"}{mark}')
