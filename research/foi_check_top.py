# -*- coding: utf-8 -*-
"""foi_check_top.py — 检查高 FOI 未标注用户的实际消息（判断真伪）"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

targets = [2429967889, 1220384810, 1717582, 3541215132, 2933474490, 2957772437]
for uid in targets:
    print(f"===== UID {uid} =====")
    n = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (uid,)).fetchone()[0]
    print(f"消息数: {n}")
    for r in conn.execute("SELECT text FROM messages WHERE user_id=? AND text LIKE '%男娘%' OR user_id=? AND text LIKE '%女装%' OR user_id=? AND text LIKE '%qwq%' OR user_id=? AND text LIKE '%丝袜%' OR user_id=? AND text LIKE '%小裙子%' LIMIT 5", (uid, uid, uid, uid, uid)):
        print(f"  {r['text'][:60]}")
    print()
conn.close()
