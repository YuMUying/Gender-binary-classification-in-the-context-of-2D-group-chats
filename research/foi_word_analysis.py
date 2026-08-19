# -*- coding: utf-8 -*-
"""foi_word_analysis.py — 对比 阳性用户 vs 高FOI正常男 的萌系/男娘话题实际用词"""
import re
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

pos_users = {375569635, 439161815, 443628409, 963653008, 1046636617, 1197677845, 2633083674, 2948988043, 3189511804}
# 高 FOI 正常男（从全库 TOP 取未标注的）
high_normal = {2429967889, 1220384810, 1717582, 3541215132, 2957772437, 2933474490, 1399716483}

def word_counts(uids):
    counter = Counter()
    n = 0
    for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
        if r['user_id'] not in uids:
            continue
        n += 1
        t = r['text'] or ''
        # 萌系语气词精确统计
        for w in re.findall(r'(捏|喵|呜|嘤|诶嘿|嘿嘿|啦~|呀~|叭|嘛~|呢~|呜呜|嘤嘤|qwq|QAQ|TAT|OvO|OwO|>_<)', t):
            counter[w] += 1
    return counter, n

pos_c, pos_n = word_counts(pos_users)
hi_c, hi_n = word_counts(high_normal)

print("=== 萌系语气词频（每千条消息） ===")
words = set(pos_c) | set(hi_c)
print(f"{'词':<8} {'阳性/千条':<12} {'高FOI正常男/千条':<16}")
for w in sorted(words, key=lambda x: -(pos_c[x] / pos_n)):
    pos_rate = pos_c[w] / pos_n * 1000
    hi_rate = hi_c[w] / hi_n * 1000
    ratio = pos_rate / hi_rate if hi_rate > 0 else float('inf')
    print(f"{w:<8} {pos_rate:<12.2f} {hi_rate:<16.2f} (比值 {ratio:.1f})")

print()
print("=== 男娘话题词频（每千条） ===")
topic_words = ['女装', '伪娘', '男娘', '药娘', '女装大佬', '穿裙', '黑丝', '白丝', '丝袜', '小裙子', 'jk', 'lo裙']
for w in topic_words:
    pat = re.compile(w)
    pc = sum(1 for r in conn.execute("SELECT text FROM messages WHERE user_id IN (SELECT user_id FROM speaker_labels WHERE user_id IN (%s)) AND text LIKE ?" % ','.join('?'*len(pos_users)), tuple(['%'+w+'%']*len(pos_users)))) if False else None
    # 简化：直接 LIKE
    pc = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id IN (%s) AND text LIKE ?" % ','.join(['?']*len(pos_users)), tuple(list(pos_users) + ['%'+w+'%'])).fetchone()[0]
    hc = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id IN (%s) AND text LIKE ?" % ','.join(['?']*len(high_normal)), tuple(list(high_normal) + ['%'+w+'%'])).fetchone()[0]
    print(f"{w:<10} 阳性={pc}  高FOI正常男={hc}")

conn.close()
