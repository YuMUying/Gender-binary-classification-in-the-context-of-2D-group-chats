# -*- coding: utf-8 -*-
"""search_bjg_images.py — 全量搜索白驹过隙信封图片"""
import json
import os
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT raw_json FROM messages 
    WHERE user_id=3615168664 AND source='forward' AND raw_json LIKE '%"type":"image"%'""").fetchall()
fns = set()
for r in rows:
    try:
        j = json.loads(r['raw_json'])
        for seg in (j.get('message') or []):
            if isinstance(seg, dict) and seg.get('type') == 'image':
                fn = (seg.get('data') or {}).get('file') or ''
                if fn:
                    fns.add(fn.upper())
    except Exception:
        pass
print(f'去重文件名: {len(fns)}')

dirs = [
    r'C:\Users\Lenovo\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic',
    r'G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\data\media\qce-harvest',
    r'G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\data\media\826904606',
    r'G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\data\media\762673304',
    r'C:\Users\Lenovo\Documents\Tencent Files\1394876195\nt_qq\nt_data\Pic',
]
found = {}
for d in dirs:
    if not os.path.isdir(d):
        continue
    for root, _, files in os.walk(d):
        for fn in files:
            u = fn.upper()
            if u in fns:
                found.setdefault(u, os.path.join(root, fn))
print(f'找到: {len(found)}/{len(fns)}')
for u, p in list(found.items())[:15]:
    print(f'  {u} → {p} ({os.path.getsize(p)/1024:.0f}KB)')
with open('research/bjg_images_found.txt', 'w', encoding='utf-8') as f:
    for u, p in found.items():
        f.write(f'{p}\n')
conn.close()
