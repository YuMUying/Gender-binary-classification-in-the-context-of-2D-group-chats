# -*- coding: utf-8 -*-
"""erotic_label_stats.py — 标注集质量统计"""
import json
import sqlite3
from collections import Counter, defaultdict

labels = [json.loads(l) for l in open('research/erotic_labels.jsonl', encoding='utf-8') if l.strip()]
print(f'总条数: {len(labels)}')
print('等级分布:', dict(Counter(r['level'] for r in labels)))

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
gender = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    gender[r['user_id']] = r['gender']
conn.close()

per_user = defaultdict(lambda: Counter())
for r in labels:
    per_user[r['user_id']][r['level']] += 1
print(f'覆盖用户: {len(per_user)} 人（男 {sum(1 for u in per_user if gender.get(u)=="male")} / 女 {sum(1 for u in per_user if gender.get(u)=="female")}）')

print('\n=== 分性别等级分布 ===')
for g in ('male', 'female'):
    tot = Counter()
    n_users = 0
    for u, c in per_user.items():
        if gender.get(u) == g:
            n_users += 1
            for k, v in c.items():
                tot[k] += v
    s = sum(tot.values())
    print(f'{g} ({n_users}人, {s}条): ' + ' '.join(f'{k}级={tot[k]} ({tot[k]/s:.0%})' for k in range(4) if tot[k]))

# 每用户标注量
print('\n每用户标注量: ' + ' '.join(f'{u}:{sum(c.values())}' for u, c in sorted(per_user.items(), key=lambda x: -sum(x[1].values()))[:12]))
low = [u for u, c in per_user.items() if sum(c.values()) < 30]
print(f'标注<30条的瘦用户: {len(low)} 个')
