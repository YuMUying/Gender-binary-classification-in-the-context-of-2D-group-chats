# -*- coding: utf-8 -*-
"""disagree_fix.py — 用各模型自身阈值重新计算分歧度（投票型）

输出 outputs/score-multi.csv 修正版：
  votes_male/votes_female 票型, flips(相对v7), boundary_std(边界距离差), disagreement
"""
import csv
import json
import statistics

MODELS = ['bert-v4', 'bert-v6', 'bert-v7']

thr = {}
for m in MODELS:
    try:
        met = json.load(open(f'models/{m}/metrics.json', encoding='utf-8'))
        thr[m] = float(met.get('threshold', 0.5))
    except Exception:
        thr[m] = 0.5
print('各模型阈值:', thr)

rows = list(csv.DictReader(open('outputs/score-multi.csv', encoding='utf-8')))
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
with open('outputs/score-multi.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

from collections import Counter
print('分歧度分布:', dict(Counter(r['disagreement'] for r in out)))
print('票型分布:', dict(Counter(f"{r['votes_male']}男{r['votes_female']}女" for r in out)))
print()
print('=== 高分歧用户（2:2 或 3:1 对翻）===')
for r in out:
    if r['disagreement'] == '高':
        print(f'  {r["user_id"]}: {r["votes_male"]}男{r["votes_female"]}女 v7={r["pred_v7"]} '
              f'v4={r["p_bert-v4"]} v5={r["p_bert-v5"]} v6={r["p_bert-v6"]} v7={r["p_bert-v7"]} '
              f'标注={r["label"] or "-"}')
