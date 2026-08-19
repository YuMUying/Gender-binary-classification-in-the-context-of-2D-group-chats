# -*- coding: utf-8 -*-
"""check_urls.py — 检查 image 段完整字段 + media_files 中该贴纸的记录"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 找一个含 cef084dc73b5 的消息
r = conn.execute("SELECT raw_json FROM messages WHERE raw_json LIKE '%cef084dc73b5%' LIMIT 1").fetchone()
if r:
    j = json.loads(r['raw_json'])
    for s in j.get('message') or []:
        if s.get('type') == 'image':
            print('=== raw_json image 段完整字段 ===')
            for k, v in s.get('data', {}).items():
                print(f'  {k}: {str(v)[:120]}')
    print()
    print('=== media_files 中含该串的记录 ===')
    for m in conn.execute("SELECT * FROM media_files WHERE url LIKE '%cef084dc73b5%' OR file_id LIKE '%cef084dc73b5%' LIMIT 3"):
        print(dict(m))
else:
    print('未找到该贴纸消息')

# 成功下载的 media 样本（看可用的完整 URL 形态）
print()
print('=== media_files 成功下载的 3 条样本 ===')
for m in conn.execute("SELECT * FROM media_files WHERE status='done' AND local_path IS NOT NULL LIMIT 3"):
    d = dict(m)
    print(f'  url={str(d["url"])[:100]}')
    print(f'  file_id={str(d["file_id"])[:80]}')
    print(f'  local_path={d["local_path"]}')
conn.close()
