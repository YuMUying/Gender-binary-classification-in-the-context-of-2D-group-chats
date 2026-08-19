# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
for r in conn.execute("SELECT peer_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE scene='group' GROUP BY peer_id"):
    print(r['peer_id'], r['c'],
          datetime.fromtimestamp(r['mn'], cst) if r['mn'] else None,
          datetime.fromtimestamp(r['mx'], cst) if r['mx'] else None)
conn.close()
