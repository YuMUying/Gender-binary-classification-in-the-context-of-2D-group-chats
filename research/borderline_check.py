# -*- coding: utf-8 -*-
"""borderline_check.py — 未标注用户中临界区(p∈[0.80,0.95])人数与网络性别分布"""
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
net = {}
for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
    net[r['user_id']] = r['network_gender']
labels = set(r['user_id'] for r in conn.execute("SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')"))
conn.close()

with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    rows = [r for r in csv.DictReader(f)]

border = []
for r in rows:
    uid = int(r['user_id'])
    if uid in labels:
        continue
    p = float(r['prob_female_mean'])
    if 0.80 <= p <= 0.95:
        border.append((uid, p, net.get(uid, 'none'), int(r['n_messages']), r['confidence']))

border.sort(key=lambda x: -x[1])
print(f'未标注且 P(女)∈[0.80,0.95] 的用户: {len(border)} 人')
from collections import Counter
print('网络性别分布:', dict(Counter(b[2] for b in border)))
for uid, p, g, n, conf in border:
    print(f'  {uid}: P(女)={p:.3f} 网络={g} 消息数={n} 置信度={conf}')
