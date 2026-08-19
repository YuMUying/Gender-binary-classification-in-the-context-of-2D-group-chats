# -*- coding: utf-8 -*-
"""check_envelope.py — 查找 2633083674 信封（聊天记录）与 1.2G 视频"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 与 2633083674 相关的私聊消息（最近 20 条）===')
rows = conn.execute("""
    SELECT * FROM messages WHERE scene='private' AND (user_id=2633083674 OR peer_id=2633083674)
    ORDER BY time DESC LIMIT 20""").fetchall()
print(f'共找到 {len(rows)} 条')
for r in rows:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | user={r["user_id"]} peer={r["peer_id"]} | {r["text"][:80]} | {r["source"]}')

print('\n=== 最近 24h 所有私聊消息 ===')
from time import time
now = int(time())
rows2 = conn.execute("SELECT * FROM messages WHERE scene='private' AND time > ? ORDER BY time DESC LIMIT 30", (now - 86400,)).fetchall()
print(f'共 {len(rows2)} 条')
for r in rows2:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | user={r["user_id"]} peer={r["peer_id"]} | {r["text"][:80]}')

print('\n=== 转发记录 (forwards) 最近 10 条 ===')
try:
    for r in conn.execute("SELECT * FROM forwards ORDER BY fetched_at DESC LIMIT 10"):
        d = dict(r)
        t = datetime.fromtimestamp(d.get('fetched_at') or 0, cst)
        print(f'  {t} | forward={str(d.get("forward_id"))[:25]} | user={d.get("envelope_user")} | {str(d.get("content_raw"))[:60]}')
except Exception as e:
    print('forwards 查询失败:', e)

print('\n=== media_files 大文件（>100MB）===\n')
try:
    for r in conn.execute("""
        SELECT * FROM media_files WHERE file_size > 100*1024*1024 ORDER BY file_size DESC LIMIT 10"""):
        d = dict(r)
        print(f'  {d.get("media_type")} | {d.get("file_size", 0)/1024/1024:.0f}MB | {str(d.get("url"))[:50]} | {str(d.get("file_id"))[:30]} | msg={d.get("message_id")}')
except Exception as e:
    print('media_files 查询失败:', e)
conn.close()
