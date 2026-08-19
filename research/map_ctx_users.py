# -*- coding: utf-8 -*-
"""map_ctx_users.py — 信封三人归属 + 星崤月凛改标女"""
import sqlite3
import time

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 1. 找 🐷 和 江墨白 的真实号（DB 昵称匹配）
for nick in ('🐷', '江墨白'):
    rows = conn.execute("SELECT user_id, COUNT(*) c FROM messages WHERE nickname=? GROUP BY user_id ORDER BY c DESC LIMIT 3", (nick,)).fetchall()
    print(f'昵称[{nick}]: {[dict(r) for r in rows]}')

# 2. 星崤月凛 3189511804 改标 female
cur = conn.execute("""
    INSERT OR REPLACE INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, updated_at)
    VALUES (3189511804, '星崤月凛', 'female', 'manual', 'high', ?)""", (int(time.time()),))
print(f'3189511804 → female 已设置')
conn.commit()

# 3. 信封消息归属（按 sender.nickname 映射）
#    星崤月凛 → 3189511804；江墨白/🐷 待确认（先查 DB 身份再映射）
rows = conn.execute("""
    SELECT id, text, raw_json FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-30 FROM messages WHERE source='forward')""").fetchall()
import json
for r in rows:
    j = json.loads(r['raw_json'] or '{}')
    sender = j.get('sender') or {}
    nick = sender.get('nickname') or ''
    if nick == '星崤月凛':
        conn.execute("UPDATE messages SET user_id=3189511804, nickname='星崤月凛' WHERE id=?", (r['id'],))
        print(f'  星崤月凛消息 → 3189511804: {r["text"][:30]}')
conn.commit()
conn.close()
