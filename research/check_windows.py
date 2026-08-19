# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('--- message_id 格式抽查 ---')
for r in conn.execute("SELECT message_id, typeof(message_id) t, substr(text,1,40) txt FROM messages WHERE scene='group' AND peer_id=826904606 AND message_id IS NOT NULL LIMIT 5"):
    print(dict(r))

print('--- 已知区窗口（每4000条）前5个 ---')
rows = conn.execute("SELECT time FROM messages WHERE scene='group' AND peer_id=826904606 AND time>0 ORDER BY time").fetchall()
times = [r['time'] for r in rows]
n_win = (len(times) + 3999) // 4000
print(f'总消息数: {len(times)}, 4000条/批 → {n_win} 批')
for i in range(min(5, n_win)):
    chunk = times[i*4000:(i+1)*4000]
    print(f'批{i}: {datetime.fromtimestamp(chunk[0], cst)} ~ {datetime.fromtimestamp(chunk[-1], cst)} ({len(chunk)}条, 窗口{(chunk[-1]-chunk[0])/3600:.1f}h)')
conn.close()
