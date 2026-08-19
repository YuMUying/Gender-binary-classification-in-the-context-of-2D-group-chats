# -*- coding: utf-8 -*-
"""compare_v7.py — 对比旧/新 v7 分数：找出 P(女) 显著变化的用户"""
import csv

old = {}
with open('outputs/score-multi.csv', encoding='utf-8') as f:   # 旧 (14:07, v4-v7)
    for r in csv.DictReader(f):
        v = r.get('p_bert-v7')
        if v:
            old[int(r['user_id'])] = float(v)

new = {}
with open('outputs/score-multi-v9.csv', encoding='utf-8') as f:  # 新 (23:39, v9a/b/c/v7)
    for r in csv.DictReader(f):
        v = r.get('p_bert-v7')
        if v:
            new[int(r['user_id'])] = float(v)

TH = 0.87
changes = []
for uid in sorted(set(old) & set(new)):
    po, pn = old[uid], new[uid]
    flip = (po >= TH) != (pn >= TH)
    if flip or abs(pn - po) > 0.08:
        changes.append((uid, po, pn, flip))

changes.sort(key=lambda x: -abs(x[2] - x[1]))
print(f'对比用户数: {len(set(old) & set(new))} | 显著变化: {len(changes)}')
print(f'\n=== v7 判女翻转（旧男→新女）===')
for uid, po, pn, flip in changes:
    if flip and pn >= TH and po < TH:
        print(f'  {uid}: 旧P(女)={po:.3f} → 新P(女)={pn:.3f}  (男→女 翻转!)')
print(f'\n=== v7 判男翻转（旧女→新男）===')
for uid, po, pn, flip in changes:
    if flip and po >= TH and pn < TH:
        print(f'  {uid}: 旧P(女)={po:.3f} → 新P(女)={pn:.3f}  (女→男 翻转!)')
print(f'\n=== 分数大幅移动（未翻转但 >0.15）===')
for uid, po, pn, flip in changes:
    if not flip and abs(pn - po) > 0.15:
        print(f'  {uid}: {po:.3f} → {pn:.3f} (Δ{abs(pn-po):.3f})')
