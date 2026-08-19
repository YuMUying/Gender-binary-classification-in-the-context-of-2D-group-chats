# -*- coding: utf-8 -*-
"""sticker_loocv.py — 贴纸通道用户级留一交叉验证（零 API）

特征：每用户的贴纸标签分布（撒娇卖萌/抽象/情感标签占比）
分类器：逻辑回归（sklearn），用户级 LOOCV
输出：AUC、准确率、极端用户（图率>50%）单独验证
"""
import csv
import json
import sqlite3
from collections import Counter

import numpy as np

# ---------- 1. 载入贴纸标签 ----------
tags = {}
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r.get('url') and r.get('emotion'):
            tags[r['url']] = r

# 情感类别（标签字段）
EMOTIONS = ['撒娇卖萌', '抽象', '可爱', '震惊', '开心', '生气', '悲伤', '无语', '其他']

# ---------- 2. 已标注用户 ----------
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
print(f'已标注用户: {len(labels)}')

# ---------- 3. 每用户贴纸统计 ----------
# 从 messages.raw_json 提取 image url
user_stats = {}   # uid -> {n_img, n_tag, tag_emotion: count, img_rate}
EXCLUDE = {1215892967, 234300537}  # 报时机器人 + 噪音用户

for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in labels or uid in EXCLUDE:
        continue
    s = user_stats.setdefault(uid, {'n_img': 0, 'n_tag': 0, 'em': Counter()})
    try:
        j = json.loads(r['raw_json'])
        msgs = j.get('message') or []
        if isinstance(msgs, dict):
            msgs = [msgs]
        for seg in msgs:
            if isinstance(seg, dict) and seg.get('type') == 'image':
                url = (seg.get('data') or {}).get('url') or ''
                s['n_img'] += 1
                t = tags.get(url)
                if t:
                    s['n_tag'] += 1
                    em = t.get('emotion') or ''
                    if em:
                        s['em'][em] += 1
    except Exception:
        pass

# 消息总数（算图率）
for uid in user_stats:
    n = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=?", (uid,)).fetchone()['c']
    user_stats[uid]['n_msg'] = n
conn.close()

# ---------- 4. 构建特征矩阵 ----------
feat_users = []
X, y = [], []
for uid, s in user_stats.items():
    total_em = sum(s['em'].values())
    if total_em < 3:      # 贴纸标签太少，无信号
        continue
    vec = []
    for em in EMOTIONS:
        vec.append(s['em'].get(em, 0) / max(total_em, 1))
    vec.append(s['n_img'] / max(s['n_msg'], 1))   # 图率
    vec.append(s['n_tag'] / max(s['n_img'], 1))   # 标签覆盖率
    X.append(vec)
    y.append(1 if labels[uid] == 'female' else 0)
    feat_users.append(uid)

X = np.array(X)
y = np.array(y)
print(f'有贴纸信号的用户: {len(feat_users)}（女 {sum(y)} / 男 {len(y) - sum(y)}）')

# ---------- 5. 用户级 LOOCV（逻辑回归）----------
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score

preds = np.zeros(len(y))
for i in range(len(y)):
    clf = LogisticRegression(max_iter=2000)
    mask = np.ones(len(y), dtype=bool)
    mask[i] = False
    clf.fit(X[mask], y[mask])
    preds[i] = clf.predict_proba(X[i:i+1])[:, 1]

auc = roc_auc_score(y, preds)
acc = accuracy_score(y, (preds >= 0.5).astype(int))
print(f'\n=== 贴纸通道 LOOCV ===')
print(f'AUC: {auc:.3f} | 准确率: {acc:.3f} ({sum((preds>=0.5).astype(int)==y)}/{len(y)})')

# 按性别分
for g, gi in (('女', 1), ('男', 0)):
    idx = np.where(y == gi)[0]
    print(f'{g}: 预测正确 {sum((preds[idx] >= 0.5).astype(int) == gi)}/{len(idx)}')

# ---------- 6. 极端用户（图率 > 50%）----------
print(f'\n=== 极端用户（图率>50%，且贴纸标签>=3）===')
ext = [(uid, s) for uid, s in user_stats.items() if s['n_img'] / max(s['n_msg'], 1) > 0.5 and sum(s['em'].values()) >= 3]
print(f'数量: {len(ext)}')
for uid, s in sorted(ext, key=lambda x: -x[1]['n_img'] / max(x[1]['n_msg'], 1)):
    total_em = sum(s['em'].values())
    top_em = s['em'].most_common(3)
    print(f'  {uid} | {labels[uid]} | 图率={s["n_img"]/max(s["n_msg"],1):.2f} | 贴纸标签={total_em} | 主要情感={top_em}')
