# -*- coding: utf-8 -*-
"""locate_xingling.py — 定位星崤月凛 8-18 消息"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 星崤月凛 8-18 全部消息（19:00-20:00）===')
for r in conn.execute("""
    SELECT time, peer_id, text FROM messages 
    WHERE user_id=3189511804 AND time BETWEEN 1787043600 AND 1787047200
    ORDER BY time"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%H:%M:%S")} | 群{r["peer_id"]} | {r["text"][:80]}')

print('\n=== 她最近 30 条消息（任意日期）===')
for r in conn.execute("""
    SELECT time, peer_id, text FROM messages 
    WHERE user_id=3189511804 AND LENGTH(text) >= 4 ORDER BY time DESC LIMIT 30"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | 群{r["peer_id"]} | {r["text"][:70]}')
conn.close()
