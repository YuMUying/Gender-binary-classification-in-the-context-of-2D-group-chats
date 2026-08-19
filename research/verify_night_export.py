# -*- coding: utf-8 -*-
"""verify_night_export.py — 验证夜间导出结果"""
import json
from collections import Counter

rows = [json.loads(l) for l in open('data/_night-test-train.jsonl', encoding='utf-8')]
print(f'train 行数: {len(rows)}')

# weight 分布
w = Counter(r.get('weight', 1.0) for r in rows)
print('weight 分布:', dict(sorted(w.items())))
night_rows = [r for r in rows if r.get('night')]
print(f'带 night 标记: {len(night_rows)}')
if night_rows:
    by_w = Counter(r['weight'] for r in night_rows)
    print('night 行 weight 分布:', dict(sorted(by_w.items())))
    # 深夜型少样本保护检查：weight=0.9 的用户
    prot = {}
    for r in night_rows:
        if r['weight'] == 0.9:
            prot.setdefault(r['user_id'], 0)
            prot[r['user_id']] += 1
    print(f'weight=0.9 用户(深夜型保护): {len(prot)} 人: {list(prot.keys())[:10]}')

# 对比：无 night 模式的行数（基线）
base = [json.loads(l) for l in open('data/train.jsonl', encoding='utf-8')]
print(f'\n正式 train.jsonl（无night）: {len(base)} 行（但那是旧标注66人前，只作参考）')

# val 检查
val = [json.loads(l) for l in open('data/_night-test-val.jsonl', encoding='utf-8')]
print(f'val 行数: {len(val)} | night 行: {sum(1 for r in val if r.get("night"))}')
