# -*- coding: utf-8 -*-
"""check_xingling.py — 星崤月凛 8-18 19:27 上下文"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 找到 8-18 19:27 附近的该用户消息
# 8-18 19:27 +08 = 1787052420 附近
target_lo = 1787052420
target_hi = 1787052600
print('=== 星崤月凛 19:27 前后消息 ===')
for r in conn.execute("""
    SELECT time, peer_id, text FROM messages 
    WHERE user_id=3189511804 AND time BETWEEN ? AND ?
    ORDER BY time""", (target_lo - 120, target_hi + 120)):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%H:%M:%S")} | 群{r["peer_id"]} | {r["text"][:80]}')

# 找 "男神跳高" 关键词消息（全局）
print('\n=== "男神跳高" 关键词消息 ===')
for r in conn.execute("""
    SELECT time, peer_id, user_id, text FROM messages 
    WHERE text LIKE '%男神跳高%' ORDER BY time"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | 群{r["peer_id"]} | {r["user_id"]} | {r["text"][:100]}')

# 该群 19:20-19:35 全部消息（上下文）
print('\n=== 目标消息所在群 19:20-19:35 全部消息 ===')
rows = conn.execute("""
    SELECT time, peer_id, user_id, nickname, text FROM messages 
    WHERE time BETWEEN ? AND ? AND text != '' AND LENGTH(text) > 0
    ORDER BY time""", (target_lo - 420, target_hi + 480)).fetchall()
# 找目标消息的群
target_group = None
for r in conn.execute("SELECT peer_id FROM messages WHERE user_id=3189511804 AND time BETWEEN ? AND ? LIMIT 1", (target_lo, target_hi)):
    target_group = r['peer_id']
print(f'目标群: {target_group}')
for r in rows:
    if r['peer_id'] != target_group:
        continue
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%H:%M:%S")} | {r["user_id"]} | {str(r["nickname"] or "")[:10]} | {r["text"][:80]}')
conn.close()
