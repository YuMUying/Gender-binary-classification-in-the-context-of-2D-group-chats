# -*- coding: utf-8 -*-
"""find_happy.py — 从 HAPPY 窗口信封提取真实参与者 QQ 号"""
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

HAPPY_START = 1786937400   # 8-17 11:30 +08
HAPPY_END = 1786940100     # 8-17 12:15 +08

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards 
    WHERE envelope_user=2633083674 ORDER BY envelope_time""").fetchall()

happy_rows = [r for r in rows if r['envelope_time'] and HAPPY_START <= r['envelope_time'] <= HAPPY_END]
other_rows = [r for r in rows if not (r['envelope_time'] and HAPPY_START <= r['envelope_time'] <= HAPPY_END)]
print(f'HAPPY 窗口信封: {len(happy_rows)} | 其他信封: {len(other_rows)}')

# HAPPY 窗口信封里的参与者统计
happy_uids = Counter()
happy_nicks = {}
for r in happy_rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            uid = m.get('user_id')
            nick = (m.get('sender') or {}).get('nickname') or m.get('nickname') or ''
            if uid is not None:
                happy_uids[uid] += 1
                if nick:
                    happy_nicks[uid] = nick
    except Exception:
        pass
print('\n=== HAPPY 窗口信封参与者 ===')
for uid, c in happy_uids.most_common():
    print(f'  {uid} ({happy_nicks.get(uid, "?")}): {c} 条')

# 其他窗口信封里的参与者统计（对比）
other_uids = Counter()
for r in other_rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            uid = m.get('user_id')
            if uid is not None:
                other_uids[uid] += 1
    except Exception:
        pass
print('\n=== 其他窗口信封参与者 ===')
for uid, c in other_uids.most_common():
    print(f'  {uid}: {c} 条')
conn.close()
