# -*- coding: utf-8 -*-
"""verify_remap.py — 验证 439161815 修正结果"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
cst = timezone(timedelta(hours=8))
def fmt(t): return datetime.fromtimestamp(t, cst).strftime('%Y-%m-%d')

for uid, name in [(439161815, '隐世云梦'), (1094950020, 'HAPPY'), (2633083674, 'EirieYuki')]:
    rows = conn.execute("SELECT source, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages WHERE user_id=? GROUP BY source", (uid,)).fetchall()
    parts = []
    for r in rows:
        parts.append(f"{r['source']}={r['c']}条[{fmt(r['mn'])}~{fmt(r['mx'])}]")
    print(f'{name} {uid}: ' + ' | '.join(parts))

lab = conn.execute('SELECT gender FROM speaker_labels WHERE user_id=439161815').fetchone()
print('439161815 标注:', lab['gender'] if lab else '无')
conn.close()
