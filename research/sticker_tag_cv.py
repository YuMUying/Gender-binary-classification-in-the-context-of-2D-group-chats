# -*- coding: utf-8 -*-
"""sticker_tag_cv.py — 阶段一验证：贴纸标签通道的判别力（LOOCV）

用 Top-200 已标注贴纸，统计每个已标注用户的贴纸标签直方图
（主类/情绪），逻辑回归留一法评估；同时报告覆盖率。
"""
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict

# 1) 标签表
tags = {}
with open('outputs/贴纸待标清单.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['主类']:
            tags[r['url']] = {'main': r['主类'], 'emo': r['情绪'], 'moe': r['萌系']}
print(f'已标注贴纸: {len(tags)} 个')

# 2) 已标注用户
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

# 3) 每用户贴纸标签直方图 + 覆盖率
MAINS = ['动漫少女', '动漫其他', '动物', '抽象', '真人', '文字梗', '其他']
EMOS = ['害羞可爱', '生气', '搞笑', '哭', '中性']
user_h = {}
user_total_img = defaultdict(int)
user_tagged = defaultdict(int)
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
                user_tagged[uid] += 1
                h = user_h.setdefault(uid, {'main': Counter(), 'emo': Counter()})
                h['main'][tags[url]['main']] += 1
                h['emo'][tags[url]['emo']] += 1
conn.close()

uids = [u for u in labels if u in user_h and user_tagged.get(u, 0) >= 5]
print(f'有效用户(标记贴纸≥5次): {len(uids)}/{len(labels)}')
cov = sum(user_tagged.get(u, 0) for u in uids) / max(sum(user_total_img.get(u, 0) for u in uids), 1)
print(f'贴纸覆盖率(有效用户中): {cov:.1%}')

# 4) LOOCV 逻辑回归
try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    def feats(uid):
        h = user_h[uid]
        tot = sum(h['main'].values()) or 1
        v = [h['main'][m] / tot for m in MAINS] + [h['emo'][e] / tot for e in EMOS]
        v += [math.log1p(user_tagged.get(uid, 0))]
        return v

    X = np.array([feats(u) for u in uids])
    y = np.array([1 if labels[u] == 'female' else 0 for u in uids])
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
    print(f'\n[LOOCV] 贴纸标签通道: {correct}/{len(uids)} = {correct/len(uids):.1%} （基线: 全猜男 = {max(sum(1 for u in uids if labels[u]=="male"), sum(1 for u in uids if labels[u]=="female"))}/{len(uids)} = {max(sum(1 for u in uids if labels[u]=="male"), sum(1 for u in uids if labels[u]=="female"))/len(uids):.1%}）')
    for uid, p, yi in sorted(zip(uids, preds, y), key=lambda x: -x[1])[:15]:
        print(f'   {uid} 真={"女" if yi else "男"} P(女|贴纸)={p:.3f} 标记数={user_tagged.get(uid, 0)}')
except ImportError as e:
    print('sklearn 不可用:', e)

# 5) 分性别情绪均值对比
print('\n=== 分性别贴纸标签均值（有效用户）===')
for g in ('male', 'female'):
    grp = [u for u in uids if labels[u] == g]
    if not grp:
        continue
    main_s = Counter(); emo_s = Counter(); n = 0
    for u in grp:
        for m, c in user_h[u]['main'].items():
            main_s[m] += c
        for e, c in user_h[u]['emo'].items():
            emo_s[e] += c
        n += user_tagged[u]
    print(f'{g} ({len(grp)}人, {n}个贴纸): 主类 ' + ' '.join(f'{m}={main_s[m]/max(n,1):.2f}' for m in MAINS if main_s[m]))
    print(f'   情绪 ' + ' '.join(f'{e}={emo_s[e]/max(n,1):.2f}' for e in EMOS if emo_s[e]))
