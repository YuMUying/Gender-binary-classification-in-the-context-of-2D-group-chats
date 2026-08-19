# -*- coding: utf-8 -*-
"""inspect_envelopes.py — 查看最近 24h 转发信封的内层发送者分布"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))

rows = conn.execute("""
    SELECT forward_id, envelope_user, envelope_time, content_raw FROM forwards
    WHERE envelope_time >= strftime('%s','now','-24 hours') ORDER BY envelope_time""").fetchall()
print(f'最近24h信封: {len(rows)} 个\n')
for r in rows:
    t = datetime.fromtimestamp(r['envelope_time'], cst).strftime('%m-%d %H:%M:%S')
    data = json.loads(r['content_raw'])
    msgs = data.get('messages', [])
    senders = {}
    for m in msgs:
        uid = m.get('sender', {}).get('user_id') or m.get('user_id')
        nick = m.get('sender', {}).get('nickname') or ''
        card = m.get('sender', {}).get('card') or ''
        senders.setdefault(uid, {'nick': nick, 'card': card, 'n': 0})
        senders[uid]['n'] += 1
    parts = ' '.join(f'{u}({s["nick"]}/{s["card"]}x{s["n"]})' for u, s in senders.items())
    print(f'信封 {t} fwd=...{str(r["forward_id"])[-8:]}: {len(msgs)}条 | {parts}')
conn.close()
