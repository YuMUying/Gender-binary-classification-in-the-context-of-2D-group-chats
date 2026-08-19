# -*- coding: utf-8 -*-
"""cleanup_109_label.py — 清理占位符 1094950020 的残留标注"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

lbl = conn.execute('SELECT * FROM speaker_labels WHERE user_id=1094950020').fetchone()
print('1094950020 当前标注:', dict(lbl) if lbl else None)

if lbl:
    conn.execute('DELETE FROM speaker_labels WHERE user_id=1094950020')
    conn.commit()
    print('已删除占位符标注')

# 验证
print('\n=== 合疯 1046636617 状态 ===')
r = conn.execute('SELECT * FROM speaker_labels WHERE user_id=1046636617').fetchone()
print('标注:', dict(r) if r else None)
r2 = conn.execute('SELECT COUNT(*) FROM messages WHERE user_id=1046636617').fetchone()
r3 = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=1046636617 AND scene='private' AND source='forward'").fetchone()
print(f'消息总数: {r2[0]} | 其中转发私聊: {r3[0]}')
conn.close()
