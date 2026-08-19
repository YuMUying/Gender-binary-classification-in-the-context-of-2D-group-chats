# -*- coding: utf-8 -*-
"""test_qce_download.py — 用 qce /download 端点按 fileid 下载长尾图（实测）"""
import json
import re
import sqlite3
import urllib.request

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 收集旧长尾 URL 的 fileid（优先：未打标、使用次数多的）
from collections import Counter
fileid_counter = Counter()
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json LIKE '%fileid=%'"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if isinstance(s, dict) and s.get('type') == 'image':
            u = (s.get('data') or {}).get('url') or ''
            m = re.search(r'fileid=([A-Za-z0-9_-]+)', u)
            if m:
                fileid_counter[m.group(1)] += 1
conn.close()
print(f'去重 fileid: {len(fileid_counter)} 个')

# 已打标 url（跳过）
import csv
known = set()
try:
    with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('url'):
                known.add(r['url'])
except Exception:
    pass

# 取前 10 个高频未打标 fileid 测试下载
token = '4Trx5OWltB1jKsdlYb6swnbelBExC71DAA34RBqL'
tested = 0
for fid, cnt in fileid_counter.most_common(10):
    url = f'http://127.0.0.1:40653/download?appid=1407&fileid={fid}&spec=0'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            ct = resp.headers.get('Content-Type', '')
            print(f'fileid={fid[:20]}... x{cnt} → OK {len(data)}B {ct}')
            if len(data) > 500 and 'json' not in ct:
                open(f'data/media/qce-dl-test_{fid[:12]}.img', 'wb').write(data)
    except Exception as e:
        print(f'fileid={fid[:20]}... x{cnt} → 失败 {e}')
    tested += 1
print(f'\n测试完成 {tested} 个')
