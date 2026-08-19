# -*- coding: utf-8 -*-
"""female_candidates_v10.py — 基于 bert-v10 的女性候选清单"""
import csv
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 已标注（排除）
labeled = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
excluded = {1215892967, 234300537}  # 报时机器人 + 噪音

# v10 预测
v10 = {}
with open('outputs/score-v10-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        v10[int(r['user_id'])] = r

# 每用户消息数、有效文本数、图率
stats = {}
for r in conn.execute("SELECT user_id, COUNT(*) c, SUM(CASE WHEN LENGTH(text)>=4 AND text NOT LIKE '[%' THEN 1 ELSE 0 END) eff FROM messages WHERE scene='group' GROUP BY user_id"):
    stats[r['user_id']] = {'c': r['c'], 'eff': r['eff']}

# 昵称
nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']

cand = []
for uid, sc in v10.items():
    if uid in labeled or uid in excluded or uid not in stats:
        continue
    st = stats[uid]
    if st['eff'] < 60:
        continue
    p = float(sc['prob_female_mean'])
    if p < 0.45:
        continue
    cand.append({
        'uid': uid, 'nick': nick.get(uid, '') or '', 'n': st['c'], 'eff': st['eff'],
        'p': p, 'pred': sc['predicted'], 'conf': sc['confidence'], 'std': sc['prob_female_std'],
    })

cand.sort(key=lambda x: (-x['p'], -x['eff']))
print(f'候选: {len(cand)} 人\n')
for i, c in enumerate(cand, 1):
    print(f"{i}. {c['uid']} | {c['nick'][:14]} | 消息{c['n']} 有效{c['eff']} | P(女)={c['p']:.3f} | {c['pred']}/{c['conf']} | std={c['std']}")

# 存 CSV
with open('outputs/女性候选v10.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['序号', 'QQ号', '昵称', '消息数', '有效文本', 'P(女)', '结论', '置信', 'std'])
    for i, c in enumerate(cand, 1):
        w.writerow([i, c['uid'], c['nick'], c['n'], c['eff'], round(c['p'], 4), c['pred'], c['conf'], c['std']])
print('\n已存 outputs/女性候选v10.csv')
conn.close()
