# -*- coding: utf-8 -*-
"""gender_declare.py — 性别自述检测：正则高召回匹配 → gpt-5.5 判定（事实性/玩笑）

输出 research/gender_declare_labels.jsonl：{id, user_id, text, declared, factual, conf}
  declared: male/female/none
  factual: yes/no/uncertain（是否陈述事实——排除玩梗/角色扮演/被迫自称）
  conf: 0-1 置信度
用法: $env:RELAY_KEY='sk-...'; python research/gender_declare.py
"""
import json
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
OUT = 'research/gender_declare_labels.jsonl'

# 高召回正则：明确的第一人称性别表述
PAT = re.compile(
    r'我是(?:一个|个|名)?(?:男生|男生|男的|男人|爷们|汉子|大老爷们|直男|基佬|gay|les|百合|同|妹子|女生|女的|女人|小萝莉|loli|LOLI|萝莉|阿姨|大叔|哥哥|弟弟|姐姐|妹妹|小男孩|小女孩)|'
    r'我(?:性别|是)[:：]?(?:男|女)|'
    r'本(?:男|直男|女|小姐|大爷)|'
    r'老娘(?:是|就)|'
    r'我(?:男|女)(?:朋友|友|票|盆友)|'
    r'我(?:前|现)?(?:男友|女友|男朋友|女朋友)|'
    r'我(?:老公|老婆|对象)(?:是|他|她)|'
    r'我(?:大概|应该|可能|确实|确定|保证|真的)是(?:个|名)?(?:男的|女的|男生|女生)|'
    r'我是(?:个)?(?:男|女)的'
)

BATCH = 15
PROMPT = """下面是一批QQ聊天消息（编号:文本）。每条可能包含第一人称的性别表述。
请判定每条：是否含性别自述、自述性别、以及是否在陈述事实。
输出JSON数组，每项{"i":编号,"declared":"male或female或none","factual":"yes或no或uncertain","conf":0到1,"r":"一句话原因"}：
- 自述必须是我方（说话人）自身性别的陈述：如"我是男生""我是女的""我前女友如何如何"（暗示自述性别为男）"我男朋友..."（暗示为女）。
- factual=yes 表示这是陈述现实事实；以下情况判 no：明显玩梗/角色扮演/二次元人设（如"我是小萝莉"在群聊玩梗语境）、被迫自称（为满足群友玩笑而说"我是萝莉"）、反问/假设句（"我是男的话..."）、虚构叙事。
- 无法判断语境时 factual=uncertain，conf 相应降低。
只输出JSON数组。"""


def judge_batch(items, retries=3):
    lines = '\n'.join(f'{i}:{t[:130]}' for i, t in items)
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': PROMPT + '\n\n' + lines}],
        'max_tokens': 2000,
        'temperature': 0,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('['); e = content.rfind(']')
            if s >= 0 and e > s:
                arr = json.loads(content[s:e + 1])
                return {int(x['i']): x for x in arr if isinstance(x, dict) and 'i' in x}
            return {}
        except Exception as ex:
            if attempt == retries - 1:
                print(f'  批判定失败: {ex}')
                return {}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0").fetchall()
    conn.close()
    print(f'总消息: {len(rows)}')

    matched = [(r['id'], r['user_id'], r['text']) for r in rows if PAT.search(r['text'] or '')]
    print(f'正则命中: {len(matched)}')

    done_ids = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            l = l.strip()
            if l:
                done_ids.add(json.loads(l)['id'])
    todo = [m for m in matched if m[0] not in done_ids]
    print(f'待判定: {len(todo)}（已完成 {len(done_ids)}）')

    def work(item):
        mid, uid, t = item
        return mid, uid, t, judge_batch([(0, t)]).get(0)

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            mid, uid, t, res = fut.result()
            if res and res.get('declared') in ('male', 'female'):
                results.append({'id': mid, 'user_id': uid, 'text': t[:200],
                                'declared': res['declared'],
                                'factual': res.get('factual', 'uncertain'),
                                'conf': float(res.get('conf', 0.5)),
                                'reason': res.get('r', '')[:80]})
            done += 1
            if done % 150 == 0 or done == len(todo):
                print(f'进度 {done}/{len(todo)}')
            if done % 150 == 0:
                with open(OUT, 'a', encoding='utf-8') as f:
                    for rec in results:
                        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                results = []
    with open(OUT, 'a', encoding='utf-8') as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    from collections import Counter
    allr = [json.loads(l) for l in open(OUT, encoding='utf-8') if l.strip()]
    print(f'\n[完成] 累计 {len(allr)} 条')
    print('自述性别:', dict(Counter(r['declared'] for r in allr)))
    print('事实性:', dict(Counter(r['factual'] for r in allr)))


if __name__ == '__main__':
    main()
