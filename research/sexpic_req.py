# -*- coding: utf-8 -*-
"""sexpic_req.py — 统计"要色图"话语的性别差异（64 已标注用户）

模式：
  请求类: (求|要|发|来|来点|来张|来个|来几|求个|求点|搞点|给点|安排)(涩|色)图
          (涩|色)图(发|求|来|要|安排|速速|交出来|谢谢|感谢|好人一生平安)
          好人一生平安 | 无内鬼 | 发车 | 开车 | 车牌 | 番号
  本子类: (本子|黄油|里番)(求|来|发|要|安排)? | 求(本子|黄油|里番)
"""
import re
import sqlite3
from collections import defaultdict

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

PAT_ASK = re.compile(
    r'(求|要|发|来|来点|来张|来个|来几|求个|求点|搞点|给点|安排)(涩|色)图|'
    r'(涩|色)图(发|求|来|要|安排|速速|交出来|谢谢|感谢|好人一生平安)|'
    r'好人一生平安|无内鬼|车牌|番号'
)
PAT_BENZI = re.compile(r'(本子|黄油|里番)(求|来|发|要|安排)?|求(本子|黄油|里番)')

user_texts = defaultdict(list)
for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
    uid = r['user_id']
    if uid in labels:
        user_texts[uid].append(r['text'] or '')
conn.close()

stats = {'male': {'n_users': 0, 'ask_users': 0, 'benzi_users': 0, 'ask_msgs': 0, 'total': 0},
         'female': {'n_users': 0, 'ask_users': 0, 'benzi_users': 0, 'ask_msgs': 0, 'total': 0}}
examples = {'male': [], 'female': []}
for uid, g in labels.items():
    texts = user_texts[uid]
    if not texts:
        continue
    st = stats[g]
    st['n_users'] += 1
    st['total'] += len(texts)
    ask_hits = [t for t in texts if PAT_ASK.search(t)]
    benzi_hits = [t for t in texts if PAT_BENZI.search(t)]
    if ask_hits:
        st['ask_users'] += 1
        st['ask_msgs'] += len(ask_hits)
        if len(examples[g]) < 3:
            examples[g].append((uid, ask_hits[0][:50]))
    if benzi_hits:
        st['benzi_users'] += 1

print('=== 要色图话语统计（64 已标注用户）===')
print(f'{"指标":<24}{"男":<14}{"女":<14}')
for g in ('male', 'female'):
    pass
m, f = stats['male'], stats['female']
print(f'{"用户数":<22}{m["n_users"]:<14}{f["n_users"]:<14}')
print(f'{"要色图(曾用)用户占比":<20}{m["ask_users"]/max(m["n_users"],1):<14.0%}{f["ask_users"]/max(f["n_users"],1):<14.0%}')
print(f'{"要色图消息占比":<22}{m["ask_msgs"]/max(m["total"],1):<14.4%}{f["ask_msgs"]/max(f["total"],1):<14.4%}')
print(f'{"求本子/黄油用户占比":<20}{m["benzi_users"]/max(m["n_users"],1):<14.0%}{f["benzi_users"]/max(f["n_users"],1):<14.0%}')
print()
print('男侧示例:', examples['male'])
print('女侧示例:', examples['female'])
