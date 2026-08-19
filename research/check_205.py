# -*- coding: utf-8 -*-
"""check_205.py — 窗口内 536 id 中归属 3541215132 的 205 条详情"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 重新提取窗口内 id
WIN_START = 1786937700
WIN_END = 1786939680
rows = conn.execute("SELECT forward_id, envelope_time, content_raw FROM forwards WHERE envelope_user=2633083674").fetchall()
target = [r for r in rows if r['envelope_time'] and WIN_START <= r['envelope_time'] < WIN_END]
ids = set()
for r in target:
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

# 归属 3541215132 的 id
lst = list(ids)
target_ids = []
for i in range(0, len(lst), 400):
    chunk = lst[i:i+400]
    ph = ','.join('?' for _ in chunk)
    for r in conn.execute(f"SELECT message_id FROM messages WHERE source='forward' AND user_id=3541215132 AND message_id IN ({ph})", chunk):
        target_ids.append(r['message_id'])
print(f'归属 3541215132 的消息: {len(target_ids)} 条')

# 详情
print('\n=== 抽样 15 条 ===')
for r in conn.execute("SELECT message_id, time, text, raw_json FROM messages WHERE message_id IN ({}) ORDER BY time LIMIT 15".format(','.join('?' for _ in target_ids[:200])), target_ids[:200]):
    t = datetime.fromtimestamp(r['time'], cst)
    jj = json.loads(r['raw_json'] or '{}')
    sender = (jj.get('sender') or {})
    print(f'  {t} | msg={r["message_id"]} | sender_uid={sender.get("user_id")} nick={sender.get("nickname")} | {r["text"][:40]}')

# 这些 id 是否也出现在其他（非窗口）信封的 content_raw 里
print('\n=== 这些 id 在其他信封中的出现 ===')
other_occ = Counter()
for r in rows:
    if r['envelope_time'] and WIN_START <= r['envelope_time'] < WIN_END:
        continue
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            mid = m.get('real_id') or m.get('message_id')
            if mid in target_ids:
                other_occ[(datetime.fromtimestamp(r['envelope_time'], cst).strftime('%m-%d %H:%M'), str(m.get('user_id')))] += 1
    except Exception:
        pass
for k, c in other_occ.most_common(10):
    print(f'  {k}: {c}')
conn.close()
