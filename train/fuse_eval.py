# 融合 BERT 与 LLM 判定，搜索最优规则
import csv

bert = {}
with open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/models/bert-v4/users.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        bert[int(row['user_id'])] = (row['true'], float(row['score']))

# LLM 结果（judge_llm 输出）
llm = {
    2803093623: ('male', 'female', 0.7), 2604093609: ('male', 'female', 0.7),
    185327596: ('female', 'male', 0.9), 2587025229: ('male', 'female', 0.9),
    1703380767: ('female', 'female', 0.7), 2392304699: ('male', 'female', 0.9),
    972242500: ('male', 'male', 0.9), 1206156741: ('female', 'male', 0.9),
    1683253039: ('female', 'female', 0.7), 3360345621: ('male', 'female', 0.9),
    439161815: ('male', 'female', 0.7), 1757193004: ('female', 'female', 0.9),
    348105425: ('female', 'female', 0.9), 1803703473: ('male', 'female', 0.7),
    1654115451: ('male', 'female', 0.7), 1115092215: ('male', 'female', 0.6),
    1395833200: ('female', 'female', 0.7), 1716842937: ('male', 'male', 0.6),
    844793387: ('male', 'female', 0.7), 3204748035: ('male', 'female', 0.6),
    3474710392: ('male', 'male', 0.7), 3544142951: ('male', 'female', 0.7),
    1521768316: ('male', 'female', 0.85), 1986993074: ('male', 'female', 0.6),
    1591798171: ('male', 'female', 0.6),
}

def eval_rule(rule):
    correct = 0
    details = []
    for uid, (t, bs) in bert.items():
        lp = 1.0 if (uid in llm and llm[uid][1] == 'female') else 0.0
        lc = llm[uid][2] if uid in llm else 0.0
        fused = rule(bs, lp, lc)
        pred = 'female' if fused >= 0.5 else 'male'
        correct += (pred == t)
        details.append((uid, t, pred, round(fused, 3)))
    return correct, details

rules = {
    'BERT(0.5)': lambda bs, lp, lc: bs,
    '平均融合': lambda bs, lp, lc: (bs + lp) / 2,
    '加权0.6B+0.4L': lambda bs, lp, lc: 0.6 * bs + 0.4 * lp,
    'LLM高置信否决': lambda bs, lp, lc: 1.0 if (lp == 1 and lc >= 0.9 and bs < 0.5) else bs,
    'LLM否决(≥0.7)': lambda bs, lp, lc: 1.0 if (lp == 1 and lc >= 0.7 and bs < 0.5) else bs,
    '双确认才女': lambda bs, lp, lc: 1.0 if (lp == 1 and bs > 0.2) else bs,
}

for name, rule in rules.items():
    correct, details = eval_rule(rule)
    fs = [d for d in details if d[1] == 'female']
    ms = [d for d in details if d[1] == 'male']
    fc = sum(1 for d in fs if d[2] == 'female')
    mc = sum(1 for d in ms if d[2] == 'male')
    print(f'{name:<16} 用户级 {correct}/25 ({correct/25:.0%}) | 女 {fc}/{len(fs)} | 男 {mc}/{len(ms)}')

# 打印最优规则（LLM否决≥0.9）细节
print('\n--- LLM高置信否决 规则详情 ---')
_, details = eval_rule(rules['LLM高置信否决'])
for uid, t, p, s in sorted(details, key=lambda x: -x[3]):
    print(f'QQ {uid} 真={t} 预={p} 分={s} {"✓" if t==p else "✗"}')
