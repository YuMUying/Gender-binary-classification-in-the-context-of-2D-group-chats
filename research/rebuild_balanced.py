# -*- coding: utf-8 -*-
"""rebuild_balanced.py — 重新生成平衡的外部增强数据

原则：外部用户数 ≈ 真实用户数（60）的一半到一倍
- 微博: 48 → 24 用户（随机抽样，按样本量分层保证多样性）
- 抑郁: 2000 → 30 用户（随机）
- 合成: 5 用户（保留）
外部合计 59 ≈ 真实 60 → 用户级平权下外部采样占比 ~50%
"""
import json
import random
import sqlite3

random.seed(42)

# --- 读取现有数据 ---
def load(path):
    rows = [json.loads(l) for l in open(path, encoding='utf-8')]
    users = {}
    for r in rows:
        users.setdefault(r['user_id'], []).append(r)
    return rows, users

# --- 微博: 48 → 24 用户 ---
_, wb_users = load('data/weibo-female.jsonl')
wb_ids = sorted(wb_users.keys())
# 分层：按样本量排序，均匀抽 24
wb_ids_sorted = sorted(wb_ids, key=lambda u: -len(wb_users[u]))
wb_keep = wb_ids_sorted[::2][:24]
if len(wb_keep) < 24:
    wb_keep = random.sample(wb_ids, 24)
wb_rows = [r for u in wb_keep for r in wb_users[u]]
with open('data/weibo-female.jsonl', 'w', encoding='utf-8') as f:
    for r in wb_rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'微博: {len(wb_ids)} → {len(wb_keep)} 用户, {len(wb_rows)} 条')

# --- 抑郁: 2000 → 30 用户 ---
_, dep_users = load('data/weibo-dep-female.jsonl')
dep_ids = sorted(dep_users.keys())
dep_keep = random.sample(dep_ids, 30)
dep_rows = [r for u in dep_keep for r in dep_users[u]]
with open('data/weibo-dep-female.jsonl', 'w', encoding='utf-8') as f:
    for r in dep_rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'抑郁: {len(dep_ids)} → {len(dep_keep)} 用户, {len(dep_rows)} 条')

# --- 合成: 保持 5 用户 ---
_, syn_users = load('data/synth-female-v2.jsonl')
print(f'合成: {len(syn_users)} 用户')

# 汇总
total_ext = len(wb_keep) + len(dep_keep) + len(syn_users)
print(f'\n外部用户合计: {total_ext} | 真实训练用户: 60 | 外部占比: {total_ext/(total_ext+60)*100:.0f}%')
