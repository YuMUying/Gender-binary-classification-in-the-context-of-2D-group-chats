# -*- coding: utf-8 -*-
"""sticker_download.py — 准备 Top-K 贴纸（复用已下载，缺失补下）

输出 data/sticker_tags/rank_NNN.ext + outputs/贴纸待标清单.csv
"""
import csv
import json
import os
import sqlite3
import urllib.request

K = 200
OUT_DIR = 'data/sticker_tags'
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 1) 全量贴纸使用次数（完整 url 为键）+ summary 统计
from collections import Counter
uses = Counter()
summ = Counter()
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json IS NOT NULL"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    for s in (j.get('message') or []):
        if not isinstance(s, dict):
            continue
        if s.get('type') == 'image':
            d = s.get('data') or {}
            url = d.get('url') or ''
            sm = d.get('summary') or ''
            if url:
                uses[url] += 1
                if sm:
                    summ[(url, sm)] += 1

# 2) media_files 已下载映射
downloaded = {}
for m in conn.execute("SELECT url, local_path FROM media_files WHERE status='downloaded' AND local_path IS NOT NULL"):
    if m['url']:
        downloaded.setdefault(m['url'], m['local_path'])
conn.close()

os.makedirs(OUT_DIR, exist_ok=True)
rows = []
missing = []
for i, (url, c) in enumerate(uses.most_common(K), 1):
    ext = os.path.splitext(url.split('?')[0])[1] or '.gif'
    if url in downloaded:
        src = downloaded[url]
    else:
        src = None
    rows.append({'rank': i, 'url': url, 'count': c, 'local_path': src, 'summary': ''})
    if not src:
        missing.append((i, url))

# 3) 写入清单 CSV
with open('outputs/贴纸待标清单.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['rank', 'url', 'count', 'summary', 'local_path', '主类', '情绪', '萌系'])
    for r in rows:
        sm = max((s for (u, s), c2 in summ.items() if u == r['url']), default='', key=lambda s: summ[(r['url'], s)])
        r['summary'] = sm
        w.writerow([r['rank'], r['url'], r['count'], sm, r['local_path'] or '', '', '', ''])

print(f'Top{K}: 已有本地文件 {sum(len(r) for r in rows if r["local_path"])} 个，缺 {len(missing)} 个')
if missing:
    print('缺失的将尝试直接下载...')
    for i, url in missing:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            ext = os.path.splitext(url.split('?')[0])[1] or '.gif'
            fn = os.path.join(OUT_DIR, f'rank_{i:03d}{ext}')
            with open(fn, 'wb') as fh:
                fh.write(data)
            print(f'  rank {i}: 已下载 {len(data)} 字节 → {fn}')
        except Exception as e:
            print(f'  rank {i}: 下载失败 {e}')

# 复制已下载文件到 sticker_tags（统一命名）
import shutil
n_copied = 0
for r in rows:
    if r['local_path'] and os.path.exists(r['local_path']):
        ext = os.path.splitext(r['local_path'])[1] or '.gif'
        dst = os.path.join(OUT_DIR, f'rank_{r["rank"]:03d}{ext}')
        if not os.path.exists(dst):
            try:
                shutil.copy2(r['local_path'], dst)
                n_copied += 1
            except Exception as e:
                print(f'  rank {r["rank"]}: 复制失败 {e}')
print(f'已统一复制到 {OUT_DIR}: {n_copied} 个')
