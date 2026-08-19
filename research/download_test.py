# -*- coding: utf-8 -*-
"""download_test.py — 测试 rkey 链接直下 + 小写md5匹配缓存"""
import json
import os
import sqlite3
import urllib.request

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 找一条含 download?appid 的 url
sample = None
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json LIKE '%download?appid%' LIMIT 3"):
    j = json.loads(r['raw_json'])
    for s in j.get('message') or []:
        if isinstance(s, dict) and s.get('type') == 'image':
            d = s.get('data') or {}
            u = d.get('url') or ''
            if 'download?appid' in u:
                sample = (u, d.get('file'))
                break
    if sample:
        break
conn.close()
print('测试:', sample[1], sample[0][:80])

if sample:
    url, f = sample
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        print(f'rkey 直下成功: {len(data)} 字节, content-type={resp.headers.get("Content-Type")}')
        os.makedirs('data/sticker_longtail', exist_ok=True)
        open(f'data/sticker_longtail/test_{f}', 'wb').write(data)
    except Exception as e:
        print(f'rkey 直下失败: {e}')

# 小写 md5 匹配缓存
pic = os.path.expanduser(r'~\Documents\Tencent Files\2740088195\nt_qq\nt_data\Pic')
cache = {}
for root, dirs, files in os.walk(pic):
    for fn in files:
        cache.setdefault(os.path.splitext(fn)[0].lower(), os.path.join(root, fn))
if sample:
    base = os.path.splitext(sample[1])[0].lower()
    print('小写md5命中缓存:', base in cache, cache.get(base))
