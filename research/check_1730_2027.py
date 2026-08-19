# -*- coding: utf-8 -*-
"""check_1730_2027.py — 检查 17:05-20:00 与 20:27-21:00 窗口信封的内容归属"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import Counter

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT forward_id, envelope_time, content_raw FROM forwards WHERE envelope_user=2633083674 ORDER BY envelope_time").fetchall()

W1_START = 1786960800  # 8-17 17:00
W1_END = 1786980000    # 8-17 20:26
W2_START = 1786980000  # 8-17 20:27
W2_END = 1786993200    # 8-17 21:00

for label, ws, we in (('17:00-20:26', W1_START, W1_END), ('20:27-21:00', W2_START, W2_END)):
    envs = [r for r in rows if r['envelope_time'] and ws <= r['envelope_time'] <= we]
    print(f'\n=== 窗口 {label}: {len(envs)} 个信封 ===')
    sender_dist = Counter()
    for r in envs:
        try:
            j = json.loads(r['content_raw'])
            for m in (j.get('messages') or []):
                s = m.get('sender') or {}
                uid = m.get('user_id')
                suid = s.get('user_id')
                snick = s.get('nickname') or ''
                sender_dist[(str(uid), str(suid), snick)] += 1
        except Exception:
            pass
    for k, c in sender_dist.most_common(10):
        print(f'  m.user_id={k[0]} | sender.user_id={k[1]} | sender.nick={k[2]}: {c}')

# 2956792638 / 439161815 的消息在 messages 表的来源
print('\n=== 2956792638 消息来源（scene/source/peer）===')
for r in conn.execute("SELECT scene, source, peer_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE user_id=2956792638 GROUP BY scene, source, peer_id"):
    print(f'  scene={r["scene"]} source={r["source"]} peer={r["peer_id"]}: {r["c"]} 条 | {r["mn"]}~{r["mx"]}')

print('\n=== 439161815 消息来源 ===')
for r in conn.execute("SELECT scene, source, peer_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE user_id=439161815 GROUP BY scene, source, peer_id"):
    print(f'  scene={r["scene"]} source={r["source"]} peer={r["peer_id"]}: {r["c"]} 条 | {r["mn"]}~{r["mx"]}')
conn.close()
