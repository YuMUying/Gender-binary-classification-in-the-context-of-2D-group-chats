# -*- coding: utf-8 -*-
"""sticker_signal.py — 实测贴纸/表情使用信号对性别的判别力（Phase 0）

从 raw_json 提取 image/market_face/face 段，构造每用户贴纸特征：
  - image_rate / face_rate / market_rate（发图、系统表情、市场贴纸占比）
  - distinct_stickers（去重贴纸数）、sticker_total、sticker_per_msg
  - 贴纸熵（多样性）
用留一法逻辑回归评估该通道单独的分类能力，并输出男女贴纸使用差异。
"""
import json
import math
import sqlite3
from collections import Counter, defaultdict

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 已标注用户
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

# 全量消息的贴纸段（一次扫描）
user_msgs = defaultdict(int)
user_img = defaultdict(int)
user_face = defaultdict(int)
user_market = defaultdict(int)
user_stickers = defaultdict(set)   # 去重 image url/file_id
user_face_ids = defaultdict(Counter)
vocab = Counter()
n_img_msgs = 0
n_total = 0

for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in labels:
        continue
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    segs = j.get('message') or []
    if not isinstance(segs, list):
        continue
    n_total += 1
    user_msgs[uid] += 1
    has_img = False
    for s in segs:
        d = s.get('data') or {}
        t = s.get('type')
        if t == 'image':
            key = d.get('url') or d.get('file') or d.get('file_id') or ''
            user_img[uid] += 1
            has_img = True
            if key:
                user_stickers[uid].add(('img', key))
                vocab[key] += 1
        elif t == 'market_face':
            mid = str(d.get('id') or '')
            user_market[uid] += 1
            has_img = True
            if mid:
                user_stickers[uid].add(('mk', mid))
                vocab[('mk', mid)] += 1
        elif t == 'face':
            fid = str(d.get('id') or '')
            user_face[uid] += 1
            user_face_ids[uid][fid] += 1
    if has_img:
        n_img_msgs += 1

conn.close()

print(f'已标注用户消息扫描: {n_total} 条，其中含图/贴纸消息 {n_img_msgs} 条 ({n_img_msgs/max(n_total,1):.1%})')
print(f'去重贴纸(自定义图+市场贴纸)词表: {len(vocab)} 个')
print(f'Top15 贴纸使用频率:')
for k, c in vocab.most_common(15):
    print(f'   {k[0]}:{str(k[1])[:36]} x{c}')
print()

# 每用户特征
feats = {}
for uid, t in labels.items():
    n = user_msgs.get(uid, 0)
    if n == 0:
        continue
    nst = len(user_stickers.get(uid, set()))
    tot = user_img.get(uid, 0) + user_market.get(uid, 0)
    # 熵
    cnt = Counter()
    for s in user_stickers.get(uid, set()):
        cnt[s] += 1
    total_s = sum(cnt.values()) or 1
    ent = -sum((c / total_s) * math.log2(c / total_s) for c in cnt.values()) if total_s > 1 else 0
    feats[uid] = {
        'label': t, 'n': n,
        'img_rate': user_img.get(uid, 0) / n,
        'face_rate': user_face.get(uid, 0) / n,
        'market_rate': user_market.get(uid, 0) / n,
        'sticker_per_msg': tot / n,
        'distinct': nst,
        'entropy': ent,
    }

print(f'有效用户: {len(feats)} 人')
print()
print(f'{"QQ":<12}{"性别":<4}{"条数":<6}{"发图率":<8}{"表情率":<8}{"贴纸率":<8}{"去重贴纸":<8}{"熵":<6}')
for uid, f in sorted(feats.items(), key=lambda x: -x[1]['n'])[:20]:
    print(f'{uid:<12}{f["label"]:<4}{f["n"]:<6}{f["img_rate"]:<8.3f}{f["face_rate"]:<8.3f}{f["sticker_per_msg"]:<8.3f}{f["distinct"]:<8}{f["entropy"]:<6.2f}')

# 分性别均值
print()
for g in ('male', 'female'):
    grp = [f for f in feats.values() if f['label'] == g]
    if not grp:
        continue
    print(f'=== {g} ({len(grp)}人) ===')
    for k in ('img_rate', 'face_rate', 'sticker_per_msg', 'distinct', 'entropy'):
        vals = [f[k] for f in grp]
        print(f'   {k}: 均值={sum(vals)/len(vals):.3f}')
print()

# LOOCV 逻辑回归（贴纸特征通道单独分类）
try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    uids = [u for u in feats if feats[u]['n'] >= 10]
    X = np.array([[feats[u]['img_rate'], feats[u]['face_rate'], feats[u]['sticker_per_msg'],
                   math.log1p(feats[u]['distinct']), feats[u]['entropy']] for u in uids])
    y = np.array([1 if feats[u]['label'] == 'female' else 0 for u in uids])
    correct = 0
    preds = []
    for i in range(len(uids)):
        m = np.ones(len(uids), dtype=bool)
        m[i] = False
        sc = StandardScaler().fit(X[m])
        clf = LogisticRegression(max_iter=500)
        clf.fit(sc.transform(X[m]), y[m])
        p = clf.predict_proba(sc.transform(X[i:i + 1]))[0, 1]
        preds.append(p)
        if (p >= 0.5) == bool(y[i]):
            correct += 1
    print(f'[LOOCV] 贴纸特征通道单独分类（{len(uids)}人, n>=10）: {correct}/{len(uids)} = {correct/len(uids):.1%}')
    print('  （对比：纯文本 v7 模型在这批用户上是 91.1%；随机猜测 73% 男基线）')
    for uid, p, yi in sorted(zip(uids, preds, y), key=lambda x: -x[1]):
        print(f'   {uid} 真={"女" if yi else "男"} P(女|贴纸)={p:.3f}')
except ImportError as e:
    print('sklearn 不可用:', e)
