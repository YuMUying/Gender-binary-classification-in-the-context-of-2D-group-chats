# -*- coding: utf-8 -*-
"""rebuild_balanced3.py — 抑郁用户 = 微博用户的 1/3（8 用户）+ 风格偏移审查

配置：微博 24 用户 / 抑郁 8 用户（1/3）/ 合成 6 用户
审查：真实女性 vs 微博女 vs 抑郁女 风格指数对比
"""
import json
import random
import re

random.seed(42)

# ========== 1. 抑郁: 8 用户 × 100 条 ==========
SRC_DEP = r'G:\Deepseek\WU3D\depressed.json'
with open(SRC_DEP, encoding='utf-8') as f:
    dep_all = json.load(f)

dep_female = []
for u in dep_all:
    g = str(u.get('gender') or '')
    if g != '女':
        continue
    tweets = u.get('tweets') or []
    texts = [str(t.get('tweet_content') or '').strip() for t in tweets]
    texts = [c for c in texts if 4 <= len(c) <= 200]
    if len(texts) >= 10:
        dep_female.append(texts)
print(f'可用抑郁女性用户: {len(dep_female)}')

random.shuffle(dep_female)
dep_rows = []
uid = 9000300000
for texts in dep_female[:8]:
    for c in texts[:100]:
        dep_rows.append({'text': c, 'label': 'female', 'user_id': uid,
                         'group_id': 0, 'time': 0, 'source': 'weibo-dep'})
    uid += 1
with open('data/weibo-dep-female.jsonl', 'w', encoding='utf-8') as f:
    for r in dep_rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'抑郁: 8 用户, {len(dep_rows)} 条')

# ========== 2. 风格偏移审查 ==========
def load_rows(path):
    return [json.loads(l) for l in open(path, encoding='utf-8')]

wb_rows = load_rows('data/weibo-female.jsonl')
syn_rows = load_rows('data/synth-female-v2.jsonl')

# 真实女性（群聊）
import sqlite3
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
real_f = [r['text'] for r in conn.execute("""
    SELECT m.text FROM messages m JOIN speaker_labels l ON l.user_id=m.user_id
    WHERE l.gender='female' AND LENGTH(m.text) >= 4 AND m.text NOT LIKE '[%'""")]
real_m = [r['text'] for r in conn.execute("""
    SELECT m.text FROM messages m JOIN speaker_labels l ON l.user_id=m.user_id
    WHERE l.gender='male' AND LENGTH(m.text) >= 4 AND m.text NOT LIKE '[%'""")]
conn.close()

PATS = {
    '粗口': re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦|草了'),
    '性发泄': re.compile(r'操死|干死|操你|干你|草你|艹你|肏|日你|想操|想干|想日|射你|舔你|吸你|上你|扑倒'),
    '叫老婆': re.compile(r'老公|老婆|宝[宝贝]|亲爱的'),
    '萌系': re.compile(r'呢|啦|喵|捏|嗷|呀|嘛|惹|滴|的说|呜呜|嘤嘤|诶嘿|嘻嘻|QAQ|qwq|ovo'),
    'emo': re.compile(r'emo|玉玉|破防|麻了|好累|心累|想死|不想活|孤独|寂寞|空虚|想哭|难过|抑郁|小丑|深夜emo'),
    '抽象': re.compile(r'草|乐|典|绷|蚌|麻了|难绷|哈人|流汗|笑死|逆天|蚌埠'),
    '颜文字': re.compile(r'[（(].{0,6}[︶﹏︿•́_•̀ㅂ￣▽▽﹏︿‿◡>﹏︵╥╯□╰눈_눈◕‿◕•̀ㅂ•́].{0,6}[）)]|QAQ|qwq|ovo|TAT|Orz'),
}

def profile(name, texts):
    n = len(texts)
    if not n:
        return
    out = {'n': n, '均长': sum(len(t) for t in texts) / n}
    for k, pat in PATS.items():
        out[k] = sum(1 for t in texts if pat.search(t)) / n
    out['超短句率(≤8字)'] = sum(1 for t in texts if len(t) <= 8) / n
    print(f'{name} (n={n}): ' + ' '.join(f'{k}={v:.4f}' for k, v in out.items()))

print('\n===== 风格偏移审查 =====')
profile('真实群聊女性', real_f)
profile('真实群聊男性', real_m)
profile('微博女性(24用户)', [r['text'] for r in wb_rows])
profile('抑郁女性(8用户)', [r['text'] for r in dep_rows])
profile('LLM合成(6风格)', [r['text'] for r in syn_rows])
