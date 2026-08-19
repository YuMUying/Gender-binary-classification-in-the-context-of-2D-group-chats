# -*- coding: utf-8 -*-
"""rebuild_balanced2.py — 微博与抑郁语料平衡（用户数 24:24，每用户上限 100 条）

原则：外部总量可大于真实（真实女性仅 13-16 人，需外部补充），
     但微博/抑郁两部分用户级平权权重相当（用户数对齐），避免单方主导。
"""
import json
import random

random.seed(42)

def load(path):
    rows = [json.loads(l) for l in open(path, encoding='utf-8')]
    users = {}
    for r in rows:
        users.setdefault(r['user_id'], []).append(r)
    return rows, users

# --- 微博: 24 用户（保留原 24 用户抽取） ---
_, wb_users = load('data/weibo-female.jsonl')
wb_ids = sorted(wb_users.keys())
print(f'微博当前用户: {len(wb_ids)}')

# --- 抑郁: 从原始 2000 用户重新抽 24 用户，每用户 100 条 ---
import os
SRC_DEP = r'G:\Deepseek\WU3D\depressed.json'
print('重新从 WU3D 提取抑郁女性（24 用户 × 100 条）...')
with open(SRC_DEP, encoding='utf-8') as f:
    dep_all = json.load(f)

dep_female = []
for u in dep_all:
    g = str(u.get('gender') or '')
    if g != '女':
        continue
    tweets = u.get('tweets') or []
    texts = []
    for t in tweets:
        c = str(t.get('tweet_content') or '').strip()
        if 4 <= len(c) <= 200:
            texts.append(c)
    if len(texts) >= 10:
        dep_female.append(texts)
print(f'可用的抑郁女性用户: {len(dep_female)}')

random.shuffle(dep_female)
dep_keep = dep_female[:24]
dep_rows = []
uid = 9000300000
for texts in dep_keep:
    for c in texts[:100]:
        dep_rows.append({'text': c, 'label': 'female', 'user_id': uid,
                         'group_id': 0, 'time': 0, 'source': 'weibo-dep'})
    uid += 1
with open('data/weibo-dep-female.jsonl', 'w', encoding='utf-8') as f:
    for r in dep_rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'抑郁: 24 用户, {len(dep_rows)} 条')

# --- 合成 ---
_, syn_users = load('data/synth-female-v2.jsonl')
print(f'合成: {len(syn_users)} 用户')

# 汇总
n_wb = 24
n_dep = 24
n_syn = len(syn_users)
total_ext = n_wb + n_dep + n_syn
print(f'\n外部用户: 微博{n_wb} + 抑郁{n_dep} + 合成{n_syn} = {total_ext} | 真实: 60')
print(f'外部采样占比(用户级平权): {total_ext/(total_ext+60)*100:.0f}%')
print(f'微博vs抑郁 用户数比: {n_wb}:{n_dep} = 1:1')
