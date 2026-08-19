# -*- coding: utf-8 -*-
"""map_bjg.py — 8-19 新信封（2633083674↔白驹过隙）占位符映射"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 这批信封：8-18 17:42 + 8-19 10:01~10:05（envelope_time）
WIN_START = 1787031600   # 8-18 17:00
WIN_END = 1787088000     # 8-19 11:00

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards 
    WHERE envelope_user=2633083674 AND envelope_time BETWEEN ? AND ?""", (WIN_START, WIN_END)).fetchall()
print(f'窗口内信封: {len(rows)} 个')
for r in rows:
    t = datetime.fromtimestamp(r['envelope_time'], cst)
    print(f'  fwd={str(r["forward_id"])[:24]} | {t.strftime("%m-%d %H:%M")}')

# 提取 1094950020 消息 id
ids = set()
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            if str(m.get('user_id')) != '1094950020':
                continue
            mid = m.get('real_id') or m.get('message_id')
            if mid is not None:
                ids.add(mid)
    except Exception:
        pass
print(f'1094950020 消息 id: {len(ids)}')

# 当前归属
dist = {}
for i in range(0, len(ids), 400):
    chunk = list(ids)[i:i+400]
    ph = ','.join('?' for _ in chunk)
    for r in conn.execute(f"SELECT user_id, COUNT(*) c FROM messages WHERE source='forward' AND message_id IN ({ph}) GROUP BY user_id", chunk):
        dist[r['user_id']] = dist.get(r['user_id'], 0) + r['c']
print('当前归属:', dist)

# 映射：user_id=1094950020 或 1046636617（上次误映射）→ 3615168664
total = 0
for i in range(0, len(ids), 400):
    chunk = list(ids)[i:i+400]
    ph = ','.join('?' for _ in chunk)
    cur = conn.execute(f"""
        UPDATE messages SET user_id=3615168664, nickname='白驹过隙'
        WHERE source='forward' AND user_id IN (1094950020, 1046636617) AND message_id IN ({ph})""", chunk)
    total += cur.rowcount
conn.commit()
print(f'\n已映射 {total} 条 → 3615168664(白驹过隙)')

# 验证
r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=3615168664").fetchone()
print(f'白驹过隙总消息: {r[0]}')
conn.close()
