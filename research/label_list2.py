# -*- coding: utf-8 -*-
"""label_list2.py — 按样本量排序的标注推荐清单

筛选逻辑：
  保留：P(女)>=0.25（边界/偏女）或 有冲突信号 或 萌系指数高 或 未达标但样本可观
  剔除：稳定男侧（P<0.15 且无冲突）→ 标注价值低
排序：消息数降序
"""
import csv
import json
import sys

from integrate_indices import compute as compute_indices

# 参考包（含指数+提示+翻案标记）
ref = {}
with open('outputs/标定参考包.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ref[int(r['QQ号'])] = r

# v7 打分（含 std/置信度）
scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

# 多模型票型
votes = {}
with open('outputs/score-multi.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        votes[int(r['user_id'])] = r

# 已标注
import sqlite3
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labeled = set(r['user_id'] for r in conn.execute(
    "SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')"))
nicks = {}
for r in conn.execute('SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id'):
    nicks[r['user_id']] = r['n']
cards = {}
for r in conn.execute("""SELECT user_id, card FROM messages WHERE card IS NOT NULL AND card != ''
                         GROUP BY user_id ORDER BY MAX(time) DESC"""):
    cards.setdefault(r['user_id'], r['card'])
nets = {}
for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
    nets[r['user_id']] = r['network_gender']
conn.close()

items = []
for uid, sc in scores.items():
    if uid in labeled:
        continue
    p = float(sc['prob_female_mean'])
    n = int(sc['n_messages'])
    if n < 30:
        continue
    v = votes.get(uid, {})
    r = ref.get(uid, {})
    moe = float(r['萌系指数']) if r.get('萌系指数') else 0.0
    ero_max = r.get('涩情max', '?')
    hint = r.get('提示', '')
    net_cn = {'male': '男', 'female': '女', 'none': '无标签'}
    net = net_cn.get(r.get('网络性别') or nets.get(uid, 'none'), nets.get(uid, '—') or '—')
    nick = r.get('昵称') or nicks.get(uid, '')
    card = r.get('群名片') or cards.get(uid, '')
    flip = r.get('v6v7翻案', '')
    net_conflict = '⚠️' in hint or flip == '是'
    msi, ri = compute_indices(uid)
    # 值得标注：偏女/边界/冲突/萌系高
    keep = (p >= 0.25) or (p >= 0.15 and net_conflict) or moe >= 0.35
    if not keep:
        continue
    items.append({
        'uid': uid, 'nick': nick, 'card': card,
        'n': n, 'p': p, 'pred': sc['predicted'], 'conf': sc['confidence'],
        'std': sc['prob_female_std'], 'net': net,
        'eromax': ero_max, 'moe': moe, 'votes': f"{v.get('votes_male','?')}男{v.get('votes_female','?')}女",
        'flip': flip, 'hint': hint, 'msi': msi, 'ri': ri,
    })

items.sort(key=lambda x: (-x['ri'], -x['msi'], -x['n']))
print(f'值得标注用户: {len(items)} 人（按 复核指数→男侧证据指数 排序）\n')
print('| QQ号 | 昵称 | 群名片 | 消息数 | P(女) | 结论 | RI复核 | MSI男侧 | 票型 | 翻案 | 提示 |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for it in items:
    print(f'| {it["uid"]} | {it["nick"]} | {it["card"]} | {it["n"]} | {it["p"]:.3f} | {it["pred"]} | '
          f'{it["ri"]:.0f} | {it["msi"]:.0f} | {it["votes"]} | {it["flip"] or "-"} | {it["hint"][:34]} |')

with open('outputs/标注推荐_按样本量.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['QQ号', '昵称', '群名片', '消息数', 'P(女)', '模型结论', '置信度', 'std', '网络性别',
                '涩情max', '萌系指数', '票型', '翻案', 'RI复核指数', 'MSI男侧指数', '提示'])
    for it in items:
        w.writerow([it['uid'], it['nick'], it['card'], it['n'], round(it['p'], 3), it['pred'], it['conf'],
                    it['std'], it['net'], it['eromax'], round(it['moe'], 2), it['votes'], it['flip'],
                    f'{it["ri"]:.0f}', f'{it["msi"]:.0f}', it['hint']])
print(f'\n[完成] → outputs/标注推荐_按样本量.csv')
