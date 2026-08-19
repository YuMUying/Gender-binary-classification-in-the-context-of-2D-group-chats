# -*- coding: utf-8 -*-
"""net_style_corr.py — 实测：网络性别 × 用户风格(p_female) × 真值 的相关性

验证两个问题：
  Q1: 已标注用户中，真值=男 的用户是否更爱把资料设成女？（萌系男现象的统计基础）
  Q2: 真值=男 且 网络=女 的用户，其风格(p_female)是否系统性更偏女？
      ——若是，则"网络=女"可作为萌系男风险的先验信号，值得做阈值调整
"""
import csv
import statistics
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
net = {}
for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
    net[r['user_id']] = r['network_gender']
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']
conn.close()

scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

# 已标注且有打分的用户（全部，含低消息数）
users = []
for uid, t in labels.items():
    s = scores.get(uid)
    if not s:
        continue
    users.append({
        'uid': uid, 'true': t,
        'net': net.get(uid, 'none') or 'none',
        'p': float(s['prob_female_mean']),
        'std': float(s.get('prob_female_std') or 0),
        'n': int(s['n_messages']),
    })

print(f'已标注且有打分: {len(users)} 人\n')

# Q1: 真值 × 网络 交叉表
print('=== Q1: 真值 × 网络性别 交叉表（人数）===')
for t in ('male', 'female'):
    grp = [u for u in users if u['true'] == t]
    from collections import Counter
    c = Counter(u['net'] for u in grp)
    print(f'真值={t} ({len(grp)}人): 网男={c.get("male", 0)} 网女={c.get("female", 0)} 无标签={c.get("none", 0)}')
print()

# Q2: 真值=男 按网络分组看风格
print('=== Q2: 真值=男 用户按网络性别分组的 P(女) 分布 ===')
for g in ('male', 'female', 'none'):
    grp = [u for u in users if u['true'] == 'male' and u['net'] == g]
    if grp:
        ps = [u['p'] for u in grp]
        print(f'网络={g} ({len(grp)}人): P(女)均值={statistics.mean(ps):.3f} 范围=[{min(ps):.3f},{max(ps):.3f}]')
        for u in sorted(grp, key=lambda x: -x['p']):
            print(f'    {u["uid"]} {u["p"]:.3f} (n={u["n"]})')
print()

print('=== Q2b: 真值=女 用户按网络性别分组的 P(女) 分布 ===')
for g in ('male', 'female', 'none'):
    grp = [u for u in users if u['true'] == 'female' and u['net'] == g]
    if grp:
        ps = [u['p'] for u in grp]
        print(f'网络={g} ({len(grp)}人): P(女)均值={statistics.mean(ps):.3f} 范围=[{min(ps):.3f},{max(ps):.3f}]')
print()

# Q3: 阈值调整策略对比（留一法）
print('=== Q3: 决策策略对比（留一法，全部已标注用户）===')
# 策略A: 全局阈值 0.870
# 策略B: 网络=女 的用户阈值提高到 0.93（萌系男防御），其余 0.870
# 策略C: 网络=女 阈值 0.95，网络=男 阈值 0.80（双向利用），其余 0.870
strategies = {
    'A 全局0.870': lambda net: 0.870,
    'B 网女0.93/其余0.870': lambda net: 0.93 if net == 'female' else 0.870,
    'C 网女0.95/网男0.80/其余0.870': lambda net: 0.95 if net == 'female' else (0.80 if net == 'male' else 0.870),
    'D 网女0.90/网男0.90/其余0.870': lambda net: 0.90 if net in ('female', 'male') else 0.870,
}
for name, th_fn in strategies.items():
    correct = 0
    for u in users:
        th = th_fn(u['net'])
        pred = 'female' if u['p'] >= th else 'male'
        if pred == u['true']:
            correct += 1
    print(f'{name}: {correct}/{len(users)} = {correct/len(users):.1%}')
