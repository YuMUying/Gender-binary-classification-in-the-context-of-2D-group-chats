# -*- coding: utf-8 -*-
"""split_by_window.py — 按信封时间窗口精确拆分：8-17→HAPPY(1717582)，8-19→合疯(1046636617)"""
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 8-17 24:00 边界（UTC+8）
AUG17_END = 1787011200   # 2026-08-17 24:00 +08 = 8-18 00:00
AUG19_START = 1787068800 # 2026-08-19 00:00 +08

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards 
    WHERE envelope_user=2633083674 ORDER BY envelope_time""").fetchall()

happy_ids = set()    # 8-17 信封中 1094950020 消息 id → HAPPY
hefeng_ids = set()   # 8-19 信封中 1094950020 消息 id → 合疯
other_ids = set()    # 其他（8-11/8-14 等）→ 保持现状

for r in rows:
    et = r['envelope_time'] or 0
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            if str(m.get('user_id')) != '1094950020':
                continue
            mid = m.get('real_id') or m.get('message_id')
            if mid is None:
                continue
            if et < AUG17_END:
                happy_ids.add(mid)
            elif et >= AUG19_START:
                hefeng_ids.add(mid)
            else:
                other_ids.add(mid)
    except Exception:
        pass

print(f'HAPPY(8-17) 信封消息 id: {len(happy_ids)}')
print(f'合疯(8-19) 信封消息 id: {len(hefeng_ids)}')
print(f'其他信封消息 id: {len(other_ids)}')
print(f'HAPPY∩合疯 重叠: {len(happy_ids & hefeng_ids)}')

# 当前 messages 表里这些 id 的归属
for label, ids in (('HAPPY', happy_ids), ('合疯', hefeng_ids)):
    if not ids:
        continue
    lst = list(ids)
    dist = Counter()
    for i in range(0, len(lst), 400):
        chunk = lst[i:i+400]
        ph = ','.join('?' for _ in chunk)
        for r in conn.execute(f"SELECT user_id, COUNT(*) c FROM messages WHERE source='forward' AND message_id IN ({ph}) GROUP BY user_id", chunk):
            dist[r['user_id']] += r['c']
    print(f'{label} id 当前在 messages 的归属: {dict(dist)}')

# 保存 id 集合供后续 UPDATE
with open('research/happy_ids.txt', 'w') as f:
    for i in sorted(happy_ids):
        f.write(str(i) + '\n')
with open('research/hefeng_ids.txt', 'w') as f:
    for i in sorted(hefeng_ids):
        f.write(str(i) + '\n')
print('\nid 集合已保存到 research/happy_ids.txt / hefeng_ids.txt')
conn.close()
