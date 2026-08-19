# -*- coding: utf-8 -*-
"""inspect_multi.py — 检查多版本分数分布"""
import csv
import json
import statistics

rows = list(csv.DictReader(open('outputs/score-multi.csv', encoding='utf-8')))
for m in ['p_bert-v4', 'p_bert-v5', 'p_bert-v6', 'p_bert-v7']:
    vals = [float(r[m]) for r in rows if r[m]]
    print(f'{m}: 均值={statistics.mean(vals):.3f} 中位={statistics.median(vals):.3f} 范围=[{min(vals):.3f},{max(vals):.3f}]')
for m in ['bert-v4', 'bert-v5', 'bert-v6', 'bert-v7']:
    try:
        met = json.load(open(f'models/{m}/metrics.json', encoding='utf-8'))
        print(f'{m} 阈值: {met.get("threshold")}')
    except Exception as e:
        print(f'{m}: 无metrics ({e})')
print()
print('高分歧 top8:')
for r in sorted(rows, key=lambda r: -float(r['std']))[:8]:
    print(f'  {r["user_id"]}: v4={r["p_bert-v4"]} v5={r["p_bert-v5"]} v6={r["p_bert-v6"]} v7={r["p_bert-v7"]} std={r["std"]} flips={r["flip_count"]}')
