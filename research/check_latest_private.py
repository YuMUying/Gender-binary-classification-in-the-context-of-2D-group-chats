# -*- coding: utf-8 -*-
"""check_latest_private.py — 检查 8-19 01:00 后的私聊消息"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 8-19 00:00 之后所有消息（任何 scene）
print('=== 8-19 00:00 之后的所有消息 ===')
for r in conn.execute("SELECT * FROM messages WHERE time > 1787068800 ORDER BY time DESC LIMIT 20"):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | scene={r["scene"]} peer={r["peer_id"]} user={r["user_id"]} | {r["text"][:60]} | {r["source"]}')

# forwards 最新
print('\n=== forwards 表最新 10 条 ===')
for r in conn.execute("SELECT * FROM forwards ORDER BY fetched_at DESC LIMIT 10"):
    d = dict(r)
    t = datetime.fromtimestamp(d.get('fetched_at') or 0, cst)
    print(f'  {t} | fwd={str(d.get("forward_id"))[:22]} | user={d.get("envelope_user")} | {str(d.get("content_raw"))[:50]}')

# 私聊全部（含 8-17 之后所有）
print('\n=== 私聊消息 8-17 18:00 之后 ===')
for r in conn.execute("SELECT * FROM messages WHERE scene='private' AND time > 1787029200 ORDER BY time DESC LIMIT 30"):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | user={r["user_id"]} peer={r["peer_id"]} | {r["text"][:70]} | {r["source"]}')
conn.close()
