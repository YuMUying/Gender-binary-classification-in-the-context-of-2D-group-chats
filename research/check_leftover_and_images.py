# -*- coding: utf-8 -*-
"""check_leftover_and_images.py — 剩余占位符 + 图片验证"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 剩余占位符消息 ===')
for r in conn.execute("SELECT id, time, text FROM messages WHERE user_id=1094950020"):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  id={r["id"]} | {t} | {r["text"][:40]}')

print('\n=== 白驹过隙信封的图片消息统计 ===')
rows = conn.execute("""
    SELECT raw_json FROM messages 
    WHERE user_id=3615168664 AND source='forward' AND raw_json LIKE '%"type":"image"%'""").fetchall()
imgs = []
for r in rows:
    try:
        j = json.loads(r['raw_json'])
        for seg in (j.get('message') or []):
            if isinstance(seg, dict) and seg.get('type') == 'image':
                d = seg.get('data') or {}
                fn = d.get('file') or ''
                u = d.get('url') or ''
                if fn:
                    imgs.append(fn)
    except Exception:
        pass
print(f'图片引用数: {len(imgs)}')
unique = set(imgs)
print(f'去重后: {len(unique)}')

# 检查本地 Pic 缓存是否有这些文件
import os
pic_dir = r'C:\Users\Lenovo\Documents\Tencent Files\1394876195\nt_qq\nt_data\Pic'
found = []
if os.path.isdir(pic_dir):
    for root, dirs, files in os.walk(pic_dir):
        for fn in files:
            if fn.upper() in unique or fn in unique:
                found.append(os.path.join(root, fn))
print(f'本地 Pic 缓存命中: {len(found)}')
for f in found[:5]:
    print(f'  {f} ({os.path.getsize(f)/1024:.0f}KB)')
conn.close()
