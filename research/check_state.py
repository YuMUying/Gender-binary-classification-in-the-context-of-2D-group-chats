# -*- coding: utf-8 -*-
"""check_state.py — 检查最近转发信封、Buchi 消息、私聊场景状态"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))
def fmt(t): return datetime.fromtimestamp(t, cst).strftime('%m-%d %H:%M:%S')

print('=== 最近48h 转发信封（text 含 [合并转发]）===')
rows = conn.execute("""
    SELECT id, scene, peer_id, user_id, nickname, time FROM messages
    WHERE text LIKE '%[合并转发]%' AND time >= strftime('%s','now','-48 hours')
    ORDER BY time DESC LIMIT 30""").fetchall()
print(len(rows), '个信封')
for r in rows:
    print(f'  {fmt(r["time"])} scene={r["scene"]} peer={r["peer_id"]} user={r["user_id"]} {r["nickname"]}')

print()
print('=== user_id=2956792638 的全部消息 ===')
rows = conn.execute("""
    SELECT source, scene, peer_id, nickname, COUNT(*) c, MIN(time) mn, MAX(time) mx
    FROM messages WHERE user_id=2956792638 GROUP BY source, scene, peer_id, nickname""").fetchall()
print(len(rows), '组')
for r in rows:
    print(f'  source={r["source"]} scene={r["scene"]} peer={r["peer_id"]} nick={r["nickname"]} n={r["c"]} {fmt(r["mn"])}~{fmt(r["mx"])}')

print()
print('=== 私聊场景各会话最近消息 ===')
rows = conn.execute("""
    SELECT peer_id, nickname, COUNT(*) c, MAX(time) mt FROM messages
    WHERE scene='private' GROUP BY peer_id ORDER BY mt DESC LIMIT 8""").fetchall()
for r in rows:
    print(f'  peer={r["peer_id"]} nick={r["nickname"]} n={r["c"]} last={fmt(r["mt"])}')

print()
print('=== forwards 表最近 5 条 ===')
rows = conn.execute("SELECT forward_id, envelope_user, envelope_time, fetched_at FROM forwards ORDER BY fetched_at DESC LIMIT 5").fetchall()
for r in rows:
    print(f'  fwd={str(r["forward_id"])[:24]} env_user={r["envelope_user"]} env_time={fmt(r["envelope_time"]) if r["envelope_time"] else None} fetched={fmt(r["fetched_at"])}')

print()
print('=== 总消息数 / 今日新增 ===')
print('  total:', conn.execute('SELECT COUNT(*) c FROM messages').fetchone()['c'])
print('  今日新增(本地时间):', conn.execute("SELECT COUNT(*) c FROM messages WHERE time >= strftime('%s','now','-12 hours')").fetchone()['c'])
conn.close()
