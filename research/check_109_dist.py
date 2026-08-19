# -*- coding: utf-8 -*-
"""check_109_dist.py — 1094950020 消息分布"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
print('=== 1094950020 消息分布（按 scene/source）===')
for r in conn.execute("""
    SELECT scene, source, COUNT(*) c, MIN(time) mn, MAX(time) mx
    FROM messages WHERE user_id=1094950020 GROUP BY scene, source"""):
    print(f'  scene={r["scene"]} source={r["source"]}: {r["c"]} 条 | {r["mn"]} ~ {r["mx"]}')

print('\n=== 是否有 live 群消息混入 ===')
for r in conn.execute("""
    SELECT COUNT(*) c FROM messages 
    WHERE user_id=1094950020 AND source IN ('live','history')"""):
    print(f'  live/history: {r["c"]} 条')
conn.close()
