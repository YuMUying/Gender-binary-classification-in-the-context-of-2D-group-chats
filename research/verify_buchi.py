# -*- coding: utf-8 -*-
"""verify_buchi.py — 核对转发用户时间范围与 Buchi 标签"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))
def fmt(t): return datetime.fromtimestamp(t, cst).strftime('%Y-%m-%d %H:%M')

for uid, label in [(3541215132, '星辞'), (1094950020, 'HAPPY'), (2956792638, 'Buchi'), (2633083674, 'EirieYuki')]:
    r = conn.execute("SELECT COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE user_id=? AND source='forward'", (uid,)).fetchone()
    print(f'{label} {uid}: {r["c"]}条 [{fmt(r["mn"])} ~ {fmt(r["mx"])}]')

lab = conn.execute('SELECT * FROM speaker_labels WHERE user_id=2956792638').fetchone()
print('标签:', dict(lab) if lab else None)
conn.close()
