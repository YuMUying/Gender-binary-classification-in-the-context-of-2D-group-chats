# -*- coding: utf-8 -*-
"""xnn_index.py — 新版双指数体系 v4

男娘指数（XNN，0-100）：
  特征 = 男娘话题(女装/伪娘/男娘/药娘/丝袜/小裙子/jk/lo裙/白丝/黑丝/穿裙/女装大佬)
        + 稀有萌系(qwq/QAQ/TAT/叭/诶嘿/Orz/OvO/OwO/嘤嘤/呜呜)
        + 自称女性(人家/咱家/本小姐/伦家/奴家/妾身/本宫/小妹)
  权重按词级区分度（阳性/正常男每千条比值）

小众性取向指数（LGBT，0-100，独立）：
  特征 = 百合/BL/耽美/同人女/嗑cp/磕cp/gl向/bl向/南通/基佬/弯了/弯的/gay/男同/给子/txl

输出: outputs/xnn_index.csv（男娘）+ outputs/lgbt_index.csv（小众性取向）
"""
import csv
import re
import sqlite3
from collections import defaultdict

# ---------------- 特征定义 ----------------
XNN_FEATURES = {
    '男娘话题': re.compile(r'(男娘|女装|伪娘|药娘|丝袜|小裙子|jk裙|lo裙|白丝|黑丝|穿裙|女装大佬|女装吧|男娘吧)'),
    '稀有萌系': re.compile(r'(qwq|QAQ|TAT|Orz|OvO|OwO|>_<|叭|诶嘿|嘤嘤|呜呜|捏~)'),
    '自称女性': re.compile(r'(人家|咱家|本小姐|伦家|奴家|妾身|本宫|小妹)'),
}
LGBT_FEATURES = {
    '百合BL': re.compile(r'(百合|gl向|耽美|同人女|嗑cp|磕cp|bl向|bl文|同人文)'),
    '同性恋话题': re.compile(r'(南通|基佬|弯了|弯的|gay|男同|给子|txl|通讯录|出柜)'),
}

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 正样本：orientation 男性（含 unknown 的 1965417382 单独处理）
pos_users = set()
for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    if r['orientation'] != '同性恋':   # 男娘指数正样本排除纯同性恋
        pos_users.add(r['user_id'])
normal_male = set(r['user_id'] for r in conn.execute(
    "SELECT user_id FROM speaker_labels WHERE gender='male'")) - pos_users

print(f"男娘正样本: {len(pos_users)} 人 {sorted(pos_users)}")
print(f"正常男: {len(normal_male)} 人")

# 统计所有用户特征
user_stats = defaultdict(lambda: {'n': 0, **{k: 0 for k in XNN_FEATURES}, **{k: 0 for k in LGBT_FEATURES}})
for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
    uid = r['user_id']
    s = user_stats[uid]
    s['n'] += 1
    t = r['text'] or ''
    for k, pat in XNN_FEATURES.items():
        if pat.search(t):
            s[k] += 1
    for k, pat in LGBT_FEATURES.items():
        if pat.search(t):
            s[k] += 1

def avg_rates(stats, uids, feats):
    sums = {k: 0.0 for k in feats}
    cnt = 0
    for uid in uids:
        s = stats.get(uid)
        if not s or s['n'] == 0:
            continue
        cnt += 1
        for k in feats:
            sums[k] += s[k] / s['n']
    for k in feats:
        sums[k] /= max(cnt, 1)
    return sums

pos_avg = avg_rates(user_stats, pos_users, XNN_FEATURES)
normal_avg = avg_rates(user_stats, normal_male, XNN_FEATURES)
print("\n=== 男娘特征区分度（阳性/正常男 比值） ===")
for k in XNN_FEATURES:
    ratio = pos_avg[k] / normal_avg[k] if normal_avg[k] > 0 else float('inf')
    print(f"  {k}: 阳性={pos_avg[k]:.5f} 正常={normal_avg[k]:.5f} 比值={ratio:.2f}")

pos_l = avg_rates(user_stats, pos_users, LGBT_FEATURES)
normal_l = avg_rates(user_stats, normal_male, LGBT_FEATURES)
print("\n=== 小众性取向特征区分度 ===")
for k in LGBT_FEATURES:
    ratio = pos_l[k] / normal_l[k] if normal_l[k] > 0 else float('inf')
    print(f"  {k}: 阳性={pos_l[k]:.5f} 正常={normal_l[k]:.5f} 比值={ratio:.2f}")

# ---------------- 指数计算 ----------------
XNN_W = {'男娘话题': 2.5, '稀有萌系': 3.0, '自称女性': 1.3}
LGBT_W = {'百合BL': 2.2, '同性恋话题': 1.5}

def compute_index(stats, feats, weights, pos_avg, normal_avg, uid):
    s = stats.get(uid)
    if not s or s['n'] == 0:
        return None
    ws = sum((s[k] / s['n']) * weights[k] for k in feats)
    pos_score = sum(pos_avg[k] * weights[k] for k in feats)
    normal_score = sum(normal_avg[k] * weights[k] for k in feats)
    center = (pos_score + normal_score) / 2
    width = max(pos_score - normal_score, 1e-9)
    import math
    raw = 100 * 0.5 * (1 + math.tanh((ws - center) / (width * 0.8)))
    conf = min(s['n'] / 300, 1.0)   # 样本置信度
    return round(50 + (raw - 50) * conf, 1)

# 全库计算
rows_xnn, rows_lgbt = [], []
for uid, s in user_stats.items():
    if s['n'] == 0:
        continue
    x = compute_index(user_stats, XNN_FEATURES, XNN_W, pos_avg, normal_avg, uid)
    l = compute_index(user_stats, LGBT_FEATURES, LGBT_W, pos_l, normal_l, uid)
    if x is not None:
        rows_xnn.append((uid, s['n'], x))
    if l is not None:
        rows_lgbt.append((uid, s['n'], l))

rows_xnn.sort(key=lambda r: -r[2])
rows_lgbt.sort(key=lambda r: -r[2])

with open('outputs/xnn_index.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['QQ号', '消息数', 'XNN男娘指数'])
    for uid, n, x in rows_xnn:
        w.writerow([uid, n, x])
with open('outputs/lgbt_index.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['QQ号', '消息数', 'LGBT小众性取向指数'])
    for uid, n, l in rows_lgbt:
        w.writerow([uid, n, l])

print(f"\n[完成] outputs/xnn_index.csv（{len(rows_xnn)} 人）")
print(f"[完成] outputs/lgbt_index.csv（{len(rows_lgbt)} 人）")

print("\n=== 真实阳性 XNN 排名 ===")
for uid, n, x in rows_xnn:
    if uid in pos_users:
        print(f"  {uid} n={n} XNN={x}")
print("\n=== 真实阳性 LGBT 排名 ===")
for uid, n, l in rows_lgbt:
    if uid in pos_users:
        print(f"  {uid} n={n} LGBT={l}")

conn.close()
