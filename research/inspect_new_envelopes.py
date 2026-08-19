# -*- coding: utf-8 -*-
"""inspect_new_envelopes.py — 检查 20:27+ 新信封：发送者 + 嵌套内联内容"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))

rows = conn.execute("""
    SELECT forward_id, envelope_time, content_raw FROM forwards
    WHERE envelope_time >= strftime('%s','now','-2 hours')
    ORDER BY envelope_time""").fetchall()
print(f'最近2h信封: {len(rows)} 个')

def walk(msgs, depth, stats, out):
    for m in msgs or []:
        uid = (m.get('sender') or {}).get('user_id') or m.get('user_id')
        stats['by_user'][uid] = stats['by_user'].get(uid, 0) + 1
        t = m.get('time') or 0
        if t:
            stats['tmin'] = min(stats['tmin'], t); stats['tmax'] = max(stats['tmax'], t)
        for seg in m.get('message') or []:
            if seg.get('type') == 'forward':
                d = seg.get('data') or {}
                stats['nested'][(depth, bool(d.get('id')), bool(d.get('content')))] = stats['nested'].get((depth, bool(d.get('id')), bool(d.get('content'))), 0) + 1
                if isinstance(d.get('content'), list) and d['content']:
                    stats['inline_msgs'] += len(d['content'])
                    out.append((depth + 1, d['content']))
                    walk(d['content'], depth + 1, stats, out)

for r in rows:
    data = json.loads(r['content_raw'])
    msgs = data.get('messages', [])
    stats = {'by_user': {}, 'nested': {}, 'inline_msgs': 0, 'tmin': 10**12, 'tmax': 0}
    out = []
    walk(msgs, 0, stats, out)
    et = datetime.fromtimestamp(r['envelope_time'], cst).strftime('%H:%M:%S')
    tmin = datetime.fromtimestamp(stats['tmin'], cst).strftime('%m-%d %H:%M') if stats['tmin'] < 10**12 else '?'
    tmax = datetime.fromtimestamp(stats['tmax'], cst).strftime('%m-%d %H:%M') if stats['tmax'] else '?'
    print(f'\n信封 fwd=...{str(r["forward_id"])[-8:]} @{et}: 顶层{len(msgs)}条 | 内层时间 {tmin}~{tmax}')
    print(f'  发送者: {stats["by_user"]}')
    print(f'  嵌套段: {stats["nested"]} | 内联消息数: {stats["inline_msgs"]}')
conn.close()
