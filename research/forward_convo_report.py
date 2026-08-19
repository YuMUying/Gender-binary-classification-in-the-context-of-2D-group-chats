# -*- coding: utf-8 -*-
"""forward_convo_report.py — 整理私聊合并转发中的双人对话并登记性别标签

用法：
  python research/forward_convo_report.py --party-a 2633083674 --party-b 2956792638 \
      --name-b Buchi --gender-b female --margin-hours 2 --out outputs/Buchi对话整理.md
"""
import argparse
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--party-a', type=int, required=True)
    ap.add_argument('--party-b', type=int, required=True)
    ap.add_argument('--name-b', default='')
    ap.add_argument('--gender-b', default=None, choices=['male', 'female', None])
    ap.add_argument('--margin-hours', type=float, default=2.0)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
        db_path = json.load(f).get('database', 'data/qqchat.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    b_rows = conn.execute("""
        SELECT * FROM messages WHERE source='forward' AND user_id=?
        ORDER BY time ASC""", (args.party_b,)).fetchall()
    if not b_rows:
        print(f'[!] 未找到 QQ {args.party_b} 的转发内层消息（source=forward）')
        conn.close(); return

    t_min = min(r['time'] for r in b_rows) - int(args.margin_hours * 3600)
    t_max = max(r['time'] for r in b_rows) + int(args.margin_hours * 3600)
    a_rows = conn.execute("""
        SELECT * FROM messages WHERE source='forward' AND user_id=? AND time BETWEEN ? AND ?
        ORDER BY time ASC""", (args.party_a, t_min, t_max)).fetchall()

    def nick_of(uid, rows):
        for r in rows:
            if r['nickname']:
                return r['nickname']
        p = conn.execute('SELECT nickname FROM user_profiles WHERE user_id=?', (uid,)).fetchone()
        return p['nickname'] if p and p['nickname'] else ''

    nick_a = nick_of(args.party_a, a_rows)
    nick_b = nick_of(args.party_b, b_rows)
    all_rows = sorted(a_rows + b_rows, key=lambda r: r['time'])

    cst = timezone(timedelta(hours=8))
    def fmt(t): return datetime.fromtimestamp(t, cst).strftime('%Y-%m-%d %H:%M:%S')
    def day(t): return datetime.fromtimestamp(t, cst).strftime('%Y-%m-%d')

    days = sorted(set(day(r['time']) for r in all_rows))
    per_day = Counter(day(r['time']) for r in all_rows)
    by_party = Counter(r['user_id'] for r in all_rows)
    lens = [len(r['text']) for r in all_rows if r['text']]

    lines = []
    lines.append(f'# 转发对话整理：{nick_a}({args.party_a}) × {nick_b or args.party_b}({args.party_b})')
    lines.append('')
    lines.append(f'- 消息总数：{len(all_rows)} 条（A={by_party[args.party_a]}，B={by_party[args.party_b]}）')
    lines.append(f'- 时间范围：{fmt(all_rows[0]["time"])} ~ {fmt(all_rows[-1]["time"])}（共 {len(days)} 天）')
    lines.append(f'- 日均：{sum(per_day.values()) / max(len(days), 1):.1f} 条；平均消息长度 {sum(lens) / max(len(lens), 1):.0f} 字')
    lines.append(f'- 逐日分布：' + '，'.join(f'{d} {per_day[d]}条' for d in days))
    lines.append('')
    lines.append('## 完整转写')
    lines.append('')
    for r in all_rows:
        who = nick_a if r['user_id'] == args.party_a else (nick_b or str(args.party_b))
        txt = (r['text'] or '').replace('\n', ' ')
        lines.append(f'**[{fmt(r["time"])}] {who}**')
        lines.append(f'> {txt}')
        lines.append('')

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[完成] 对话 {len(all_rows)} 条 → {args.out}')

    # 登记 B 的性别标签
    if args.gender_b:
        existing = conn.execute('SELECT gender FROM speaker_labels WHERE user_id=?', (args.party_b,)).fetchone()
        if existing and existing['gender'] == args.gender_b:
            print(f'[标签] QQ {args.party_b} 已是 {args.gender_b}，无需更新')
        else:
            conn.execute("""
                INSERT INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, label_group, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                  nickname=COALESCE(excluded.nickname, nickname),
                  gender=excluded.gender, label_source=excluded.label_source,
                  label_confidence=excluded.label_confidence,
                  label_group=COALESCE(excluded.label_group, label_group),
                  updated_at=excluded.updated_at
            """, (args.party_b, args.name_b or None, args.gender_b, 'forward-confirm', 'high', None,
                  int(datetime.now().timestamp())))
            conn.commit()
            print(f'[标签] 已登记 QQ {args.party_b} → {args.gender_b}（nickname={args.name_b or "?"}，来源 forward-confirm）')
    conn.close()

if __name__ == '__main__':
    main()
