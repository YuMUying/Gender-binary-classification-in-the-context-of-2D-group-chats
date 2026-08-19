# -*- coding: utf-8 -*-
"""verify_windows_attribution.py — 各窗口信封消息 id 的当前归属"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import Counter

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT forward_id, envelope_time, content_raw FROM forwards WHERE envelope_user=2633083674 ORDER BY envelope_time").fetchall()

# 用信封时间字符串直接分组（避免时间戳换算错误）
def et_str(ts):
    return datetime.fromtimestamp(ts, cst).strftime('%Y-%m-%d %H:%M')

windows = {
    'W1_1135_1207(HAPPY)': (lambda ts: '2026-08-17' <= et_str(ts) <= '2026-08-17 12:07'),
    'W2_1208_1210(?)':      (lambda ts: '2026-08-17 12:08' <= et_str(ts) <= '2026-08-17 12:15'),
    'W3_1705_1711(Buchi)':  (lambda ts: '2026-08-17 17:00' <= et_str(ts) <= '2026-08-17 20:00'),
    'W4_2027_2030(隐世云梦)': (lambda ts: '2026-08-17 20:27' <= et_str(ts) <= '2026-08-17 21:00'),
    'W5_0819(合疯)':         (lambda ts: et_str(ts) >= '2026-08-19 00:00'),
}

win_ids = {}
for name, pred in windows.items():
    ids = set()
    for r in rows:
        if r['envelope_time'] and pred(r['envelope_time']):
            try:
                j = json.loads(r['content_raw'])
                for m in (j.get('messages') or []):
                    if str(m.get('user_id')) != '1094950020':
                        continue
                    mid = m.get('real_id') or m.get('message_id')
                    if mid is not None:
                        ids.add(mid)
            except Exception:
                pass
    win_ids[name] = ids
    print(f'{name}: {len(ids)} 个消息 id')

print('\n=== 各窗口 id 在 messages 表的 user_id 归属 ===')
for name, ids in win_ids.items():
    if not ids:
        continue
    dist = Counter()
    lst = list(ids)
    for i in range(0, len(lst), 400):
        chunk = lst[i:i+400]
        ph = ','.join('?' for _ in chunk)
        for r in conn.execute(f"SELECT user_id, COUNT(*) c FROM messages WHERE source='forward' AND message_id IN ({ph}) GROUP BY user_id", chunk):
            dist[r['user_id']] += r['c']
    print(f'  {name}: {dict(dist)}')

print('\n=== 窗口间 id 重叠 ===')
names = list(win_ids)
for i in range(len(names)):
    for j in range(i+1, len(names)):
        inter = len(win_ids[names[i]] & win_ids[names[j]])
        if inter:
            print(f'  {names[i]} ∩ {names[j]}: {inter}')
conn.close()
