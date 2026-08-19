# -*- coding: utf-8 -*-
"""verify_ctx_sender.py — 核对信封每条消息的真实发送者"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 新信封 18 条消息的 sender 详情 ===')
rows = conn.execute("""
    SELECT time, user_id, text, raw_json FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-30 FROM messages WHERE source='forward')
    ORDER BY time""").fetchall()
seen = set()
for r in rows:
    key = (r['time'], r['text'][:30])
    if key in seen:
        continue
    seen.add(key)
    j = json.loads(r['raw_json'] or '{}')
    sender = j.get('sender') or {}
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M:%S")} | user_id={r["user_id"]} sender={sender.get("user_id")} nick={sender.get("nickname")} | {r["text"][:50]}')
conn.close()
