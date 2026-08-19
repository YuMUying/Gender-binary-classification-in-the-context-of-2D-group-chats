# -*- coding: utf-8 -*-
"""weibo_prep2.py — 提取女性微博文本 → jsonl + 域偏移统计"""
import csv
import json
import os
import re

ROOT = r'G:\Deepseek\e8784-extract\weibo'
OUT = r'G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\data\weibo-female.jsonl'

CJK = re.compile(r'[\u4e00-\u9fff]')
# 群聊风格信号（与 speech_index 一致）
SIG = {
    '粗口': re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦|草了'),
    '性发泄': re.compile(r'操死|干死|操你|干你|草你|艹你|肏|日你|想操|想干|想日|射你|舔你|吸你|上你|扑倒'),
    '叫老婆': re.compile(r'老公|老婆|宝[宝贝]|亲爱的'),
    '萌系': re.compile(r'呢|啦|喵|捏|嗷|呀|嘛|惹|滴|的说|呜呜|嘤嘤|诶嘿|嘻嘻|QAQ|qwq'),
}

rows_out = []
n_text = 0
n_short = 0
sig_count = {k: 0 for k in SIG}
uid = 9000200000  # 隔离段

for gender in ('female', 'male'):
    for user_dir in os.listdir(os.path.join(ROOT, gender)):
        d = os.path.join(ROOT, gender, user_dir)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.csv'):
                continue
            with open(os.path.join(d, fn), encoding='utf-8-sig', errors='replace') as f:
                rd = csv.reader(f)
                try:
                    header = next(rd)
                    # 定位"正文"列
                    try:
                        ti = header.index('正文')
                    except ValueError:
                        continue
                except Exception:
                    continue
                for row in rd:
                    if len(row) <= ti:
                        continue
                    t = (row[ti] or '').strip()
                    if not t or len(t) < 4:
                        continue
                    if not CJK.search(t):
                        continue
                    # 过滤明显非自然语言（链接/纯话题）
                    if re.match(r'^[#@].*$', t):
                        continue
                    if len(t) > 200:
                        t = t[:200]
                    n_text += 1
                    if len(t) <= 12:
                        n_short += 1
                    for k, pat in SIG.items():
                        if pat.search(t):
                            sig_count[k] += 1
                    if gender == 'female':
                        rows_out.append({'text': t, 'label': 'female', 'user_id': uid, 'group_id': 0,
                                         'time': 0, 'source': 'weibo'})
                        uid += 1

print(f'有效文本行: {n_text}（其中短句<=12字: {n_short}）')
print(f'风格信号占比(全量):')
for k in SIG:
    print(f'  {k}: {sig_count[k]}/{n_text} = {sig_count[k]/max(n_text,1):.4f}')
print(f'\n女性样本: {len(rows_out)} 条 → {OUT}')
with open(OUT, 'w', encoding='utf-8') as f:
    for r in rows_out:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
