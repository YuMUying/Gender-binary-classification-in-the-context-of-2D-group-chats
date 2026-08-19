# -*- coding: utf-8 -*-
"""check_g3_envelopes.py — 检查新信封内容：参与者/图片占比/抽样"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import Counter

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 最新入库的 forward 消息（id 最大 800 条）
print('=== 新信封参与者分布 ===')
rows = conn.execute("""
    SELECT user_id, COUNT(*) c, MIN(time) mn, MAX(time) mx FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-900 FROM messages WHERE source='forward')
    GROUP BY user_id ORDER BY c DESC""").fetchall()
for r in rows:
    print(f'  {r["user_id"]}: {r["c"]} 条 | {datetime.fromtimestamp(r["mn"], cst)} ~ {datetime.fromtimestamp(r["mx"], cst)}')

# 图片占比
print('\n=== 图片占比 ===')
img = conn.execute("""
    SELECT COUNT(*) c FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-900 FROM messages WHERE source='forward')
      AND raw_json LIKE '%"type":"image"%'""").fetchone()[0]
total = conn.execute("""
    SELECT COUNT(*) c FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-900 FROM messages WHERE source='forward')""").fetchone()[0]
print(f'图片消息: {img}/{total} = {img/max(total,1):.2f}')

# 文本抽样
print('\n=== 文本消息抽样（最近 12 条）===')
for r in conn.execute("""
    SELECT time, user_id, text FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-900 FROM messages WHERE source='forward')
      AND text NOT LIKE '[%' AND LENGTH(text) > 2
    ORDER BY id DESC LIMIT 12"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | {r["user_id"]} | {r["text"][:50]}')

# 图片 URL 抽查（取 5 个 URL）
print('\n=== 图片 URL 抽查 ===')
urls = []
for r in conn.execute("""
    SELECT raw_json FROM messages 
    WHERE source='forward' AND id > (SELECT MAX(id)-900 FROM messages WHERE source='forward')
      AND raw_json LIKE '%"type":"image"%' LIMIT 200"""):
    try:
        j = json.loads(r['raw_json'])
        for seg in (j.get('message') or []):
            if isinstance(seg, dict) and seg.get('type') == 'image':
                u = (seg.get('data') or {}).get('url') or ''
                fn = (seg.get('data') or {}).get('file') or ''
                if u:
                    urls.append((u, fn))
    except Exception:
        pass
print(f'共收集 {len(urls)} 个图片引用')
for u, fn in urls[:5]:
    print(f'  file={fn} | url={u[:80]}')
conn.close()
