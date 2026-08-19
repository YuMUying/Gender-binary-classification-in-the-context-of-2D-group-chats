# -*- coding: utf-8 -*-
"""meta_loocv.py — 用户级元特征 LOOCV：涩情通道 / 贴纸情绪通道 / 文本通道 组合

用法: python research/meta_loocv.py
"""
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

EMOS = ['撒娇卖萌', '发呆装傻', '疲惫困倦', '无语无奈', '委屈哭', '生气嫌弃', '得意坏笑', '开心兴奋', '搞怪沙雕', '中性']

# 涩情通道
ero = {}
with open('outputs/erotic_chat.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ero[int(r['user_id'])] = r

# 贴纸 v2 标签（含长尾追加）
tags = {}
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r.get('emotion'):
            tags[r['url']] = r

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

user_h = defaultdict(lambda: {'emo': Counter(), 'n_tag': 0})
for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in labels:
        continue
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if isinstance(s, dict) and s.get('type') == 'image':
            url = (s.get('data') or {}).get('url') or ''
            if url in tags:
                user_h[uid]['emo'][tags[url]['emotion']] += 1
                user_h[uid]['n_tag'] += 1
conn.close()

# 文本通道 p_female（v7 打分）
textp = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        textp[int(r['user_id'])] = float(r['prob_female_mean'])

uids = sorted(labels)
print(f'用户: {len(uids)} (男 {sum(1 for u in uids if labels[u]=="male")} / 女 {sum(1 for u in uids if labels[u]=="female")})')


def run_cv(name, feats_fn, valid_fn):
    sub = [u for u in uids if valid_fn(u)]
    if len(sub) < 8:
        print(f'{name}: 有效用户过少 ({len(sub)})，跳过')
        return
    X = np.array([feats_fn(u) for u in sub])
    y = np.array([1 if labels[u] == 'female' else 0 for u in sub])
    base = max(sum(y == 0), sum(y == 1))
    correct = 0
    preds = []
    for i in range(len(sub)):
        m = np.ones(len(sub), dtype=bool); m[i] = False
        sc = StandardScaler().fit(X[m])
        clf = LogisticRegression(max_iter=800)
        clf.fit(sc.transform(X[m]), y[m])
        p = clf.predict_proba(sc.transform(X[i:i + 1]))[0, 1]
        preds.append(p)
        if (p >= 0.5) == bool(y[i]):
            correct += 1
    print(f'{name}: {correct}/{len(sub)} = {correct/len(sub):.1%} （基线 {base}/{len(sub)} = {base/len(sub):.1%}）')
    for uid, p, yi in sorted(zip(sub, preds, y), key=lambda x: -x[1]):
        print(f'   {uid} 真={"女" if yi else "男"} P(女)={p:.3f}')
    print()


# 通道1：涩情（全量覆盖）
ero_feats = lambda u: [int(ero[u]['ero_any']), int(ero[u]['ero_max']), float(ero[u]['ero_ratio']),
                       float(ero[u]['ero_hit_ratio']), math.log1p(int(ero[u]['total']))]
run_cv('[涩情聊天]', ero_feats, lambda u: u in ero)

# 通道2：贴纸情绪（≥5标签）
stk_feats = lambda u: [user_h[u]['emo'][e] / user_h[u]['n_tag'] for e in EMOS] + [math.log1p(user_h[u]['n_tag'])]
run_cv('[贴纸情绪]', stk_feats, lambda u: user_h[u]['n_tag'] >= 5)

# 通道3：文本 p_female（基准）
run_cv('[文本v7]', lambda u: [textp.get(u, 0.5)], lambda u: u in textp)

# 通道4：文本 + 涩情
run_cv('[文本+涩情]', lambda u: [textp.get(u, 0.5)] + ero_feats(u), lambda u: u in ero and u in textp)

# 通道5：文本 + 涩情 + 贴纸情绪
run_cv('[文本+涩情+贴纸]', lambda u: [textp.get(u, 0.5)] + ero_feats(u) + stk_feats(u),
       lambda u: u in ero and u in textp and user_h[u]['n_tag'] >= 5)

# 涩情通道的性别统计
print('=== 涩情通道分性别统计 ===')
for g in ('male', 'female'):
    grp = [u for u in uids if labels[u] == g and u in ero]
    any1 = sum(1 for u in grp if int(ero[u]['ero_any']) == 1)
    max3 = sum(1 for u in grp if int(ero[u]['ero_max']) == 3)
    max2 = sum(1 for u in grp if int(ero[u]['ero_max']) == 2)
    print(f'{g} ({len(grp)}人): 参与涩情={any1} ({any1/len(grp):.0%}) | 露骨级3={max3} | 明显级2={max2} | 最大0/1级={len(grp)-any1}')
