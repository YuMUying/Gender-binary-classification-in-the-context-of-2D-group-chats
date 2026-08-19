# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('data/qqchat.db')
cur = conn.execute("UPDATE messages SET user_id=3615168664, nickname='白驹过隙' WHERE user_id=1094950020 AND source='forward'")
print(f'剩余占位符映射: {cur.rowcount} 条')
conn.commit()
r = conn.execute('SELECT COUNT(*) FROM messages WHERE user_id=1094950020').fetchone()
print(f'占位符剩余: {r[0]}')
conn.close()
