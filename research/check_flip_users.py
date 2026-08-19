# -*- coding: utf-8 -*-
"""check_flip_users.py — 翻转用户详情"""
import sqlite3
import csv

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']

# 女→男翻转
flip_users = [2026691756, 3359965313, 2124957352, 3038117065, 234300537, 2780529603, 731520043, 2213154584]
print('=== 女→男翻转用户（旧判女 → 新判男）===')
for uid in flip_users:
    print(f"  {uid} | {nick.get(uid,'?')[:12]} | 标注={labels.get(uid,'未标注')} | 样本(缺失区)=", end='')
    r = conn.execute("SELECT COUNT(*) c, SUM(CASE WHEN time<1781537480 THEN 1 ELSE 0 END) old FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f"{r['c']} (缺失区{r['old']})")

# 大幅上涨用户抽样
print('\n=== 大幅上涨用户（Δ>0.5，未标注的）===')
big = [2281047532, 3103856427, 1421971856, 2498419003, 3434568972, 3537261081, 2256125929, 2819659340, 2756308289, 1453224144, 2664463054, 2456116695]
for uid in big:
    print(f"  {uid} | {nick.get(uid,'?')[:12]} | 标注={labels.get(uid,'未标注')}")

# 女性候选 top5 详情
print('\n=== 女性候选 top5 ===')
for uid in [284256062, 3202322974, 2498419003, 3615168664, 1453224144]:
    r = conn.execute("SELECT COUNT(*) c, SUM(CASE WHEN time<1781537480 THEN 1 ELSE 0 END) old FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f"  {uid} | {nick.get(uid,'?')[:12]} | 总{r['c']}条 缺失区{r['old']}条 | 标注={labels.get(uid,'未标注')}")
conn.close()
