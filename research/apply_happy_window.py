# -*- coding: utf-8 -*-
"""apply_happy_window.py — 精确窗口 8-17 11:35:00~12:07:59 的信封 → HAPPY(1717582)"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

WIN_START = 1786937700   # 8-17 11:35:00 +08
WIN_END = 1786939680     # 8-17 12:08:00 +08（含 12:07:59）

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards 
    WHERE envelope_user=2633083674 ORDER BY envelope_time""").fetchall()

target = [r for r in rows if r['envelope_time'] and WIN_START <= r['envelope_time'] < WIN_END]
print(f'窗口内信封: {len(target)} 个')
for r in target:
    t = datetime.fromtimestamp(r['envelope_time'], cst)
    print(f'  fwd={str(r["forward_id"])[:24]} | {t.strftime("%H:%M:%S")}')

# 提取这些信封中 1094950020 的消息 id
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
print(f'\n窗口内 1094950020 消息 id: {len(ids)}')

# 检查这些 id 在 messages 表的当前归属
dist = {}
for i in range(0, len(ids), 400):
    chunk = list(ids)[i:i+400]
    ph = ','.join('?' for _ in chunk)
    for r in conn.execute(f"SELECT user_id, COUNT(*) c FROM messages WHERE source='forward' AND message_id IN ({ph}) GROUP BY user_id", chunk):
        dist[r['user_id']] = dist.get(r['user_id'], 0) + r['c']
print('当前归属:', dist)

# 执行修改：只改 user_id=1046636617 的行（我 remap 的），且仅限窗口内 id
if ids:
    lst = list(ids)
    total = 0
    for i in range(0, len(lst), 400):
        chunk = lst[i:i+400]
        ph = ','.join('?' for _ in chunk)
        cur = conn.execute(f"""
            UPDATE messages SET user_id=1717582, nickname='HAPPY'
            WHERE source='forward' AND user_id=1046636617 AND message_id IN ({ph})""", chunk)
        total += cur.rowcount
    conn.commit()
    print(f'\n已修改 {total} 条 → HAPPY(1717582)')

# 恢复 HAPPY 标注
conn.execute("""
    INSERT OR REPLACE INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, updated_at)
    VALUES (1717582, 'HAPPY', 'female', 'manual', 'high', ?)""", (int(__import__('time').time()),))
conn.commit()
print('speaker_labels: 1717582 → female(HAPPY) 已恢复')

# 验证
for uid in (1717582, 1046636617):
    r = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f'user {uid}: {r["c"]} 条')
conn.close()
