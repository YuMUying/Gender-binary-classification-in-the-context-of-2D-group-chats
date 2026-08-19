# -*- coding: utf-8 -*-
"""threeway_report.py — 三方对照表：人工标注 × 网络资料性别 × 模型判断

用法: python research/threeway_report.py [--min-msgs 30]
"""
import argparse
import csv
import json
import os
import sqlite3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-msgs', type=int, default=30)
    ap.add_argument('--score', default='outputs/score-v7-all.csv')
    ap.add_argument('--out', default='outputs/三方对照表.md')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    conn = sqlite3.connect(os.path.join(root, 'data/qqchat.db'))
    conn.row_factory = sqlite3.Row

    # 网络性别
    net = {}
    for r in conn.execute('SELECT user_id, network_gender, source FROM profile_genders'):
        net[r['user_id']] = {'g': r['network_gender'], 'src': r['source']}
    # 人工标注 + 昵称
    label = {}
    for r in conn.execute("SELECT user_id, gender, label_confidence FROM speaker_labels WHERE gender IN ('male','female')"):
        label[r['user_id']] = r['gender']
    nick = {}
    for r in conn.execute('SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id'):
        nick[r['user_id']] = r['n']
    conn.close()

    # 模型打分
    score = {}
    with open(os.path.join(root, args.score), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            score[int(row['user_id'])] = row

    G_CN = {'male': '男', 'female': '女', 'none': '无标签'}

    lines = []
    lines.append('# 三方对照表（人工标注 × 网络资料性别 × 模型判断 v7）')
    lines.append('')
    lines.append('网络性别来源：NapCat get_stranger_info（用户自报，仅供参考）+ 2 条人工覆盖（星辞=女、Buchi=无标签）')
    lines.append(f'打分阈值：0.870（bert-v7 metrics.json）')
    lines.append('')

    # ---- 一、已标注用户 ----
    lines.append('## 一、已标注用户（人工标注为真值基准）')
    lines.append('')
    lines.append('| QQ号 | 昵称 | 人工标注 | 网络性别 | 模型判断 | P(女) | 消息数 | 冲突标记 |')
    lines.append('|---|---|---|---|---|---|---|---|')
    n_conf = 0
    n_both = 0
    for uid in sorted(label):
        l = label[uid]
        g = net.get(uid, {}).get('g', '?')
        s = score.get(uid)
        if not s or int(s['n_messages']) < args.min_msgs:
            continue
        pred = s['predicted']
        p = float(s['prob_female_mean'])
        marks = []
        if g in ('male', 'female') and g != l:
            marks.append('⚠️人工×网络冲突')
            n_conf += 1
        if pred != l:
            marks.append('❌模型×人工冲突')
        if not marks and g == l:
            n_both += 1
        lines.append(f'| {uid} | {nick.get(uid, "?")} | {G_CN.get(l, l)} | {G_CN.get(g, g)} | {pred} | {p:.3f} | {s["n_messages"]} | {"；".join(marks) if marks else "—"} |')
    lines.append('')
    lines.append(f'（已标注且≥{args.min_msgs}条用户中：人工×网络冲突 {n_conf} 人，人工=网络=模型三方一致 {n_both} 人）')
    lines.append('')

    # ---- 二、未标注用户：模型高置信 + 网络性别非空 ----
    lines.append('## 二、未标注用户（模型高置信且网络性别已知，供伪标签/复核参考）')
    lines.append('')
    lines.append('| QQ号 | 昵称 | 网络性别 | 模型判断 | P(女) | 消息数 | 建议 |')
    lines.append('|---|---|---|---|---|---|---|')
    rows2 = []
    for uid, info in net.items():
        if uid in label or info['g'] in ('none', '?', None):
            continue
        s = score.get(uid)
        if not s or int(s['n_messages']) < args.min_msgs:
            continue
        p = float(s['prob_female_mean'])
        pred = s['predicted']
        agree = (info['g'] == pred)
        conf = s['confidence']
        if conf != 'high':
            continue
        adv = ''
        if agree:
            adv = '✅可考虑伪标签'
        else:
            adv = '⚠️网络与模型冲突，需复核'
        rows2.append((uid, nick.get(uid, '?'), info['g'], pred, p, s['n_messages'], adv))
    rows2.sort(key=lambda r: -r[4])
    for uid, n, g, pred, p, m, adv in rows2:
        lines.append(f'| {uid} | {n} | {G_CN.get(g, g)} | {pred} | {p:.3f} | {m} | {adv} |')
    lines.append('')

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(os.path.join(root, args.out), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[完成] → {args.out}')
    print(f'  已标注用户冲突: {n_conf} 人（人工×网络）')
    print(f'  未标注高置信候选: {len(rows2)} 人（其中一致 {sum(1 for r in rows2 if "可考虑" in r[6])} 人）')

if __name__ == '__main__':
    main()
