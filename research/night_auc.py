# -*- coding: utf-8 -*-
"""night_auc.py — 深夜占比的性别区分度量化"""
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

night = {}
for r in conn.execute("""
    SELECT user_id,
           SUM(CASE WHEN strftime('%H', time, 'unixepoch', '+8 hours') IN ('00','01','02','03','04','05') THEN 1 ELSE 0 END) night,
           COUNT(*) c
    FROM messages WHERE user_id IN ({}) AND LENGTH(text) > 4
    GROUP BY user_id""".format(','.join(str(u) for u in labels))):
    if r['c'] >= 50:
        night[r['user_id']] = r['night'] / r['c']

# AUC 计算（深夜占比作为"判女"分数）
pairs = [(v, 1 if labels[u] == 'female' else 0) for u, v in night.items()]
pairs.sort(key=lambda x: x[0])
n_pos = sum(p for _, p in pairs)
n_neg = len(pairs) - n_pos
auc = 0
for i, (v, p) in enumerate(pairs):
    if p == 1:
        auc += sum(1 for v2, p2 in pairs if v2 < v and p2 == 0)
auc = auc / (n_pos * n_neg) if n_pos * n_neg else 0
print(f'深夜占比判女 AUC: {auc:.3f} (0.5=无区分度, 1=完美)')
print(f'样本: 男{sum(1 for _, p in pairs if p==0)} 女{sum(1 for _, p in pairs if p==1)}')

# 中位阈值切分
import statistics
med = statistics.median([v for v, _ in pairs])
fp = [u for u, v in night.items() if v > med and labels[u] == 'male']
fn = [u for u, v in night.items() if v <= med and labels[u] == 'female']
print(f'\n用中位 {med:.3f} 切分: 男误判女 {len(fp)} 人, 女误判男 {len(fn)} 人')
print('男误判(深夜活跃的男性):', fp[:10])
print('女误判(白天活跃的女性):', fn[:10])

# 对比：主模型 P(女) 的 AUC（用 score-v7-all）
import csv
scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = float(r['prob_female_mean'])
pairs2 = [(scores.get(u, 0.5), 1 if labels[u] == 'female' else 0) for u in night if u in scores]
pairs2.sort(key=lambda x: x[0])
n_pos2 = sum(p for _, p in pairs2)
n_neg2 = len(pairs2) - n_pos2
auc2 = 0
for i, (v, p) in enumerate(pairs2):
    if p == 1:
        auc2 += sum(1 for v2, p2 in pairs2 if v2 < v and p2 == 0)
auc2 = auc2 / (n_pos2 * n_neg2) if n_pos2 * n_neg2 else 0
print(f'\n对比: v7 模型 P(女) 判女 AUC: {auc2:.3f}')
conn.close()
