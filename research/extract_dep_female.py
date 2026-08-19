# -*- coding: utf-8 -*-
"""extract_dep_female.py — 从 WU3D 提取抑郁女性用户推文（雪々风格增强）

筛选：gender=女 AND label=1（抑郁）
每用户最多 MAX_PER_USER 条（用户级平权）
输出: data/weibo-dep-female.jsonl（user_id 9000300000+ 隔离段）
"""
import json
import os
import re

SRC = r'G:\Deepseek\WU3D\depressed.json'
OUT = 'data/weibo-dep-female.jsonl'
MAX_PER_USER = 50
MAX_USERS = 2000

CJK = re.compile(r'[\u4e00-\u9fff]')

def main():
    print(f'加载 {SRC} ...')
    with open(SRC, encoding='utf-8') as f:
        users = json.load(f)
    print(f'抑郁用户总数: {len(users)}')

    out_rows = []
    uid = 9000300000
    n_users = 0
    for u in users:
        if n_users >= MAX_USERS:
            break
        g = str(u.get('gender') or '')
        if g != '女':
            continue
        tweets = u.get('tweets') or []
        texts = []
        for t in tweets:
            c = str(t.get('tweet_content') or '').strip()
            if 4 <= len(c) <= 200 and CJK.search(c):
                texts.append(c)
        if len(texts) < 5:
            continue
        # 每用户最多 MAX_PER_USER 条
        for c in texts[:MAX_PER_USER]:
            out_rows.append({'text': c, 'label': 'female', 'user_id': uid,
                             'group_id': 0, 'time': 0, 'source': 'weibo-dep'})
        n_users += 1
        uid += 1
        if n_users % 200 == 0:
            print(f'  已处理 {n_users} 用户, {len(out_rows)} 条')

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n[完成] 抑郁女性用户 {n_users} 个, 推文 {len(out_rows)} 条 → {OUT}')

if __name__ == '__main__':
    main()
