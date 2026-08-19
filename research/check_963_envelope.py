# -*- coding: utf-8 -*-
"""check_963_envelope.py — 新信封参与者 + 占位符"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 新入库 forward 消息参与者 ===')
rows = conn.execute("""
    SELECT user_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-1300 FROM messages WHERE source='forward')
    GROUP BY user_id ORDER BY c DESC""").fetchall()
for r in rows:
    t0 = datetime.fromtimestamp(r['mn'], cst)
    t1 = datetime.fromtimestamp(r['mx'], cst)
    print(f'  {r["user_id"]}: {r["c"]} 条 | {t0.strftime("%m-%d")}~{t1.strftime("%m-%d")}')

print('\n=== sender 昵称分布（新信封）===')
nick_dist = {}
rows2 = conn.execute("""
    SELECT raw_json FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-1300 FROM messages WHERE source='forward')""").fetchall()
for r in rows2:
    try:
        j = json.loads(r['raw_json'])
        s = j.get('sender') or {}
        key = f"{s.get('user_id')}|{s.get('nickname')}"
        nick_dist[key] = nick_dist.get(key, 0) + 1
    except Exception:
        pass
for k, c in sorted(nick_dist.items(), key=lambda x: -x[1])[:12]:
    print(f'  {c:5d} | {k}')

print('\n=== 文本抽样 15 条 ===')
seen = set()
n = 0
for r in conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-1300 FROM messages WHERE source='forward')
      AND text NOT LIKE '[%' AND LENGTH(text) > 2 ORDER BY time"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | {r["user_id"]} | {r["text"][:50]}')
    n += 1
    if n >= 15:
        break
conn.close()
