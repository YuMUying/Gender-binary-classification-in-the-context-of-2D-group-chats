# -*- coding: utf-8 -*-
"""problem_users.py — 列出验证集错误用户与复核候选（含昵称/群名片/打分）"""
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

uids = [439161815, 1591798171, 1757193004, 348105425, 1395833200]

# v7 打分
scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

for uid in uids:
    nick = conn.execute("SELECT nickname FROM user_profiles WHERE user_id=?", (uid,)).fetchone()
    nickname = nick['nickname'] if nick and nick['nickname'] else ''
    cards = []
    for g in (826904606, 762673304):
        card = conn.execute("""SELECT card FROM messages WHERE peer_id=? AND user_id=? AND card IS NOT NULL AND card != ''
                               ORDER BY time DESC LIMIT 1""", (g, uid)).fetchone()
        if card and card['card']:
            cards.append(f'群{g}: {card["card"]}')
    lab = conn.execute("SELECT gender FROM speaker_labels WHERE user_id=?", (uid,)).fetchone()
    label = lab['gender'] if lab else '?'
    s = scores.get(uid, {})
    p = float(s.get('prob_female_mean', -1)) if s else -1
    n = s.get('n_messages', '?')
    pred = s.get('predicted', '?')
    print(f'{uid} | {nickname} | {" / ".join(cards) if cards else "无群名片"} | 标注={label} | P(女)={p:.3f} | 预测={pred} | 消息数={n}')
conn.close()
