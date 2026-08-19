# -*- coding: utf-8 -*-
"""monthly_dist.py — 1094950020 forward 消息月份分布 + 新批样本"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))

rows = conn.execute("""
    SELECT time, text FROM messages WHERE user_id=1094950020 AND source='forward'
    ORDER BY time""").fetchall()
print(f'共 {len(rows)} 条')
from collections import Counter
months = Counter(datetime.fromtimestamp(r['time'], cst).strftime('%Y-%m') for r in rows)
for m in sorted(months):
    print(f'  {m}: {months[m]} 条')

print('\n=== 6月以后的样本（新批内容）===')
shown = 0
for r in rows:
    if r['time'] >= datetime(2026, 6, 17, tzinfo=cst).timestamp():
        t = datetime.fromtimestamp(r['time'], cst).strftime('%m-%d %H:%M')
        print(f'  [{t}] {r["text"][:50]!r}')
        shown += 1
        if shown >= 10:
            break
conn.close()
