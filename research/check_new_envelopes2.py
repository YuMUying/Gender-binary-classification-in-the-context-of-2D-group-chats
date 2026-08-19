# -*- coding: utf-8 -*-
"""check_new_envelopes2.py — 按入库顺序查新信封内容"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== forwards 最新 15 条 ===')
for r in conn.execute("SELECT * FROM forwards ORDER BY fetched_at DESC LIMIT 15"):
    d = dict(r)
    t = datetime.fromtimestamp(d.get('fetched_at') or 0, cst)
    print(f'  {t} | fwd={str(d.get("forward_id"))[:24]} | user={d.get("envelope_user")}')

print('\n=== messages source=forward 最新入库（按 id 倒序 20 条）===')
for r in conn.execute("SELECT id, time, user_id, text FROM messages WHERE source='forward' ORDER BY id DESC LIMIT 20"):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  id={r["id"]} | {t} | {r["user_id"]} | {r["text"][:60]}')

print('\n=== 视频/文件占位符（最近入库 forward）===')
vids = conn.execute("""
    SELECT id, time, user_id, text FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id) - 5000 FROM messages WHERE source='forward')
      AND (text LIKE '%[视频%' OR text LIKE '%[文件%' OR text LIKE '%[语音%' OR text LIKE '%.rar%' OR text LIKE '%.mp4%' OR text LIKE '%MAMIYA%')""").fetchall()
print(f'视频/文件类: {len(vids)} 条')
for r in vids[:20]:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  id={r["id"]} | {t} | {r["user_id"]} | {r["text"][:90]}')
conn.close()
