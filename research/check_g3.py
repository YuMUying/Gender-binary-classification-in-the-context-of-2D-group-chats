# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
r = conn.execute("SELECT COUNT(*) FROM messages WHERE scene='group' AND peer_id=723216773").fetchone()
r2 = conn.execute("SELECT MIN(time), MAX(time) FROM messages WHERE scene='group' AND peer_id=723216773").fetchone()
print(f'群3消息数: {r[0]}')
if r2[0]:
    print(f'范围: {datetime.fromtimestamp(r2[0], cst)} ~ {datetime.fromtimestamp(r2[1], cst)}')
conn.close()
