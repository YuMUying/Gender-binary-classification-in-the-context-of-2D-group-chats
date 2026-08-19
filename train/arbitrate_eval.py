# 仲裁规则评估：BERT(v5) 不确定（分数 0.2~0.8）时用 LLM 判定
import csv
import json
from collections import defaultdict

# v5 用户分数
bert = {}
with open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/models/bert-v5/users.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        bert[int(row['user_id'])] = (row['true'], float(row['score']))

# 测试集标签（v5 的 val.jsonl = 阈值100测试集）
labels = {}
for line in open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/data/val.jsonl', encoding='utf-8'):
    r = json.loads(line)
    labels[r['user_id']] = r['label']

# LLM 判定（25 用户版，覆盖 v5 测试集大部分用户）
llm = {
    2803093623: 'female', 2604093609: 'female', 185327596: 'male', 2587025229: 'female',
    1703380767: 'female', 2392304699: 'female', 972242500: 'male', 1206156741: 'male',
    1683253039: 'female', 3360345621: 'female', 439161815: 'female', 1757193004: 'female',
    348105425: 'female', 1803703473: 'female', 1654115451: 'female', 1115092215: 'female',
    1395833200: 'female', 1716842937: 'male', 844793387: 'female', 3204748035: 'female',
    3474710392: 'male', 3544142951: 'female', 1521768316: 'female', 1986993074: 'female',
    1591798171: 'female',
}

def arbitrate(bs, uid):
    if 0.2 <= bs <= 0.8 and uid in llm:
        return llm[uid]
    return 'female' if bs >= 0.5 else 'male'

correct = 0
rows = []
for uid, (t, bs) in sorted(bert.items(), key=lambda kv: -kv[1][1]):
    p = arbitrate(bs, uid)
    hit = (p == labels.get(uid))
    correct += hit
    rows.append((uid, labels.get(uid), p, bs, hit))
print(f'仲裁规则（BERT不确定时用LLM）: {correct}/{len(rows)} ({correct/len(rows):.1%})')
fs = [r for r in rows if r[1] == 'female']
ms = [r for r in rows if r[1] == 'male']
print(f'女性 {sum(1 for r in fs if r[2]=="female")}/{len(fs)} | 男性 {sum(1 for r in ms if r[2]=="male")}/{len(ms)}')
for uid, t, p, bs, hit in sorted(rows, key=lambda x: -x[3]):
    print(f'QQ {uid} 真={t} 判={p} BERT={bs:.3f} {"✓" if hit else "✗"}')
