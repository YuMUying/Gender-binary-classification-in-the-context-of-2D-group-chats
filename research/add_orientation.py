# -*- coding: utf-8 -*-
"""add_orientation.py — 扩展 speaker_labels 加 orientation 列 + 批量标注

orientation 取值（用户标定原文）：'男娘+双','双','同性恋' 等
"""
import sqlite3
import time

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 1. 加列
cols = [r['name'] for r in conn.execute("PRAGMA table_info(speaker_labels)")]
if 'orientation' not in cols:
    conn.execute("ALTER TABLE speaker_labels ADD COLUMN orientation TEXT")
    print('已加列 orientation')
else:
    print('orientation 列已存在')

# 2. 批量标注（gender + orientation）
LABELS = [
    # (user_id, gender, orientation, nickname)
    (2633083674, None, '双', None),           # 只标性取向，不标性别
    (443628409, 'male', '男娘+双', None),
    (1197677845, 'male', '双', None),
    (1965417382, None, '双', None),           # 只标性取向
    (375569635, 'male', '男娘+双', None),
    (2948988043, 'male', '双', None),
    (1046636617, 'male', '双', '合疯'),
    (439161815, 'male', '双', '隐世云梦'),
    (963653008, 'male', '双', None),
    (3189511804, 'male', '同性恋', '星崤月凛'),
]

for uid, gender, orientation, nick in LABELS:
    now = int(time.time())
    if gender:
        conn.execute("""
            INSERT INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, updated_at, orientation)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              gender=excluded.gender, orientation=excluded.orientation,
              label_source='manual', label_confidence='high', updated_at=excluded.updated_at
            """, (uid, nick, gender, 'manual', 'high', now, orientation))
    else:
        # 只更新 orientation，不动 gender
        conn.execute("""
            INSERT INTO speaker_labels (user_id, gender, label_source, label_confidence, updated_at, orientation)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET orientation=excluded.orientation,
              label_source='manual', label_confidence='high', updated_at=excluded.updated_at
            """, (uid, 'unknown', 'manual', 'high', now, orientation))
    print(f'  {uid}: gender={gender or "(保持)"} orientation={orientation}')
conn.commit()

# 验证
print('\n=== 带 orientation 的用户 ===')
for r in conn.execute("SELECT user_id, gender, orientation FROM speaker_labels WHERE orientation IS NOT NULL ORDER BY user_id"):
    print(f'  {r["user_id"]} | {r["gender"]} | {r["orientation"]}')
conn.close()
