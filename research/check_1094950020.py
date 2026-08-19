# -*- coding: utf-8 -*-
"""check_1094950020.py — 确认 1094950020 身份 + [文件:] 详情"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 1094950020 与 1046636617 是否同一人（群名片/昵称）===')
for uid in (1094950020, 1046636617):
    r = conn.execute("SELECT MAX(nickname) n FROM messages WHERE user_id=?", (uid,)).fetchone()
    r2 = conn.execute("SELECT card, COUNT(*) c FROM messages WHERE user_id=? AND card IS NOT NULL AND card!='' GROUP BY card ORDER BY c DESC LIMIT 3", (uid,)).fetchall()
    r3 = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f'{uid}: 昵称={r["n"]} | 总消息={r3["c"]} | 名片: {[dict(x) for x in r2]}')

print('\n=== [文件:] 消息详情（id=237650）===')
r = conn.execute("SELECT * FROM messages WHERE id=237650").fetchone()
if r:
    print(f'time={datetime.fromtimestamp(r["time"], cst)} user={r["user_id"]} text={r["text"]}')
    print('raw_json:', (r['raw_json'] or '')[:800])

print('\n=== 信封里 1094950020 的发言片段（是否像合疯）===')
for r in conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND user_id=1094950020 AND LENGTH(text) > 4
    ORDER BY id DESC LIMIT 12"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | {r["text"][:50]}')
conn.close()
