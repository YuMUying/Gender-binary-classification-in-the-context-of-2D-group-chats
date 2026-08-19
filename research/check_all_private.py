# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
total = conn.execute("SELECT COUNT(*) FROM messages WHERE scene='private'").fetchone()[0]
print(f'DB 私聊总数(入库): {total}')
rows = conn.execute("SELECT * FROM messages WHERE scene='private' ORDER BY time DESC LIMIT 20").fetchall()
for r in rows:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | user={r["user_id"]} peer={r["peer_id"]} | {r["text"][:50]} | {r["source"]}')
conn.close()
