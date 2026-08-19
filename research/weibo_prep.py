# -*- coding: utf-8 -*-
"""weibo_prep.py — 微博数据集清洗：提取女性文本 + 域偏移统计"""
import csv
import os
import re

ROOT = r'G:\Deepseek\e8784-extract\weibo'
OUT = r'G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\data\weibo-female.jsonl'

# 看一个 CSV 的结构
sample_f = os.path.join(ROOT, 'female', '宁宁河上草', '2821194470.csv')
with open(sample_f, encoding='utf-8-sig', errors='replace') as f:
    rd = csv.reader(f)
    header = next(rd)
    print('CSV 表头:', header)
    for i, row in enumerate(rd):
        if i >= 2:
            break
        print(f'  行{i}: {[str(x)[:40] for x in row]}')

# 统计所有女性文件的行数/文本量
n_female_files = 0
n_female_rows = 0
total_chars = 0
for user_dir in os.listdir(os.path.join(ROOT, 'female')):
    d = os.path.join(ROOT, 'female', user_dir)
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if fn.endswith('.csv'):
            n_female_files += 1
            with open(os.path.join(d, fn), encoding='utf-8-sig', errors='replace') as f:
                rd = csv.reader(f)
                try:
                    header = next(rd)
                except Exception:
                    continue
                # 找文本列
                for row in rd:
                    if len(row) < 2:
                        continue
                    n_female_rows += 1
                    total_chars += sum(len(str(x)) for x in row)
print(f'\n女性文件: {n_female_files} | 数据行: {n_female_rows} | 字符总量: {total_chars}')
