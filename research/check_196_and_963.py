# -*- coding: utf-8 -*-
"""check_196_and_963.py — 验证 1965417382 入库 + 找 963653008 记录"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 1965417382 私聊消息 ===')
for r in conn.execute("SELECT time, user_id, text FROM messages WHERE scene='private' AND (user_id=1965417382 OR peer_id=1965417382) ORDER BY time"):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | {r["user_id"]} | {r["text"][:50]}')

print('\n=== 963653008 相关消息（任意来源）===')
for r in conn.execute("""
    SELECT scene, source, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages 
    WHERE user_id=963653008 GROUP BY scene, source"""):
    print(f'  scene={r["scene"]} source={r["source"]}: {r["c"]} 条 | {r["mn"]}~{r["mx"]}')

print('\n=== 2633083674 的 forwards 中 963653008 出现情况 ===')
import json
rows = conn.execute("SELECT content_raw FROM forwards WHERE envelope_user=2633083674").fetchall()
n963 = 0
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            if str(m.get('user_id')) == '963653008':
                n963 += 1
    except Exception:
        pass
print(f'forwards 内容中 user_id=963653008 的消息: {n963} 条')

# 占位符里的 963653008（sender.nickname=肖月子洋？）
n963b = 0
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            s = m.get('sender') or {}
            if s.get('nickname') == '肖月子洋' or s.get('user_id') == '963653008':
                n963b += 1
    except Exception:
        pass
print(f'sender 为肖月子洋/963653008 的消息: {n963b} 条')
conn.close()
