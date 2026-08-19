import csv
rows = []
with open('../models/bert-v6/users.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        rows.append(r)
fs = [r for r in rows if r['true'] == 'female']
ms = [r for r in rows if r['true'] == 'male']
fc = sum(1 for r in fs if r['pred'] == 'female')
mc = sum(1 for r in ms if r['pred'] == 'male')
print(f'用户级: {fc+mc}/{len(rows)} ({(fc+mc)/len(rows):.0%}) | 女性 {fc}/{len(fs)} | 男性 {mc}/{len(ms)}')
print()
print(f'{"QQ":<12}{"真实":<8}{"预测":<8}{"P女":<8}{"条数":<6}')
for r in sorted(rows, key=lambda x: int(x['n_msgs']), reverse=True):
    hit = r['pred'] == r['true']
    mark = '✓' if hit else '✗'
    print(f"{r['user_id']:<12}{r['true']:<8}{r['pred']:<8}{r['score']:<8}{r['n_msgs']:<6}{mark}")
