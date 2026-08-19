# -*- coding: utf-8 -*-
"""list_bjg_image_names.py — 输出白驹过隙信封图片文件名（JSON）"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
names = {}
for r in conn.execute("""
    SELECT raw_json FROM messages 
    WHERE user_id=3615168664 AND source='forward' AND raw_json LIKE '%"type":"image"%'"""):
    try:
        j = json.loads(r['raw_json'])
        for seg in (j.get('message') or []):
            if isinstance(seg, dict) and seg.get('type') == 'image':
                fn = (seg.get('data') or {}).get('file') or ''
                if fn:
                    names[fn] = 'envelope'
    except Exception:
        pass
print(json.dumps(names, ensure_ascii=False))
conn.close()
