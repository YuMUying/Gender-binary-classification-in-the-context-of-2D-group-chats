# 测试集评估：预测 vs 真实标签
import csv
import json
from collections import defaultdict

# 读测试集标签
labels = {}
for line in open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/data/test-weak.jsonl', encoding='utf-8'):
    r = json.loads(line)
    labels[r['user_id']] = r['label']   # male/female

# 读预测
preds = {}
with open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/outputs/test-predictions.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        preds[int(row['user_id'])] = (float(row['prob_female']), row['predicted'])

rows = []
for uid, label in labels.items():
    if uid in preds:
        prob, pred = preds[uid]
        rows.append((uid, label, pred, prob))

correct = sum(1 for _, t, p, _ in rows if t == p)
print(f'测试集用户级: {correct}/{len(rows)} 正确 ({correct/len(rows):.2%})')
print(f'\n{"QQ":<12}{"真实":<8}{"预测":<8}{"P(女)":<8}{"条数":<6}')
for uid, t, p, prob in sorted(rows, key=lambda x: -x[3]):
    n = 0
    for line in open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/data/test-weak.jsonl', encoding='utf-8'):
        if json.loads(line)['user_id'] == uid:
            n += 1
    mark = ' ✓' if t == p else ' ✗'
    print(f'{uid:<12}{t:<8}{p:<8}{prob:<8.3f}{n:<6}{mark}')

# 分性别统计
females = [(t, p) for _, t, p, _ in rows if t == 'female']
males = [(t, p) for _, t, p, _ in rows if t == 'male']
fc = sum(1 for t, p in females if t == p)
mc = sum(1 for t, p in males if t == p)
print(f'\n女性: {fc}/{len(females)} 正确 | 男性: {mc}/{len(males)} 正确')
