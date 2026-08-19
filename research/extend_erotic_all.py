# -*- coding: utf-8 -*-
"""extend_erotic_all.py — 扩展涩情标注到全库用户（补足 2/3 级样本）

对未标注用户的全部关键词命中消息做 gpt-5.5 判定，追加到 research/erotic_labels.jsonl。
用法: $env:RELAY_KEY='sk-...'; python research/extend_erotic_all.py
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
OUT = 'research/erotic_labels.jsonl'

KW = re.compile(
    r'涩|色(?!彩|块|系|调|盲)|欲|本子|裸|胸|乳|福利|内裤|裤衩|罩|操|艹|高潮|射|液|发情|色批|好涩|色色|涩涩|'
    r'黄油|里番|黄文|黄图|女装(?!大)|腿(?!本)|白丝|黑丝|绝对领域|泳装|性感|诱惑|媚|烧|骚|湿|硬了|丁丁|批|吊|'
    r'做爱|口交|肛|龟头|阴道|精子|爱液|约炮|炮友|援交|同人(?!志)|瑟瑟|想艹|肏|干你|草你|上你|扑倒|'
    r'扒衣|摸胸|揉|内射|体外|无套|原味|卖骚|勾引|勾搭|调戏|撩|暧昧|涩图|图涩'
)
BATCH = 15
PROMPT = """下面是一批QQ聊天消息（编号:文本，[图片]等为占位符）。请逐条判断是否含涩情/色情/性暗示内容，输出JSON数组，每项{"i":编号,"l":0或1或2或3}：
l=0 无；1 轻微暧昧擦边；2 明显色情；3 露骨色情。
注意：日常粗口（卧槽/我操/妈的）不算色情；二次元语境下提到腿/泳装等需结合上下文，明确描写身体或性行为的才算。
只输出JSON数组。"""


def judge_batch(items, retries=3):
    lines = '\n'.join(f'{i}:{t[:130]}' for i, t in items)
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': PROMPT + '\n\n' + lines}],
        'max_tokens': 1200,
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
                return {int(x['i']): int(x['l']) for x in arr if isinstance(x, dict) and 'i' in x}
            return {}
        except Exception as ex:
            if attempt == retries - 1:
                return {}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    labeled = set(r['user_id'] for r in conn.execute(
        "SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')"))
    rows = conn.execute(
        "SELECT id, user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0").fetchall()
    conn.close()
    print(f'总消息: {len(rows)}')

    hits = [(r['id'], r['user_id'], r['text']) for r in rows
            if r['user_id'] not in labeled and KW.search(r['text'] or '')]
    print(f'未标注用户命中消息: {len(hits)}')

    done_ids = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            l = l.strip()
            if l:
                done_ids.add(json.loads(l)['id'])
    todo = [h for h in hits if h[0] not in done_ids]
    print(f'待判定: {len(todo)}')

    def work(item):
        mid, uid, t = item
        return mid, uid, t, judge_batch([(0, t)]).get(0)

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            mid, uid, t, lvl = fut.result()
            if lvl is not None:
                results.append({'id': mid, 'user_id': uid, 'text': t[:200], 'level': lvl})
            done += 1
            if done % 200 == 0 or done == len(todo):
                print(f'进度 {done}/{len(todo)}')
            if done % 200 == 0:
                with open(OUT, 'a', encoding='utf-8') as f:
                    for rec in results:
                        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                results = []
    with open(OUT, 'a', encoding='utf-8') as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    from collections import Counter
    all_labels = [json.loads(l)['level'] for l in open(OUT, encoding='utf-8') if l.strip()]
    print(f'\n[完成] 累计 {len(all_labels)} 条: ' + str(dict(Counter(all_labels))))


if __name__ == '__main__':
    main()
