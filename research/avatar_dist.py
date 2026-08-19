# -*- coding: utf-8 -*-
"""avatar_dist.py — 头像描述风格分布（分性别）"""
import json
import sqlite3

desc = {}
for l in open('research/avatar_desc.jsonl', encoding='utf-8'):
    l = l.strip()
    if l:
        d = json.loads(l)
        desc[str(d['uin'])] = d['desc']

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {str(r['user_id']): r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
conn.close()

STYLE_KEYS = [('动漫', '二次元/动漫'), ('真人', '真人'), ('动物', '动物'), ('抽象', '抽象'), ('Q版', 'Q版'), ('风景', '风景')]
from collections import Counter

for g in ('male', 'female'):
    users = [u for u in desc if labels.get(u) == g]
    style_c = Counter()
    for u in users:
        d = desc[u]
        s = json.dumps(d, ensure_ascii=False)
        hit = False
        for k, name in STYLE_KEYS:
            if k in s:
                style_c[name] += 1
                hit = True
        if not hit:
            style_c['其他'] += 1
    print(f'{g} ({len(users)}人) 头像风格: ' + ' '.join(f'{k}={v}' for k, v in style_c.most_common()))
    # 动漫少女关键词
    girl = sum(1 for u in users if '少女' in json.dumps(desc[u], ensure_ascii=False))
    print(f'  其中含"少女"字样: {girl}/{len(users)}')
