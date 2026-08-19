# -*- coding: utf-8 -*-
"""mark_skip_rar.py — 确认并标记 1.2G rar 文件跳过下载"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== media_files 中该大文件相关记录 ===')
rows = conn.execute("""
    SELECT * FROM media_files WHERE media_type IN ('file','video')
    ORDER BY id DESC LIMIT 20""").fetchall()
print(f'file/video 记录: {len(rows)} 条')
for r in rows:
    d = dict(r)
    print(f'  id={d["id"]} type={d["media_type"]} status={d["status"]} url={str(d["url"])[:60]} file_id={str(d["file_id"])[:40]}')

print('\n=== 检查是否已有该 rar 的下载痕迹 ===')
for r in conn.execute("""
    SELECT * FROM media_files 
    WHERE url LIKE '%MAMIYA%' OR file_id LIKE '%MAMIYA%' OR url LIKE '%.rar%'"""):
    d = dict(r)
    print(f'  命中: id={d["id"]} type={d["media_type"]} status={d["status"]} url={str(d["url"])[:80]}')

print('\n=== 本地文件系统是否已有该 rar ===')
import os
hits = []
for root in [r'C:\Users\Lenovo\.qq-chat-exporter\resources',
             r'C:\Users\Lenovo\Documents\Tencent Files\2740088195\nt_qq\nt_data']:
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if 'MAMIYA' in fn or fn.lower().endswith('.rar'):
                hits.append(os.path.join(dirpath, fn))
for h in hits:
    sz = os.path.getsize(h)
    print(f'  {h} ({sz/1024/1024:.0f}MB)')
if not hits:
    print('  未找到（未下载，安全）')
conn.close()
