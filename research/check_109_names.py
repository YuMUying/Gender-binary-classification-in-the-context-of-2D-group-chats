# -*- coding: utf-8 -*-
"""check_109_names.py — 1094950020 消息里的发送者昵称分布"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 已映射，先查备份中的原样？直接用 forwards 表 content_raw 查 sender 字段
names = {}
rows = conn.execute("SELECT content_raw FROM forwards WHERE envelope_user=2633083674").fetchall()
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            uid = m.get('user_id')
            nick = m.get('nickname') or ''
            sender = m.get('sender') or {}
            sn = sender.get('nickname') or ''
            key = f'{uid}|{nick}|{sn}'
            names[key] = names.get(key, 0) + 1
    except Exception:
        pass

print('=== forwards 内容中的 user_id/昵称 分布 ===')
for k, c in sorted(names.items(), key=lambda x: -x[1]):
    print(f'  {c:5d} 条 | {k}')

# 检查 1094950020 的 raw_json sender 字段（messages 表已映射，从备份查？直接看 raw_json 里的 user_id 字段）
print('\n=== messages 里原 1094950020 消息的 raw_json user_id 抽查（新信封部分）===')
rows2 = conn.execute("""
    SELECT raw_json FROM messages 
    WHERE user_id=1046636617 AND source='forward' AND raw_json LIKE '%1094950020%'
    LIMIT 5""").fetchall()
for r in rows2[:3]:
    print((r['raw_json'] or '')[:300])
conn.close()
