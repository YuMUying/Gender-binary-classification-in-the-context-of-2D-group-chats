# -*- coding: utf-8 -*-
"""emo_hypothesis.py — 验证假设：男声女气误判用户是否 emo 词频更高

分组：v10 判女但标男（误判组）/ 正确判男（普通男）/ 真实女性
指标：emo 词率（玉玉/破防/emo/好累/想死 等二次元群常用情绪词）
"""
import csv
import re
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

v10 = {}
with open('outputs/score-v10-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        v10[int(r['user_id'])] = r

# emo 词典（二次元群聊语境）
EMO = re.compile(
    r'emo|玉玉|玉玉症|破防|麻了|麻掉|绷不住|破大防|好累|好累啊|心累|累死|不想活|想死|活不下去|'
    r'孤独|寂寞|空虚|眼泪|哭了|想哭|呜呜呜|呜呜|嘤嘤|好难过|难过|悲伤|抑郁|emo了|emo中|'
    r'小丑|小丑竟是我|寄了|完蛋|废了|好烦|烦死|烦躁|emo时刻|深夜emo|玉玉了|快玉玉了')

# 分组
groups = {'误判男(判女实男)': [], '普通男': [], '真实女': []}
for uid, g in labels.items():
    sc = v10.get(uid)
    if not sc:
        continue
    if g == 'male':
        if sc['predicted'] == 'female':
            groups['误判男(判女实男)'].append(uid)
        else:
            groups['普通男'].append(uid)
    else:
        groups['真实女'].append(uid)

# 统计 emo 词率
print('=== emo 词率对比 ===')
for gname, uids in groups.items():
    total = 0
    emo = 0
    per_user = []
    for uid in uids:
        n = 0
        e = 0
        for r in conn.execute("SELECT text FROM messages WHERE user_id=?", (uid,)):
            t = r['text'] or ''
            if len(t) >= 4 and not t.startswith('['):
                n += 1
                if EMO.search(t):
                    e += 1
        if n >= 20:
            per_user.append(e / n)
            total += n
            emo += e
    if per_user:
        import statistics
        print(f'  {gname} (n={len(per_user)}): 消息级 emo率={emo/max(total,1):.4f} | 人均 emo率均值={statistics.mean(per_user):.4f} 中位={statistics.median(per_user):.4f}')

# 误判组逐用户
print('\n=== 误判组逐用户 emo 率 ===')
for uid in groups['误判男(判女实男)']:
    n = 0
    e = 0
    for r in conn.execute("SELECT text FROM messages WHERE user_id=?", (uid,)):
        t = r['text'] or ''
        if len(t) >= 4 and not t.startswith('['):
            n += 1
            if EMO.search(t):
                e += 1
    nick = conn.execute("SELECT MAX(nickname) n FROM messages WHERE user_id=?", (uid,)).fetchone()['n']
    if n >= 20:
        print(f'  {uid} | {str(nick)[:10]} | emo率={e/n:.4f} ({e}/{n})')
conn.close()
