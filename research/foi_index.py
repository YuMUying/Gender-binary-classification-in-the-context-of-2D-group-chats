# -*- coding: utf-8 -*-
"""foi_index.py — FOI（Femboy Orientation Index / 男娘综合指数）v3

v3 定稿：
  - 特征收敛为词级高区分度信号（基于 foi_word_analysis.py 实测比值）：
      男娘话题: 男娘/女装/伪娘/药娘/丝袜/小裙子/jk/lo裙/白丝/黑丝/穿裙/女装大佬
      稀有萌系: qwq/QAQ/TAT/叭/诶嘿/Orz/OvO/OwO
      百合BL:  百合/gl向/耽美/同人女/嗑cp/磕cp
  - 移除宽泛萌系词（喵/呜/捏 在二次元群人人用，无区分度）
  - 权重 = 词级区分度（阳性/正常男 每千条比值）
  - 置信度惩罚：样本 < CONF_FULL 条时指数向 50 收缩
  - 指数定位：男娘相关信号强度（0-100，供人工参考，非身份判定）

用法: python research/foi_index.py
输出: outputs/foi_index.csv + 追加 标定参考包.csv/.md
"""
import csv
import math
import re
import sqlite3

# 词级模式 → 权重（区分度实测比值圆整）
FEATURES = {
    '男娘话题': (re.compile(r'(男娘|女装|伪娘|药娘|丝袜|小裙子|jk裙|lo裙|白丝|黑丝|穿裙|女装大佬|女装吧|男娘吧)'), 2.5),
    '稀有萌系': (re.compile(r'(qwq|QAQ|TAT|Orz|OvO|OwO|>_<|叭|诶嘿|嘤嘤|呜呜)'), 3.0),
    '百合BL': (re.compile(r'(百合|gl向|耽美|同人女|嗑cp|磕cp|bl向)'), 2.2),
    '自称女性': (re.compile(r'(人家|咱家|本小姐|伦家|奴家|妾身|本宫|小妹)'), 1.3),
}

CONF_FULL = 300  # 样本量充分阈值

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

pos_users = set()
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    if r['gender'] == 'male':
        pos_users.add(r['user_id'])
normal_male = set(r['user_id'] for r in conn.execute(
    "SELECT user_id FROM speaker_labels WHERE gender='male'")) - pos_users

def collect_stats(uids):
    result = {}
    for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
        uid = r['user_id']
        if uid not in uids:
            continue
        s = result.setdefault(uid, {'n': 0, **{k: 0 for k in FEATURES}})
        s['n'] += 1
        t = r['text'] or ''
        for k, (pat, w) in FEATURES.items():
            if pat.search(t):
                s[k] += 1
    return result

pos_stats = collect_stats(pos_users)
normal_stats = collect_stats(normal_male)

def avg_rates(stats):
    sums = {k: 0.0 for k in FEATURES}
    cnt = 0
    for uid, s in stats.items():
        if s['n'] == 0:
            continue
        cnt += 1
        for k in FEATURES:
            sums[k] += s[k] / s['n']
    for k in FEATURES:
        sums[k] /= max(cnt, 1)
    return sums

pos_avg = avg_rates(pos_stats)
normal_avg = avg_rates(normal_stats)
pos_score = sum(pos_avg[k] * FEATURES[k][1] for k in FEATURES)
normal_score = sum(normal_avg[k] * FEATURES[k][1] for k in FEATURES)
print(f"阳性加权人均分={pos_score:.5f}  正常男={normal_score:.5f}  分离度={pos_score/max(normal_score,1e-9):.2f}x")

CENTER = (pos_score + normal_score) / 2
WIDTH = max(pos_score - normal_score, 1e-9)

def foi(ws, n):
    conf = min(n / CONF_FULL, 1.0)
    raw = 100 * 0.5 * (1 + math.tanh((ws - CENTER) / (WIDTH * 0.8)))
    return round(50 + (raw - 50) * conf, 1)

all_stats = collect_stats(set(r['user_id'] for r in conn.execute("SELECT user_id FROM messages")))
rows_out = []
for uid, s in all_stats.items():
    if s['n'] == 0:
        continue
    ws = sum((s[k] / s['n']) * FEATURES[k][1] for k in FEATURES)
    rows_out.append((uid, s['n'], ws, foi(ws, s['n'])))

print("\n=== 标签用户 FOI（v3） ===")
print(f"{'UID':<12} {'标签':<8} {'消息':<6} {'FOI'}")
for uid, info in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    row = next((x for x in rows_out if x[0] == uid), None)
    if row:
        print(f"{uid:<12} {info:<8} {row[1]:<6} {row[3]}")
    else:
        print(f"{uid:<12} {info:<8} {'-':<6} (无消息)")

pos_fois = [f for uid, n, ws, f in rows_out if uid in pos_users]
normal_fois = [f for uid, n, ws, f in rows_out if uid in normal_male]
if pos_fois and normal_fois:
    print(f"\n阳性 FOI: 均值={sum(pos_fois)/len(pos_fois):.1f} 范围=[{min(pos_fois)},{max(pos_fois)}]")
    print(f"正常男 FOI: 均值={sum(normal_fois)/len(normal_fois):.1f} 范围=[{min(normal_fois)},{max(normal_fois)}]")

print("\n=== 全库 TOP 15（带样本量） ===")
for uid, n, ws, f in sorted(rows_out, key=lambda x: -x[3])[:15]:
    print(f"  {uid} 消息{n} FOI={f}")

with open('outputs/foi_index.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['QQ号', '消息数', '加权分', 'FOI指数'])
    for uid, n, ws, f in sorted(rows_out, key=lambda x: -x[3]):
        w.writerow([uid, n, f'{ws:.5f}', f])
print(f"\n[完成] outputs/foi_index.csv 已写出（{len(rows_out)} 人）")
conn.close()
