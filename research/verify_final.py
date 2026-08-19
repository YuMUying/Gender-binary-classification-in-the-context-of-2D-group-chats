# -*- coding: utf-8 -*-
"""verify_final.py — 最终验证"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 相关用户最终状态 ===')
for uid in (1717582, 1046636617, 3541215132, 1094950020):
    r = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=?", (uid,)).fetchone()
    lbl = conn.execute("SELECT gender, nickname FROM speaker_labels WHERE user_id=?", (uid,)).fetchone()
    print(f'  user={uid}: 消息 {r["c"]} 条 | 标注: {dict(lbl) if lbl else "无"}')

print('\n=== 合疯消息构成 ===')
for r in conn.execute("SELECT scene, source, COUNT(*) c FROM messages WHERE user_id=1046636617 GROUP BY scene, source"):
    print(f'  scene={r["scene"]} source={r["source"]}: {r["c"]} 条')

print('\n=== HAPPY 消息时间范围 ===')
r = conn.execute("SELECT MIN(time), MAX(time) FROM messages WHERE user_id=1717582").fetchone()
from datetime import datetime, timezone, timedelta
cst = timezone(timedelta(hours=8))
print(f'  {datetime.fromtimestamp(r[0], cst)} ~ {datetime.fromtimestamp(r[1], cst)}')
conn.close()
