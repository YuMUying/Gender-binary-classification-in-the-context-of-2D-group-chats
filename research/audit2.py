# -*- coding: utf-8 -*-
"""audit2.py — messages 表 forward 消息按 user_id/peer_id 分布"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== source=forward 按 user_id ===')
for r in conn.execute("SELECT user_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE source='forward' GROUP BY user_id ORDER BY c DESC"):
    print(f'  user={r["user_id"]}: {r["c"]} 条 | {r["mn"]} ~ {r["mx"]}')

print('\n=== source=forward 按 peer_id ===')
for r in conn.execute("SELECT peer_id, COUNT(*) c FROM messages WHERE source='forward' GROUP BY peer_id ORDER BY c DESC"):
    print(f'  peer={r["peer_id"]}: {r["c"]} 条')

print('\n=== source=forward 且 peer_id=1094950020 的 user_id 分布 ===')
for r in conn.execute("SELECT user_id, COUNT(*) c FROM messages WHERE source='forward' AND peer_id=1094950020 GROUP BY user_id"):
    print(f'  user={r["user_id"]}: {r["c"]} 条')

print('\n=== user_id=1046636617 的分布（scene/source）===')
for r in conn.execute("SELECT scene, source, COUNT(*) c FROM messages WHERE user_id=1046636617 GROUP BY scene, source"):
    print(f'  scene={r["scene"]} source={r["source"]}: {r["c"]} 条')

print('\n=== user_id=1094950020 剩余 ===')
r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=1094950020").fetchone()
print(f'  {r[0]} 条')
conn.close()
