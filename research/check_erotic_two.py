# -*- coding: utf-8 -*-
"""check_erotic_two.py — 查看两用户现有涩情标签 + 高涩情消息抽样"""
import json
from collections import Counter

for uid in (2673619125, 3600881346):
    levels = []
    samples = []
    for l in open('research/erotic_labels.jsonl', encoding='utf-8'):
        j = json.loads(l)
        if j.get('user_id') == uid:
            levels.append(j.get('level'))
            if j.get('level', 0) >= 2:
                samples.append(j.get('text', '')[:60])
    print(f'{uid}: 已标 {len(levels)} 条, level分布: {dict(Counter(levels))}')
    for s in samples[:5]:
        print(f'    [{s}]')
    print()
