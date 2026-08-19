# -*- coding: utf-8 -*-
"""fix_synth_uid.py — 重写合成/微博数据的 user_id 分组（用户级平权公平化）

问题：原文件每条消息一个 user_id → 用户级平权采样下每条权重=1，
      真实用户权重=1/消息数，合成数据被严重过采样。
修复：合成按风格分 5 个用户；微博按真实用户分 48 个用户。
"""
import csv
import json
import os

# --- 合成数据：按风格分用户 ---
src = 'data/synth-female-v2.jsonl'
dst = 'data/synth-female-v2.jsonl'
rows = [json.loads(l) for l in open(src, encoding='utf-8')]
style_uid = {'normal': 9000100001, 'abstract': 9000100002, 'moe': 9000100003,
             'rough': 9000100004, 'night': 9000100005}
for r in rows:
    r['user_id'] = style_uid.get(r.get('style'), 9000100001)
    r['group_id'] = 0
with open(dst, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
from collections import Counter
print('合成数据用户分布:', dict(Counter(r['user_id'] for r in rows)))

# --- 微博数据：按真实用户分组 ---
wb_src = r'G:\Deepseek\e8784-extract\weibo'
out_rows = []
uid_base = 9000200000
user_map = {}   # (gender, user_dir) -> uid
for gender in ('female',):
    gdir = os.path.join(wb_src, gender)
    if not os.path.isdir(gdir):
        continue
    for user_dir in os.listdir(gdir):
        d = os.path.join(gdir, user_dir)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.csv'):
                continue
            with open(os.path.join(d, fn), encoding='utf-8-sig', errors='replace') as f:
                rd = csv.reader(f)
                try:
                    header = next(rd)
                    ti = header.index('正文')
                except Exception:
                    continue
                key = (gender, user_dir)
                if key not in user_map:
                    user_map[key] = uid_base + len(user_map)
                uid = user_map[key]
                import re
                CJK = re.compile(r'[\u4e00-\u9fff]')
                for row in rd:
                    if len(row) <= ti:
                        continue
                    t = (row[ti] or '').strip()
                    if not t or len(t) < 4 or len(t) > 200 or not CJK.search(t):
                        continue
                    out_rows.append({'text': t, 'label': 'female', 'user_id': uid,
                                     'group_id': 0, 'time': 0, 'source': 'weibo'})
with open('data/weibo-female.jsonl', 'w', encoding='utf-8') as f:
    for r in out_rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'微博数据: {len(out_rows)} 条, {len(user_map)} 个用户')
print('微博用户样本量分布:', sorted(Counter(r['user_id'] for r in out_rows).values())[:5], '...',
      sorted(Counter(r['user_id'] for r in out_rows).values())[-5:])
