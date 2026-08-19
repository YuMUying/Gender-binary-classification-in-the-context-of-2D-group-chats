# -*- coding: utf-8 -*-
"""map_ctx_users2.py — 🐷/江墨白 信封消息映射"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT id, text, raw_json FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-30 FROM messages WHERE source='forward')""").fetchall()
mapped = {'🐷': 838969717, '江墨白': 2803093623, '星崤月凛': 3189511804}
count = 0
for r in rows:
    j = json.loads(r['raw_json'] or '{}')
    sender = j.get('sender') or {}
    nick = sender.get('nickname') or ''
    if nick in mapped:
        uid = mapped[nick]
        cur = conn.execute("UPDATE messages SET user_id=?, nickname=? WHERE id=?", (uid, nick, r['id']))
        count += cur.rowcount
conn.commit()
print(f'信封消息映射完成: {count} 条')

# 验证
print('\n=== 各用户信封消息数 ===')
for uid, nick in ((3189511804, '星崤月凛'), (838969717, '🐷'), (2803093623, '江墨白')):
    r = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=? AND source='forward'", (uid,)).fetchone()
    print(f'  {uid} {nick}: {r["c"]} 条转发消息')
# 占位符剩余
r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=1094950020").fetchone()
print(f'占位符 1094950020 剩余: {r[0]}')
conn.close()
