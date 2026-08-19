# -*- coding: utf-8 -*-
"""foi_features.py — FOI 特征区分度验证：orientation 标签用户 vs 正常男性
统计各特征率，看哪些特征能把 男娘/双/同性恋 用户从正常男性中分出来"""
import re
import sqlite3

# 特征模式
FEATURES = {
    '萌系语气': re.compile(r'(捏|喵|呜|嘤|诶嘿|嘿嘿|啦~|~$|呀~|叭|嘛~|呢~)'),
    '自称女性': re.compile(r'(人家|咱家|本小姐|伦家|奴家|妾身|本宫)'),
    '男娘话题': re.compile(r'(女装|伪娘|男娘|药娘|女装大佬|穿裙|jk|lo裙|黑丝|白丝)'),
    '同性恋话题': re.compile(r'(南通|基佬|基|弯了|弯的|老公|处对象|对象|gay|bl|耽美|男同)'),
    '撒娇示弱': re.compile(r'(求求|抱抱|贴贴|要亲亲|要抱|好想要|委屈|嘤嘤|撒娇|哄哄|摸摸头)'),
    '百合BL': re.compile(r'(百合|gl|耽美|同人女|嗑cp|磕cp|cp粉)'),
}

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# orientation 用户（男娘/双/同性恋 = 目标阳性）
orient_users = set()
for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    orient_users.add(r['user_id'])
# 正常男性（有 male 标签且无 orientation）
normal_male = set()
for r in conn.execute("SELECT user_id FROM speaker_labels WHERE gender='male'"):
    if r['user_id'] not in orient_users:
        normal_male.add(r['user_id'])

print(f"orientation 用户数: {len(orient_users)}: {sorted(orient_users)}")
print(f"正常男性用户数: {len(normal_male)}")

# 逐用户统计特征率
def stats_users(uids):
    result = {}
    for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
        uid = r['user_id']
        if uid not in uids:
            continue
        s = result.setdefault(uid, {'n': 0, **{k: 0 for k in FEATURES}})
        s['n'] += 1
        t = r['text'] or ''
        for k, pat in FEATURES.items():
            if pat.search(t):
                s[k] += 1
    return result

o_stats = stats_users(orient_users)
n_stats = stats_users(normal_male)

def avg_rates(stats, n_users):
    """人均特征率（先按用户归一，再平均）"""
    sums = {k: 0.0 for k in FEATURES}
    cnt = 0
    for uid, s in stats.items():
        if s['n'] == 0:
            continue
        cnt += 1
        for k in FEATURES:
            sums[k] += s[k] / s['n']
    for k in FEATURES:
        sums[k] /= max(cnt, 1)
    return sums, cnt

o_avg, o_cnt = avg_rates(o_stats, orient_users)
n_avg, n_cnt = avg_rates(n_stats, normal_male)

print(f"\n{'特征':<10} {'orientation均率':<16} {'正常男均率':<16} {'比值':<8}")
print('-' * 56)
for k in FEATURES:
    ratio = o_avg[k] / n_avg[k] if n_avg[k] > 0 else float('inf')
    marker = ' ***' if ratio >= 2 else (' **' if ratio >= 1.5 else '')
    print(f"{k:<10} {o_avg[k]:<16.6f} {n_avg[k]:<16.6f} {ratio:<8.2f}{marker}")

conn.close()
