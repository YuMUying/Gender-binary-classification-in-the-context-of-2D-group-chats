# -*- coding: utf-8 -*-
"""peek_envelopes.py — 查看 17:05+ 新信封内层消息样本（时间+内容）"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards
    WHERE envelope_time >= strftime('%s','now','-8 hours')
    ORDER BY envelope_time DESC LIMIT 3""").fetchall()

for r in rows:
    et = datetime.fromtimestamp(r['envelope_time'], cst).strftime('%m-%d %H:%M:%S')
    print(f'===== 信封 fwd=...{str(r["forward_id"])[-8:]} 发送于 {et} =====')
    data = json.loads(r['content_raw'])
    msgs = data.get('messages', [])
    times = [m.get('time') for m in msgs if m.get('time')]
    if times:
        print(f'  内层时间范围: {datetime.fromtimestamp(min(times), cst).strftime("%Y-%m-%d %H:%M")} ~ {datetime.fromtimestamp(max(times), cst).strftime("%Y-%m-%d %H:%M")}')
    shown = 0
    for m in msgs:
        uid = m.get('sender', {}).get('user_id') or m.get('user_id')
        nick = m.get('sender', {}).get('nickname') or ''
        txt = ''
        for seg in m.get('message', []) or []:
            if seg.get('type') == 'text':
                txt += seg.get('data', {}).get('text', '')
        t = datetime.fromtimestamp(m.get('time', 0), cst).strftime('%m-%d %H:%M') if m.get('time') else '??'
        print(f'  [{t}] {uid} ({nick}): {txt[:60]!r}')
        shown += 1
        if shown >= 6:
            break
    print()
conn.close()
