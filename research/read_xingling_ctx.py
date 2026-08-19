# -*- coding: utf-8 -*-
"""read_xingling_ctx.py — 读信封上下文"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 新信封内容（18 条）===')
for r in conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-30 FROM messages WHERE source='forward')
    ORDER BY time"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M:%S")} | {r["user_id"]} | {r["text"][:80]}')
conn.close()
