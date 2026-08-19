# -*- coding: utf-8 -*-
"""media_status.py — 媒体下载状态与缓存统计"""
import json
import os
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== media_files 状态分布 ===')
for r in conn.execute('SELECT status, COUNT(*) c FROM media_files GROUP BY status ORDER BY c DESC'):
    print(f'  {r["status"]}: {r["c"]}')

print('\n=== 消息中 image 段 URL 类型分布 ===')
types = Counter()
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json LIKE '%image%' LIMIT 20000"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if isinstance(s, dict) and s.get('type') == 'image':
            u = (s.get('data') or {}).get('url') or ''
            if 'gxh.vip.qq.com' in u:
                types['gxh官方表情包'] += 1
            elif 'download?appid' in u or 'gchat.qpic.cn' in u:
                types['qpic签名下载链接'] += 1
            else:
                types['其他'] += 1
print(dict(types))

print('\n=== QQ 客户端 Pic 缓存（按月份目录）===')
pic = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic')
months = Counter()
if os.path.isdir(pic):
    for root, dirs, files in os.walk(pic):
        rel = os.path.relpath(root, pic)
        if rel != '.':
            months[rel.split(os.sep)[0]] += len(files)
    for m in sorted(months):
        print(f'  {m}: {months[m]} 个文件')
conn.close()
