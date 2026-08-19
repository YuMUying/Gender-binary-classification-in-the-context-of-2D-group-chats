# -*- coding: utf-8 -*-
"""fix_labels.py — 确认/设置 Buchi 与 隐世云梦 标注"""
import sqlite3
import time

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

for uid in (2956792638, 439161815, 3541215132, 1717582, 1046636617):
    r = conn.execute("SELECT * FROM speaker_labels WHERE user_id=?", (uid,)).fetchone()
    print(f'{uid}: {dict(r) if r else "无标注"}')

# Buchi → female
conn.execute("""
    INSERT OR REPLACE INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, updated_at)
    VALUES (2956792638, 'Buchi', 'female', 'manual', 'high', ?)""", (int(time.time()),))
conn.commit()
print('\n2956792638 → female(Buchi) 已设置')

# 隐世云梦 439161815 → male（用户说标注为男，确认）
r = conn.execute("SELECT gender FROM speaker_labels WHERE user_id=439161815").fetchone()
print(f'439161815 当前标注: {r["gender"] if r else "无"}')
if not r or r['gender'] != 'male':
    conn.execute("""
        INSERT OR REPLACE INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, updated_at)
        VALUES (439161815, '隐世云梦', 'male', 'manual', 'high', ?)""", (int(time.time()),))
    conn.commit()
    print('439161815 → male(隐世云梦) 已设置')
else:
    print('439161815 已是 male ✓')
conn.close()
