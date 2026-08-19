# -*- coding: utf-8 -*-
"""disagree_v10.py — 用各模型自身阈值重算 v10 四模型投票/分歧

输入: outputs/score-multi-v10.csv（predict_multi 输出，含 p_bert-v10/p_bert-v10-synth/p_bert-v10-wb/p_bert-v7）
输出: 覆盖 score-multi-v10.csv（votes_male/female, flip_count, boundary_std, disagreement）
"""
import csv
import json
import statistics

MODELS = ['bert-v10', 'bert-v10-synth', 'bert-v10-wb', 'bert-v7']

thr = {}
for m in MODELS:
    try:
        met = json.load(open(f'models/{m}/metrics.json', encoding='utf-8'))
        thr[m] = float(met.get('threshold', 0.5))
    except Exception:
        thr[m] = 0.5
print('各模型阈值:', thr)

rows = list(csv.DictReader(open('outputs/score-multi-v10.csv', encoding='utf-8')))
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
    # 参考主模型 = v10-wb（当前生产候选）
    p_main = ps['bert-v10-wb']
    main_thr = thr['bert-v10-wb']
    pred_main = 'female' if p_main is not None and p_main >= main_thr else 'male'
    flips = sum(1 for m in MODELS if ps[m] is not None and
                (ps[m] >= thr[m]) != (p_main >= main_thr))
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
    r['pred_main'] = pred_main
    out.append(r)

out.sort(key=lambda r: -float(r['boundary_std']))
with open('outputs/score-multi-v10.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

from collections import Counter
print('分歧度分布:', dict(Counter(r['disagreement'] for r in out)))
print('票型分布:', dict(Counter(f"{r['votes_male']}男{r['votes_female']}女" for r in out)))
print('高分歧用户数:', sum(1 for r in out if r['disagreement'] == '高'))
print(f'[完成] 覆盖 score-multi-v10.csv（{len(out)} 用户）')
