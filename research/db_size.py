# -*- coding: utf-8 -*-
"""db_size.py — 数据库大小与表统计"""
import os
import sqlite3

db = 'data/qqchat.db'
size = os.path.getsize(db)
wal = os.path.getsize(db + '-wal') if os.path.exists(db + '-wal') else 0
shm = os.path.getsize(db + '-shm') if os.path.exists(db + '-shm') else 0
print(f'DB 文件: {size/1024/1024:.1f} MB (+WAL {wal/1024/1024:.1f} MB, +SHM {shm/1024/1024:.1f} MB)')

conn = sqlite3.connect(db)
print()
print('=== 各表行数 ===')
for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        print(f'  {name}: {n:,} 行')
    except Exception as e:
        print(f'  {name}: 无法统计 ({e})')

# 消息表按场景/来源分布
print()
print('=== messages 按 scene/source ===')
for r in conn.execute("SELECT scene, source, COUNT(*) c FROM messages GROUP BY scene, source ORDER BY c DESC"):
    print(f'  {r[0]}/{r[1]}: {r[2]:,}')

# 媒体目录大小
print()
media_dir = 'data/media'
if os.path.isdir(media_dir):
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(media_dir) for f in fn)
    n = sum(len(fn) for _, _, fn in os.walk(media_dir))
    print(f'data/media: {n} 个文件, {total/1024/1024:.1f} MB')
conn.close()
