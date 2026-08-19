# -*- coding: utf-8 -*-
"""split_envelopes.py — 按信封时间区分 HAPPY 窗口 vs 合疯窗口"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 所有信封（envelope_user=2633083674，按信封发送时间）===')
rows = conn.execute("""
    SELECT forward_id, envelope_time, fetched_at FROM forwards 
    WHERE envelope_user=2633083674 ORDER BY envelope_time""").fetchall()
for r in rows:
    t = datetime.fromtimestamp(r['envelope_time'] or 0, cst) if r['envelope_time'] else None
    print(f'  fwd={str(r["forward_id"])[:24]} | 信封时间={t}')

# HAPPY 窗口 = 8-17 11:30 ~ 12:15（用户说 11:34-12:07，放宽边界覆盖全部 15 个）
HAPPY_START = 1786937400   # 2026-08-17 11:30 +08
HAPPY_END = 1786940100     # 2026-08-17 12:15 +08

happy_fwds = [r['forward_id'] for r in rows if r['envelope_time'] and HAPPY_START <= r['envelope_time'] <= HAPPY_END]
print(f'\nHAPPY 窗口信封数: {len(happy_fwds)}')
print('非 HAPPY 窗口信封数:', len(rows) - len(happy_fwds))

# 收集 HAPPY 窗口信封中 user_id=1094950020 的消息 id
happy_ids = set()
other_ids = set()
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            uid = m.get('user_id')
            if uid is None:
                uid = (m.get('sender') or {}).get('user_id')
            if str(uid) != '1094950020':
                continue
            mid = m.get('real_id') or m.get('message_id')
            if mid is None:
                continue
            if r['envelope_time'] and HAPPY_START <= r['envelope_time'] <= HAPPY_END:
                happy_ids.add(mid)
            else:
                other_ids.add(mid)
    except Exception:
        pass

print(f'\nHAPPY 窗口信封中 1094950020 消息数: {len(happy_ids)}')
print(f'其他窗口信封中 1094950020 消息数: {len(other_ids)}')
print(f'重叠: {len(happy_ids & other_ids)}')

# 检查这些 id 在 messages 表的现状
if happy_ids:
    ph = ','.join('?' for _ in list(happy_ids)[:500])
    n = conn.execute(f"SELECT COUNT(*) FROM messages WHERE source='forward' AND message_id IN ({ph})", list(happy_ids)[:500]).fetchone()[0]
    print(f'前500个 HAPPY id 在 messages 中的命中: {n}')
conn.close()
