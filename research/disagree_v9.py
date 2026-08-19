# -*- coding: utf-8 -*-
"""disagree_v9.py — 用各模型自身阈值重算 v9 四模型投票/分歧（修正统一阈值 bug）

输出 outputs/score-multi-v9.csv 修正版（votes_male/female, flip_count, boundary_std, disagreement）
"""
import csv
import json
import statistics

MODELS = ['bert-v9a', 'bert-v9b', 'bert-v9c', 'bert-v7']

thr = {}
for m in MODELS:
    try:
        met = json.load(open(f'models/{m}/metrics.json', encoding='utf-8'))
        thr[m] = float(met.get('threshold', 0.5))
    except Exception:
        thr[m] = 0.5
print('各模型阈值:', thr)

rows = list(csv.DictReader(open('outputs/score-multi-v9.csv', encoding='utf-8')))
out = []
for r in rows:
    ps = {}
    for m in MODELS:
        v = r.get(f'p_{m}')
        ps[m] = float(v) if v else None
    votes_m = votes_f = 0
    dists = []
    for m in MODELS:
        p = ps[m]
        if p is None:
            continue
        if p >= thr[m]:
            votes_f += 1
        else:
            votes_m += 1
        dists.append(p - thr[m])
    n = len(dists)
    bstd = statistics.pstdev(dists) if n > 1 else 0.0
    p7 = ps['bert-v7']
    pred7 = 'female' if p7 is not None and p7 >= thr['bert-v7'] else 'male'
    flips = sum(1 for m in MODELS[:-1] if ps[m] is not None and
                (ps[m] >= thr[m]) != (p7 >= thr['bert-v7']))
    if votes_m == votes_f:
        disagree = '高'
    elif flips >= 2 or bstd >= 0.15:
        disagree = '高'
    elif flips == 1 or bstd >= 0.08:
        disagree = '中'
    else:
        disagree = '低'
    r['votes_male'] = votes_m
    r['votes_female'] = votes_f
    r['boundary_std'] = round(bstd, 4)
    r['flip_count'] = flips
    r['disagreement'] = disagree
    out.append(r)

out.sort(key=lambda r: -float(r['boundary_std']))
with open('outputs/score-multi-v9.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

from collections import Counter
print('分歧度分布:', dict(Counter(r['disagreement'] for r in out)))
print('票型分布:', dict(Counter(f"{r['votes_male']}男{r['votes_female']}女" for r in out)))
