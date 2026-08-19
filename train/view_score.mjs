import csv
rows = []
with open('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/outputs/score-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        rows.append(r)
print('临界用户:')
for r in rows:
    if r['confidence'] == 'borderline':
        print(f"  QQ {r['user_id']}  p女={r['prob_female_mean']}  {r['n_messages']}条  预测={r['predicted']} 标签={r['label'] or '未知'}")
print('\n未标注且高置信的女性候选（可能值得补标）:')
fem = [r for r in rows if r['confidence'] == 'high' and r['predicted'] == 'female' and not r['label']]
for r in sorted(fem, key=lambda x: -int(x['n_messages']))[:10]:
    print(f"  QQ {r['user_id']}  p女={r['prob_female_mean']}  {r['n_messages']}条")
