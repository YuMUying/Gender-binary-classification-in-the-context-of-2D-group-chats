# -*- coding: utf-8 -*-
"""unlabeled_list.py — 群1+群2 达标未标注用户清单（供人工标注）

达标定义：群消息中有效文本（≥4字）≥100 条（与 weak-as-test 阈值一致）
输出 outputs/待标注清单_群1群2.md / .csv
"""
import csv
import sqlite3

MIN_EFF = 100

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 未标注用户（群1或群2有发言）
rows = conn.execute("""
    SELECT m.user_id,
           COUNT(*) c,
           SUM(CASE WHEN LENGTH(m.text) >= 4 THEN 1 ELSE 0 END) eff,
           MAX(m.nickname) nick,
           MAX(m.time) mt
    FROM messages m
    WHERE m.scene='group' AND m.peer_id IN (826904606, 762673304)
      AND m.user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
    GROUP BY m.user_id HAVING eff >= ?""", (MIN_EFF,)).fetchall()

# 群名片（两群各自最新）
def latest_card(uid, gid):
    r = conn.execute("""SELECT card FROM messages WHERE peer_id=? AND user_id=? AND card IS NOT NULL AND card!=''
                        ORDER BY time DESC LIMIT 1""", (gid, uid)).fetchone()
    return r['card'] if r else ''

net = {}
for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
    net[r['user_id']] = r['network_gender']

# v7 打分
scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

# 涩情特征
ero = {}
with open('outputs/erotic_features_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ero[int(r['user_id'])] = r

G_CN = {'male': '男', 'female': '女', 'none': '无标签'}

def priority(p):
    """标注优先级：模型倾向女的用户最优先（可能男声女气，也可能女——都高价值）"""
    if p >= 0.5:
        return '★★★ 模型倾向女'
    if p >= 0.25:
        return '★★ 边界'
    return '★ 稳定男侧'

items = []
for r in rows:
    uid = r['user_id']
    s = scores.get(uid, {})
    if not s:
        continue
    p = float(s['prob_female_mean'])
    pred = s['predicted']
    conf = s['confidence']
    card1 = latest_card(uid, 826904606)
    card2 = latest_card(uid, 762673304)
    e = ero.get(uid, {})
    items.append({
        'uid': uid, 'nick': r['nick'] or '', 'card1': card1, 'card2': card2,
        'n': r['c'], 'eff': r['eff'], 'p': p, 'pred': pred, 'conf': conf,
        'net': net.get(uid, 'none'), 'eromax': e.get('ero_max', '?'),
        'pri': priority(p),
    })

items.sort(key=lambda x: -x['p'])   # 女概率降序：疑似男声女气排最前
conn.close()
print(f'达标未标注用户: {len(items)} 人\n')

lines = ['# 待标注清单（群1+群2，达标未标注用户）', '',
         f'- 达标定义：群消息有效文本(≥4字) ≥ {MIN_EFF} 条',
         '- 按 P(女) 降序排列：排前面的最可能是"男声女气"（模型倾向女），标注价值最高',
         '- 标注命令：node scripts/label.js --user <QQ号> --gender male|female',
         '', '| QQ号 | 昵称 | 群1名片 | 群2名片 | 消息数 | P(女) | 模型结论 | 置信度 | 网络性别 | 涩情max | 优先级 |',
         '|---|---|---|---|---|---|---|---|---|---|---|']
for it in items:
    lines.append(f'| {it["uid"]} | {it["nick"]} | {it["card1"]} | {it["card2"]} | {it["n"]} | {it["p"]:.3f} | '
                 f'{it["pred"]} | {it["conf"]} | {G_CN.get(it["net"], it["net"])} | {it["eromax"]} | {it["pri"]} |')
with open('outputs/待标注清单_群1群2.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

with open('outputs/待标注清单_群1群2.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['QQ号', '昵称', '群1名片', '群2名片', '消息数', 'P(女)', '模型结论', '置信度', '网络性别', '涩情max', '优先级'])
    for it in items:
        w.writerow([it['uid'], it['nick'], it['card1'], it['card2'], it['n'], round(it['p'], 3),
                    it['pred'], it['conf'], it['net'], it['eromax'], it['pri']])

# 摘要
from collections import Counter
print('=== 优先级分布 ===')
print(Counter(it['pri'].split(' ')[0] for it in items))
print('=== P(女)≥0.5（最优先标注）===')
for it in items:
    if it['p'] >= 0.5:
        print(f'  {it["uid"]} {it["nick"]} P(女)={it["p"]:.3f} 预测={it["pred"]} 消息={it["n"]} 网络={it["net"]} 涩情max={it["eromax"]}')
