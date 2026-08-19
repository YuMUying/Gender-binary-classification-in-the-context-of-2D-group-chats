# -*- coding: utf-8 -*-
"""评估 FOI 训练数据规模"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

pos = set()
for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != '' AND gender='male'"):
    pos.add(r['user_id'])
neg = set(r['user_id'] for r in conn.execute(
    "SELECT user_id FROM speaker_labels WHERE gender='male'")) - pos

def msg_stats(uids):
    total, per = 0, {}
    for uid in uids:
        n = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND scene IN ('group','private') AND LENGTH(text)>=2", (uid,)).fetchone()[0]
        per[uid] = n
        total += n
    return total, per

pt, pp = msg_stats(pos)
nt, np_ = msg_stats(neg)
print(f"阳性(orientation男): {len(pos)} 人, 总消息 {pt}")
for uid in sorted(pp, key=lambda x: -pp[x]):
    print(f"  {uid}: {pp[uid]}")
print(f"\n阴性(正常男): {len(neg)} 人, 总消息 {nt}")
print(f"  消息>500: {sum(1 for v in np_.values() if v>500)} 人")
print(f"  消息>200: {sum(1 for v in np_.values() if v>200)} 人")

# 每用户消息数分布（阴性）
import statistics
vals = sorted(np_.values(), reverse=True)
print(f"\n阴性消息数分布 TOP20: {vals[:20]}")
conn.close()
