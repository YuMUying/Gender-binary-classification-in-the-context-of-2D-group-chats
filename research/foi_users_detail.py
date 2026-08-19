# -*- coding: utf-8 -*-
"""foi_users_detail.py — 每个 orientation 用户的特征明细 + 优化模式区分度"""
import re
import sqlite3

# 优化后的模式：同性恋话题聚焦特定词（排除"对象"等泛化用法）
FEATURES = {
    '萌系语气': re.compile(r'(捏|喵|呜|嘤|诶嘿|嘿嘿|啦~|呀~|叭|嘛~|呢~|呜呜|嘤嘤)'),
    '自称女性': re.compile(r'(人家|咱家|本小姐|伦家|奴家|妾身|本宫|小妹)'),
    '男娘话题': re.compile(r'(女装|伪娘|男娘|药娘|女装大佬|穿裙|jk裙|lo裙|黑丝|白丝|丝袜|小裙子)'),
    '同性恋话题': re.compile(r'(南通|基佬|弯了|弯的|gay|耽美|男同|给子|txl|通讯录)'),
    '撒娇示弱': re.compile(r'(求求|抱抱|贴贴|要亲亲|要抱抱|好想要|委屈|哄哄|摸摸头|撒娇)'),
    '百合BL': re.compile(r'(百合|gl向|耽美|同人女|嗑cp|磕cp)'),
    '颜文字': re.compile(r'(\(*≧▽≦\)*|\(*＞﹏＜\)*|\(*´∀`\)*|\(*｡>﹏<｡\)*|qwq|QAQ|TAT|Orz|OvO|OwO|>_<|T_T)'),
}

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

orient = {}
for r in conn.execute("SELECT user_id, gender, orientation, nickname FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    orient[r['user_id']] = dict(r)

normal_male = set(r['user_id'] for r in conn.execute(
    "SELECT user_id FROM speaker_labels WHERE gender='male'")) - set(orient.keys())

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

o_stats = stats_users(set(orient.keys()))
n_stats = stats_users(normal_male)

print("=== 每个 orientation 用户特征率 ===")
print(f"{'UID':<12} {'标签':<8} {'消息数':<7} " + ' '.join(f"{k[:4]}" for k in FEATURES))
for uid, info in sorted(orient.items()):
    s = o_stats.get(uid, {'n': 0, **{k: 0 for k in FEATURES}})
    n = max(s['n'], 1)
    rates = ' '.join(f"{s[k]/n:.3f}" for k in FEATURES)
    print(f"{uid:<12} {info['orientation']:<8} {s['n']:<7} {rates}")

print()
print("=== 群体对比（优化后模式） ===")
def avg_rates(stats):
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

oa, oc = avg_rates(o_stats)
na, nc = avg_rates(n_stats)
for k in FEATURES:
    ratio = oa[k] / na[k] if na[k] > 0 else float('inf')
    print(f"{k:<8} orient={oa[k]:.5f}  normal={na[k]:.5f}  比值={ratio:.2f}")

conn.close()
