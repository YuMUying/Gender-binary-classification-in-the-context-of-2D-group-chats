# -*- coding: utf-8 -*-
"""sticker_topk.py — Top-K 贴纸清单（频次 + 下载状态 + 覆盖率）"""
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 收集全部贴纸使用（不限已标注用户）
uses = Counter()      # (kind, key) -> count
n_sticker_msgs = 0
n_total = 0
for r in conn.execute("SELECT raw_json FROM messages WHERE raw_json IS NOT NULL"):
    try:
        j = json.loads(r['raw_json'])
    except Exception:
        continue
    segs = j.get('message') or []
    if not isinstance(segs, list):
        continue
    n_total += 1
    hit = False
    for s in segs:
        d = s.get('data') or {}
        t = s.get('type')
        if t == 'image':
            key = d.get('url') or d.get('file') or d.get('file_id') or ''
            if key:
                uses[('img', key)] += 1
                hit = True
        elif t == 'market_face':
            mid = str(d.get('id') or '')
            if mid:
                uses[('mk', mid)] += 1
                hit = True
    if hit:
        n_sticker_msgs += 1

total_uses = sum(uses.values())
print(f'消息 {n_total} 条，贴纸消息 {n_sticker_msgs} 条，贴纸使用总次数 {total_uses}，去重贴纸 {len(uses)} 个')
print()

# 下载状态统计（img 类按 url 匹配 media_files）
down = set()
for r in conn.execute("SELECT url, file_id FROM media_files WHERE status='done' AND local_path IS NOT NULL"):
    if r['url']:
        down.add(r['url'])
    if r['file_id']:
        down.add(r['file_id'])

top = uses.most_common(300)
covered = sum(c for _, c in top)
print(f'Top300 覆盖 {covered}/{total_uses} = {covered/total_uses:.1%} 的使用量')
print()
print(f'{"#":<4}{"类型":<6}{"使用次数":<8}{"下载":<5}键(截断)')
for i, ((kind, key), c) in enumerate(top, 1):
    dl = 'Y' if (kind == 'img' and (key in down)) else 'N'
    print(f'{i:<4}{kind:<6}{c:<8}{dl:<5}{key[:60]}')
conn.close()
