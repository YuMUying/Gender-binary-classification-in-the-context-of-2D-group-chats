# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
r = conn.execute("SELECT MIN(time), MAX(time), COUNT(*) FROM messages WHERE scene='group' AND peer_id=826904606 AND time>0").fetchone()
print(f'群1 范围: {datetime.fromtimestamp(r[0], cst)} ~ {datetime.fromtimestamp(r[1], cst)} | 消息数: {r[2]}')
r2 = conn.execute("SELECT COUNT(*) FROM messages WHERE source='qce'").fetchone()
print(f'qce 来源消息: {r2[0]}')
print('--- 各月分布 ---')
for row in conn.execute("SELECT strftime('%Y-%m', time, 'unixepoch', '+8 hours') m, COUNT(*) FROM messages WHERE scene='group' AND peer_id=826904606 GROUP BY m ORDER BY m"):
    print(row[0], row[1])
print('--- 6-09~6-16 每日 ---')
for row in conn.execute("SELECT strftime('%Y-%m-%d', time, 'unixepoch', '+8 hours') d, COUNT(*) FROM messages WHERE scene='group' AND peer_id=826904606 AND time BETWEEN 1781280000 AND 1781798400 GROUP BY d ORDER BY d"):
    print(row[0], row[1])
conn.close()
