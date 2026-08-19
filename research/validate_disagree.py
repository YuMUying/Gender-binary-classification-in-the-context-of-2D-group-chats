# -*- coding: utf-8 -*-
"""validate_disagree.py — 预验证：分歧度信号是否预测模型错误（64 标注用户）

问题：v6v7 翻案 / 边界分歧度 高的用户，v7 是否更容易判错？
若显著相关 → 冲突指数值得做；否则只是噪声。
"""
import csv
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
conn.close()

scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

multi = {}
with open('outputs/score-multi.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        multi[int(r['user_id'])] = r

rows = []
for uid, g in labels.items():
    s = scores.get(uid)
    m = multi.get(uid)
    if not s or not m:
        continue
    p7 = float(s['prob_female_mean'])
    pred7 = s['predicted']
    correct = pred7 == g
    rows.append({
        'uid': uid, 'label': g, 'pred': pred7, 'correct': correct,
        'flip': m.get('flip_count', '0'), 'bstd': float(m.get('boundary_std', 0) or 0),
        'disagree': m.get('disagreement', '低'),
        'std': float(s['prob_female_std']),
    })

n = len(rows)
err = [r for r in rows if not r['correct']]
print(f'已标注用户: {n}，v7 错误: {len(err)}（{len(err)/n:.1%}）\n')

# 1) 翻案 vs 错误
flip_rows = [r for r in rows if int(r['flip']) >= 1]
noflip_rows = [r for r in rows if int(r['flip']) == 0]
for name, grp in [('翻案(v6≠v7)', flip_rows), ('不翻案', noflip_rows)]:
    if grp:
        e = sum(1 for r in grp if not r['correct'])
        print(f'{name}: {len(grp)} 人，错误 {e}（{e/len(grp):.1%}）')

# 2) 分歧度等级 vs 错误
for lvl in ('高', '中', '低'):
    grp = [r for r in rows if r['disagree'] == lvl]
    if grp:
        e = sum(1 for r in grp if not r['correct'])
        print(f'分歧度={lvl}: {len(grp)} 人，错误 {e}（{e/len(grp):.1%}）')

# 3) 边界分歧度 top vs 错误
import statistics
bstd_hi = [r for r in rows if r['bstd'] >= 0.08]
bstd_lo = [r for r in rows if r['bstd'] < 0.08]
for name, grp in [('边界分歧≥0.08', bstd_hi), ('边界分歧<0.08', bstd_lo)]:
    if grp:
        e = sum(1 for r in grp if not r['correct'])
        print(f'{name}: {len(grp)} 人，错误 {e}（{e/len(grp):.1%}）')

print('\n=== 错误用户的分歧特征 ===')
for r in err:
    print(f'  {r["uid"]} 真={r["label"]} 预={r["pred"]} 翻案={r["flip"]} 边界std={r["bstd"]:.3f} 分歧={r["disagree"]} 文本std={r["std"]:.3f}')
