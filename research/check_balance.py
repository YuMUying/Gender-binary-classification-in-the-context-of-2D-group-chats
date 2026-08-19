# -*- coding: utf-8 -*-
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
rows = conn.execute("SELECT gender, COUNT(*) FROM speaker_labels WHERE gender IN ('male','female') GROUP BY gender").fetchall()
print('标注集(全部):', dict(rows))
conn.close()

train = [json.loads(l) for l in open('data/train.jsonl', encoding='utf-8')]
val = [json.loads(l) for l in open('data/val.jsonl', encoding='utf-8')]
print('train 消息:', dict(Counter(r['label'] for r in train)))
print('val 消息:', dict(Counter(r['label'] for r in val)))
tl = {r['user_id']: r['label'] for r in train}
vl = {r['user_id']: r['label'] for r in val}
print('train 用户:', dict(Counter(tl.values())), '| val 用户:', dict(Counter(vl.values())))

tu = Counter(r['user_id'] for r in train)
m_samples = [tu[u] for u in tl if tl[u] == 'male']
f_samples = [tu[u] for u in tl if tl[u] == 'female']
ms = sorted(m_samples); fs = sorted(f_samples)
print(f'train 男用户样本: min={ms[0]} med={ms[len(ms)//2]} max={ms[-1]}')
print(f'train 女用户样本: min={fs[0]} med={fs[len(fs)//2]} max={fs[-1]}')
print(f'男样本总量: {sum(m_samples)} | 女样本总量: {sum(f_samples)}')
