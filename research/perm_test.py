# -*- coding: utf-8 -*-
"""perm_test.py — 置换检验：v7 用户级判定的显著性（45 标注用户 LOOCV 口径）

零假设：模型分数与性别标签无关。
做法：固定每用户 p_female 均值，随机打乱标签 5000 次，
统计"阈值判定准确率"的零分布，比较真实准确率的 p 值。
"""
import csv
import json
import random

rows = list(csv.DictReader(open('outputs/score-v7-all.csv', encoding='utf-8')))
labeled = [(int(r['user_id']), float(r['prob_female_mean']), r['label']) for r in rows if r.get('label') in ('male', 'female')]
threshold = json.load(open('models/bert-v7/metrics.json', encoding='utf-8')).get('threshold', 0.87)
n = len(labeled)
print(f'已标注用户: {n}（男{sum(1 for _,_,l in labeled if l=="male")}/女{sum(1 for _,_,l in labeled if l=="female")}）阈值={threshold}')

y_true = [1 if l == 'female' else 0 for _, _, l in labeled]
ps = [p for _, p, _ in labeled]
real_acc = sum(1 for p, t in zip(ps, y_true) if (p >= threshold) == bool(t)) / n
print(f'真实判定一致率: {real_acc:.1%}')

random.seed(42)
better = 0
n_perm = 5000
for i in range(n_perm):
    y_perm = y_true[:]
    random.shuffle(y_perm)
    acc = sum(1 for p, t in zip(ps, y_perm) if (p >= threshold) == bool(t)) / n
    if acc >= real_acc:
        better += 1
p_value = (better + 1) / (n_perm + 1)
print(f'置换检验 p 值 = {p_value:.4f}（5000 次标签置换）')
print(f'随机标签下的准确率上界（max over 5000 次）与分布参考：')
# 顺便给出随机分布统计
from collections import Counter
import statistics
accs = []
random.seed(42)
for i in range(n_perm):
    y_perm = y_true[:]
    random.shuffle(y_perm)
    accs.append(sum(1 for p, t in zip(ps, y_perm) if (p >= threshold) == bool(t)) / n)
print(f'  零分布: 均值={statistics.mean(accs):.3f} 标准差={statistics.pstdev(accs):.3f} 最大={max(accs):.3f}')
