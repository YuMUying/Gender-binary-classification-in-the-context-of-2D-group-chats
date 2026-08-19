# -*- coding: utf-8 -*-
"""infer_one.py — 单用户多通道推理汇总"""
import csv
import json
import sqlite3
import sys

uid = int(sys.argv[1])

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print(f'===== 用户 {uid} =====')
nick = conn.execute("SELECT nickname, first_seen, last_seen, message_count FROM user_profiles WHERE user_id=?", (uid,)).fetchone()
if nick:
    print(f'昵称: {nick["nickname"]} | 库内消息: {nick["message_count"]}')
for g in (826904606, 762673304):
    card = conn.execute("SELECT card FROM messages WHERE peer_id=? AND user_id=? AND card IS NOT NULL AND card!='' ORDER BY time DESC LIMIT 1", (g, uid)).fetchone()
    if card:
        print(f'群{g} 群名片: {card["card"]}')
    cnt = conn.execute("SELECT COUNT(*) c FROM messages WHERE peer_id=? AND user_id=?", (g, uid)).fetchone()['c']
    if cnt:
        print(f'群{g} 消息数: {cnt}')
lab = conn.execute("SELECT * FROM speaker_labels WHERE user_id=?", (uid,)).fetchone()
print('人工标注:', dict(lab) if lab else '无')
net = conn.execute("SELECT network_gender, source FROM profile_genders WHERE user_id=?", (uid,)).fetchone()
print('网络性别:', dict(net) if net else '无')
conn.close()

# v7 文本打分
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if int(r['user_id']) == uid:
            print(f'\n[文本 v7] P(女)均值={r["prob_female_mean"]} 中位={r["prob_female_median"]} std={r["prob_female_std"]} 条数={r["n_messages"]} 预测={r["predicted"]} 置信度={r["confidence"]} (阈值 {r["threshold"]})')

# 涩情特征（本地模型）
with open('outputs/erotic_features_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if int(r['user_id']) == uid:
            print(f'[涩情] 消息={r["total"]} 参与={r["ero_any"]} 最大级={r["ero_max"]} 占比={r["ero_ratio"]} (1级{r["lvl1"]}/2级{r["lvl2"]}/3级{r["lvl3"]})')

# 自述
found = False
for l in open('research/gender_declare_labels.jsonl', encoding='utf-8'):
    l = l.strip()
    if not l:
        continue
    d = json.loads(l)
    if d['user_id'] == uid:
        found = True
        print(f'[自述] {d["declared"]} 事实={d["factual"]} conf={d["conf"]} | {d["text"][:40]!r} | {d.get("reason","")[:40]}')
if not found:
    print('[自述] 无')

# 头像描述（仅已标注45人有）
for l in open('research/avatar_desc.jsonl', encoding='utf-8'):
    l = l.strip()
    if not l:
        continue
    d = json.loads(l)
    if int(d['uin']) == uid:
        dd = d.get('desc') or {}
        print(f'[头像] {dd.get("overall","")[:60]} | {dd.get("style","")[:40]}')
        break
