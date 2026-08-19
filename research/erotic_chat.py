# -*- coding: utf-8 -*-
"""erotic_chat.py — 聊天涩情等级检测（用户级特征）

流程：关键词预筛（高召回）→ gpt-5.5 批量判定 0-3 级（每批15条）
输出: outputs/erotic_chat.csv（user_id, total, hit, judged, ero_any, ero_max, ero_ratio, ero_hit_ratio）
用法: $env:RELAY_KEY='sk-...'; python research/erotic_chat.py
"""
import csv
import json
import os
import re
import sqlite3
import time
from collections import defaultdict

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
OUT = 'outputs/erotic_chat.csv'

# 关键词预筛（高召回，容忍误报，LLM 再判）
KW = re.compile(
    r'涩|色(?!彩|块|系|调|盲)|欲|本子|裸|胸|乳|福利|内裤|裤衩|罩|操|艹|高潮|射|液|发情|色批|好涩|色色|涩涩|'
    r'黄油|里番|黄文|黄图|女装(?!大)|腿(?!本)|白丝|黑丝|绝对领域|泳装|性感|诱惑|媚|烧|骚|湿|硬了|丁丁|批|吊|'
    r'做爱|口交|肛|龟头|阴道|精子|爱液|约炮|炮友|援交|本子|同人(?!志)|瑟瑟|想艹|肏|干你|草你|上你|扑倒|'
    r'扒衣|摸胸|揉|内射|体外|无套|原味|卖骚|勾引|勾搭|调戏|撩|暧昧|涩图|图涩'
)

BATCH = 15
JUDGE_PROMPT = """下面是一批QQ聊天消息（编号:文本，[图片]等为占位符）。请逐条判断是否含涩情/色情/性暗示内容，输出JSON数组，每项{"i":编号,"l":0或1或2或3,"r":"原因"}：
l=0 无；1 轻微暧昧擦边；2 明显色情；3 露骨色情。
注意：日常粗口（卧槽/我操/妈的）不算色情；二次元语境下提到腿/泳装等需结合上下文，明确描写身体/性行为的才算。
只输出JSON数组。"""


def judge_batch(items, retries=3):
    """items: [(idx, text)] -> {idx: level}"""
    lines = '\n'.join(f'{i}:{t[:120]}' for i, t in items)
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': JUDGE_PROMPT + '\n\n' + lines}],
        'max_tokens': 1500,
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
                print(f'  批判定失败: {ex}')
                return {}
            time.sleep(2 * (attempt + 1))


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    labels = {}
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
        labels[r['user_id']] = r['gender']

    # 每用户：全部消息文本
    user_msgs = defaultdict(list)
    for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
        uid = r['user_id']
        if uid in labels:
            user_msgs[uid].append(r['text'])
    conn.close()

    rows = []
    for uid in sorted(labels):
        texts = user_msgs[uid]
        total = len(texts)
        hits = [t for t in texts if KW.search(t)]
        judged = {}
        if hits:
            sample = hits[:60]
            for b in range(0, len(sample), BATCH):
                items = [(b + k, t) for k, t in enumerate(sample[b:b + BATCH])]
                judged.update(judge_batch(items))
                time.sleep(0.3)
        ero_msgs = [lvl for lvl in judged.values() if lvl >= 1]
        ero_any = 1 if ero_msgs else 0
        ero_max = max(ero_msgs) if ero_msgs else 0
        ero_ratio = len(ero_msgs) / total if total else 0
        ero_hit_ratio = len(ero_msgs) / max(len(hits), 1)
        rows.append({
            'user_id': uid, 'label': labels[uid], 'total': total,
            'kw_hit': len(hits), 'judged': len(judged),
            'ero_any': ero_any, 'ero_max': ero_max,
            'ero_ratio': round(ero_ratio, 4), 'ero_hit_ratio': round(ero_hit_ratio, 4),
        })
        print(f'{uid} {labels[uid]}: total={total} hit={len(hits)} judged={len(judged)} any={ero_any} max={ero_max} ratio={ero_ratio:.3f}')

    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['user_id', 'label', 'total', 'kw_hit', 'judged',
                                          'ero_any', 'ero_max', 'ero_ratio', 'ero_hit_ratio'])
        w.writeheader()
        w.writerows(rows)
    print(f'\n[完成] → {OUT}')


if __name__ == '__main__':
    main()
