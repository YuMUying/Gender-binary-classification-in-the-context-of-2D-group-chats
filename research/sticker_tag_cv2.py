# -*- coding: utf-8 -*-
"""sticker_tag_cv2.py — 阶段一验证v2：新分级（情绪细类/文字梗/涩情）LOOCV

特征：情绪直方图(9类) + 文字梗占比 + 涩情(ero_max, ero_ratio)
"""
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict

EMOS = ['撒娇卖萌', '发呆装傻', '疲惫困倦', '无语无奈', '委屈哭', '生气嫌弃', '得意坏笑', '开心兴奋', '搞怪沙雕', '中性']

# v2 标签表
tags = {}
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['emotion']:
            tags[r['url']] = r
print(f'已标注贴纸(v2): {len(tags)} 个')

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

user_h = defaultdict(lambda: {'emo': Counter(), 'meme': 0, 'n_tag': 0, 'ero_max': 0, 'ero_n': 0})
user_total_img = Counter()
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
            user_total_img[uid] += 1
            if url in tags:
                t = tags[url]
                user_h[uid]['emo'][t['emotion']] += 1
                user_h[uid]['n_tag'] += 1
                user_h[uid]['meme'] += (1 if t['meme'] == '有' else 0)
                user_h[uid]['ero_max'] = max(user_h[uid]['ero_max'], int(t['ero']))
                user_h[uid]['ero_n'] += (1 if int(t['ero']) >= 1 else 0)
conn.close()

uids = [u for u in labels if user_h[u]['n_tag'] >= 5]
print(f'有效用户(标签贴纸≥5): {len(uids)}/{len(labels)}')
cov = sum(user_h[u]['n_tag'] for u in uids) / max(sum(user_total_img[u] for u in uids), 1)
print(f'覆盖率: {cov:.1%}')

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    def feats(uid):
        h = user_h[uid]
        tot = h['n_tag'] or 1
        v = [h['emo'][e] / tot for e in EMOS]
        v += [h['meme'] / tot, h['ero_max'] / 3, h['ero_n'] / tot, math.log1p(tot)]
        return v

    X = np.array([feats(u) for u in uids])
    y = np.array([1 if labels[u] == 'female' else 0 for u in uids])
    base = max(sum(y == 0), sum(y == 1))
    correct = 0
    preds = []
    for i in range(len(uids)):
        m = np.ones(len(uids), dtype=bool); m[i] = False
        clf = LogisticRegression(max_iter=800)
        clf.fit(StandardScaler().fit_transform(X[m]), y[m])
        p = clf.predict_proba(StandardScaler().fit_transform(X[i:i + 1]))[0, 1]
        preds.append(p)
        if (p >= 0.5) == bool(y[i]):
            correct += 1
    print(f'\n[LOOCV] 贴纸v2通道: {correct}/{len(uids)} = {correct/len(uids):.1%} （基线全猜男: {base}/{len(uids)} = {base/len(uids):.1%}）')
    for uid, p, yi in sorted(zip(uids, preds, y), key=lambda x: -x[1]):
        print(f'   {uid} 真={"女" if yi else "男"} P(女)={p:.3f} 标签数={user_h[uid]["n_tag"]} 撒娇={user_h[uid]["emo"]["撒娇卖萌"]} 文字梗={user_h[uid]["meme"]}')
except ImportError as e:
    print('sklearn 不可用:', e)

# 分性别均值
print('\n=== 分性别贴纸标签均值 ===')
for g in ('male', 'female'):
    grp = [u for u in uids if labels[u] == g]
    if not grp:
        continue
    tot = sum(user_h[u]['n_tag'] for u in grp) or 1
    emo_s = Counter(); meme = sum(user_h[u]['meme'] for u in grp)
    for u in grp:
        for e, c in user_h[u]['emo'].items():
            emo_s[e] += c
    print(f'{g} ({len(grp)}人, {tot}个贴纸): ' + ' '.join(f'{e}={emo_s[e]/tot:.2f}' for e in EMOS if emo_s[e]) + f' | 文字梗={meme/tot:.2f}')
