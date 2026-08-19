# -*- coding: utf-8 -*-
"""check_new_envelopes.py — 检查 8-19 新信封内容"""
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 8-19 01:00 后入库的消息（forward 来源）
print('=== 8-19 01:00 后入库消息（source=forward）===')
rows = conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND time > 1787067600 ORDER BY time LIMIT 15""").fetchall()
print(f'共 {len(rows)} 条（显示前 15）')
for r in rows:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | {r["user_id"]} | {r["text"][:60]}')

# 用户构成
print('\n=== 信封中参与用户统计 ===')
for r in conn.execute("""
    SELECT user_id, COUNT(*) c FROM messages 
    WHERE source='forward' AND time > 1787067600 GROUP BY user_id ORDER BY c DESC"""):
    print(f'  {r["user_id"]}: {r["c"]} 条')

# 视频/文件占位符检查
print('\n=== 8-19 新消息中的视频/文件占位符 ===')
vids = conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND time > 1787067600 
      AND (text LIKE '%[视频%' OR text LIKE '%[文件%' OR text LIKE '%[语音%' OR text LIKE '%.rar%' OR text LIKE '%.mp4%')""").fetchall()
print(f'视频/文件类消息: {len(vids)} 条')
for r in vids[:20]:
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t} | {r["user_id"]} | {r["text"][:80]}')
conn.close()
