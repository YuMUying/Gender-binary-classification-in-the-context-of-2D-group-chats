# -*- coding: utf-8 -*-
"""search_user.py — 全表搜索某 user_id 的所有痕迹"""
import sqlite3
import sys

uid = int(sys.argv[1])
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print(f'=== 搜索 user_id={uid} ===')
rows = conn.execute("""SELECT scene, peer_id, source, COUNT(*) c, MIN(time) mn, MAX(time) mx,
                       MAX(nickname) nick, MAX(card) card
                       FROM messages WHERE user_id=? GROUP BY scene, peer_id, source""", (uid,)).fetchall()
if not rows:
    print('messages 表：无任何消息')
else:
    for r in rows:
        print(f'  scene={r["scene"]} peer={r["peer_id"]} source={r["source"]} 消息={r["c"]}条 [{r["mn"]}~{r["mx"]}] 昵称={r["nick"]} 名片={r["card"]}')

# 相近 QQ 号（避免手误）
print('\n=== 相近 QQ 号（±3）===')
for delta in range(-3, 4):
    if delta == 0:
        continue
    u2 = uid + delta
    n = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=?", (u2,)).fetchone()['c']
    nick = conn.execute("SELECT nickname FROM user_profiles WHERE user_id=?", (u2,)).fetchone()
    if n:
        print(f'  {u2}: {n}条 昵称={nick["nickname"] if nick else "?"}')

# 群2 全部成员数量（当前库内）
print('\n=== 群2 (762673304) 库内发言用户数 ===')
print(conn.execute("SELECT COUNT(DISTINCT user_id) c FROM messages WHERE peer_id=762673304").fetchone()['c'])
conn.close()
