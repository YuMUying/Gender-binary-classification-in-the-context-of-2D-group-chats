# -*- coding: utf-8 -*-
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']

print('=== v10-wb 标女判男 ===')
with open('outputs/score-v10-wb-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        uid = int(r['user_id'])
        if uid in labels and labels[uid] == 'female' and r['predicted'] == 'male':
            print(f"{uid} | {nick.get(uid, '?')} | P(女)={r['prob_female_mean']} | n={r['n_messages']}")

print('=== v10-wb 标男判女 ===')
with open('outputs/score-v10-wb-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        uid = int(r['user_id'])
        if uid in labels and labels[uid] == 'male' and r['predicted'] == 'female':
            print(f"{uid} | {nick.get(uid, '?')} | P(女)={r['prob_female_mean']} | n={r['n_messages']}")
conn.close()
