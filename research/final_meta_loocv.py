# -*- coding: utf-8 -*-
"""final_meta_loocv.py — 最终用户级元特征 LOOCV（v7文本 + 涩情 + 自述 + 网络性别）

通道：
  T = 文本 v7 p_female
  E = 涩情（API金标 any/max + 本地模型 any/max 两种口径）
  D = 性别自述（male/female 事实声明）
  N = 网络性别
"""
import csv
import json
import math
import sqlite3

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']
net = {}
for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
    net[r['user_id']] = r['network_gender']
conn.close()

textp = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        textp[int(r['user_id'])] = float(r['prob_female_mean'])

ero_api = {}
with open('outputs/erotic_chat.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ero_api[int(r['user_id'])] = r
ero_loc = {}
with open('outputs/erotic_features_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ero_loc[int(r['user_id'])] = r

# 自述特征
decl = {}
for l in open('research/gender_declare_labels.jsonl', encoding='utf-8'):
    l = l.strip()
    if not l:
        continue
    d = json.loads(l)
    u = d['user_id']
    if d['factual'] != 'yes':
        continue
    e = decl.setdefault(u, {'male': 0.0, 'female': 0.0})
    e[d['declared']] = max(e[d['declared']], d['conf'])

uids = sorted(labels)
print(f'用户 {len(uids)}（男{sum(1 for u in uids if labels[u]=="male")}/女{sum(1 for u in uids if labels[u]=="female")}）\n')


def run(name, feats):
    X = np.array([feats(u) for u in uids])
    y = np.array([1 if labels[u] == 'female' else 0 for u in uids])
    base = max(sum(y == 0), sum(y == 1))
    correct = 0
    for i in range(len(uids)):
        m = np.ones(len(uids), dtype=bool); m[i] = False
        sc = StandardScaler().fit(X[m])
        clf = LogisticRegression(max_iter=1000)
        clf.fit(sc.transform(X[m]), y[m])
        p = clf.predict_proba(sc.transform(X[i:i + 1]))[0, 1]
        if (p >= 0.5) == bool(y[i]):
            correct += 1
    print(f'{name}: {correct}/{len(uids)} = {correct/len(uids):.1%} （基线 {base}/{len(uids)} = {base/len(uids):.1%}）')


T = lambda u: [textp.get(u, 0.5)]
E_api = lambda u: [int(ero_api[u]['ero_any']), int(ero_api[u]['ero_max']), float(ero_api[u]['ero_ratio'])] if u in ero_api else [0, 0, 0]
E_loc = lambda u: [int(ero_loc[u]['ero_any']), int(ero_loc[u]['ero_max'])] if u in ero_loc else [0, 0]
D = lambda u: [decl.get(u, {}).get('male', 0), decl.get(u, {}).get('female', 0)]
N = lambda u: [1 if net.get(u) == 'male' else 0, 1 if net.get(u) == 'female' else 0]

run('[文本v7]', T)
run('[文本+涩情API]', lambda u: T(u) + E_api(u))
run('[文本+涩情本地]', lambda u: T(u) + E_loc(u))
run('[文本+自述]', lambda u: T(u) + D(u))
run('[文本+网络性别]', lambda u: T(u) + N(u))
run('[文本+涩情API+自述]', lambda u: T(u) + E_api(u) + D(u))
run('[文本+涩情本地+自述+网络]', lambda u: T(u) + E_loc(u) + D(u) + N(u))

print('\n=== 自述分布 ===')
for u in uids:
    if u in decl:
        print(f'  {u} {labels[u]}: 男声明conf={decl[u].get("male",0):.2f} 女声明conf={decl[u].get("female",0):.2f}')
