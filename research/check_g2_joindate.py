# -*- coding: utf-8 -*-
"""check_g2_joindate.py — 群2 最早消息 + 系统消息（入群通知）"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 群2 最早 10 条消息 ===')
for r in conn.execute("""
    SELECT time, user_id, nickname, text, source FROM messages 
    WHERE scene='group' AND peer_id=762673304 ORDER BY time ASC LIMIT 10"""):
    print(f'  {datetime.fromtimestamp(r["time"], cst)} | {r["user_id"]} | {r["nickname"]} | {r["text"][:50]} | {r["source"]}')

print('\n=== 群2 系统消息（raw_json 含 grayTip/系统） ===')
for r in conn.execute("""
    SELECT time, raw_json FROM messages 
    WHERE scene='group' AND peer_id=762673304 AND raw_json LIKE '%grayTip%'
    ORDER BY time ASC LIMIT 10"""):
    try:
        j = json.loads(r['raw_json'])
        tip = ''
        for seg in (j.get('message') or []):
            d = seg.get('data') or {}
            tip = d.get('tip_text') or d.get('text') or json.dumps(d, ensure_ascii=False)[:80]
            break
    except Exception as e:
        tip = f'(解析失败 {e})'
    print(f'  {datetime.fromtimestamp(r["time"], cst)} | {tip}')

print('\n=== 群2 最早消息的 raw_json 抽查（前2条） ===')
for r in conn.execute("""
    SELECT time, raw_json FROM messages 
    WHERE scene='group' AND peer_id=762673304 ORDER BY time ASC LIMIT 2"""):
    print(f'--- {datetime.fromtimestamp(r["time"], cst)} ---')
    print((r['raw_json'] or '')[:600])
conn.close()
