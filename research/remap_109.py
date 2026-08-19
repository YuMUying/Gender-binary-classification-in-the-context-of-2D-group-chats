# -*- coding: utf-8 -*-
"""remap_109.py — 1094950020(占位符) → 1046636617(合疯)"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

lbl = conn.execute('SELECT * FROM speaker_labels WHERE user_id=1094950020').fetchone()
print('1094950020 标注:', dict(lbl) if lbl else None)

cur = conn.execute("""
    UPDATE messages SET user_id=1046636617, nickname='合疯'
    WHERE user_id=1094950020 AND scene='private' AND source='forward'""")
print(f'映射消息数: {cur.rowcount}')
conn.commit()

r = conn.execute('SELECT COUNT(*) FROM messages WHERE user_id=1094950020').fetchone()
r2 = conn.execute('SELECT COUNT(*) FROM messages WHERE user_id=1046636617').fetchone()
r3 = conn.execute("SELECT MAX(nickname) FROM messages WHERE user_id=1046636617").fetchone()
print(f'1094950020 剩余: {r[0]} | 1046636617 总数: {r2[0]} | 昵称: {r3[0]}')
conn.close()
