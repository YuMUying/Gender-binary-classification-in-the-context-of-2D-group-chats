# -*- coding: utf-8 -*-
"""check_xuexue.py — 雪々(1757193004) 发言风格抽样"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
print('=== 雪々 有效文本抽样 25 条 ===')
n = 0
for r in conn.execute("""
    SELECT time, text FROM messages WHERE user_id=1757193004 
    AND LENGTH(text) >= 4 AND text NOT LIKE '[%' ORDER BY time DESC"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | {r["text"][:60]}')
    n += 1
    if n >= 25:
        break
conn.close()
