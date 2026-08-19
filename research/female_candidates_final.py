# -*- coding: utf-8 -*-
"""female_candidates_final.py — 值得标注的候选女性（排除已标注）"""
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

labeled = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
excluded = {1215892967, 234300537}

# v10 预测
v10 = {}
with open('outputs/score-v10-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        v10[int(r['user_id'])] = r

# 参考包指数（MSI/RI/涩情）
ref = {}
try:
    with open('outputs/标定参考包.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            ref[int(r['QQ号'])] = r
except Exception:
    pass

stats = {}
for r in conn.execute("SELECT user_id, COUNT(*) c, SUM(CASE WHEN LENGTH(text)>=4 AND text NOT LIKE '[%' THEN 1 ELSE 0 END) eff FROM messages WHERE scene='group' GROUP BY user_id"):
    stats[r['user_id']] = (r['c'], r['eff'])

nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']

cand = []
for uid, sc in v10.items():
    if uid in labeled or uid in excluded or uid not in stats:
        continue
    n, eff = stats[uid]
    if eff < 60:
        continue
    p = float(sc['prob_female_mean'])
    if p < 0.4:
        continue
    r = ref.get(uid, {})
    cand.append({
        'uid': uid, 'nick': nick.get(uid, '') or '', 'n': n, 'eff': eff,
        'p': p, 'conf': sc['confidence'], 'std': sc['prob_female_std'],
        'msi': r.get('男侧证据指数', ''), 'ri': r.get('复核指数', ''),
        'ero_max': r.get('涩情max', ''), 'night': r.get('深夜占比', ''),
    })

cand.sort(key=lambda x: (-x['p'], -x['eff']))
print(f'候选: {len(cand)} 人\n')
for i, c in enumerate(cand, 1):
    print(f"{i}. {c['uid']} | {c['nick'][:14]} | 消息{c['n']} 有效{c['eff']} | P(女)={c['p']:.3f} {c['conf']} | std={c['std']} | MSI={c['msi']} RI={c['ri']} 涩情max={c['ero_max']} 深夜={c['night']}")

with open('outputs/候选女性_待标注.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['序号', 'QQ号', '昵称', '消息数', '有效文本', 'P(女)', '置信', 'std', 'MSI', 'RI', '涩情max', '深夜占比'])
    for i, c in enumerate(cand, 1):
        w.writerow([i, c['uid'], c['nick'], c['n'], c['eff'], round(c['p'], 4), c['conf'], c['std'], c['msi'], c['ri'], c['ero_max'], c['night']])
print('\n已存 outputs/候选女性_待标注.csv')
conn.close()
