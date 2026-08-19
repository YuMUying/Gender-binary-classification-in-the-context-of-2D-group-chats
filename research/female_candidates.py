# -*- coding: utf-8 -*-
"""female_candidates.py — 生成女性优先标注清单（含全部指数）"""
import csv

rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))

# 排除 284256062（无文本，全是占位符，不可训练）
EXCLUDE = {284256062}
cand = [r for r in rows
        if int(r['QQ号']) not in EXCLUDE
        and float(r['P(女)']) >= 0.5
        and int(r['消息数']) >= 100]
cand.sort(key=lambda r: (-float(r['P(女)']), -int(r['消息数'])))

# 按"可训练性"排序：无男侧冲突(MSI<35)优先，RI低优先
def score(r):
    msi = float(r.get('男侧证据指数') or 0)
    ri = float(r.get('复核指数') or 0)
    return (1 if msi < 35 else 0, -float(r['P(女)']), ri)

cand.sort(key=score, reverse=False)
cand.sort(key=lambda r: (0 if float(r.get('男侧证据指数') or 0) < 35 else 1, -float(r['P(女)'])))

with open('outputs/女性优先标注清单.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['排序', 'QQ号', '昵称', '消息数', 'P(女)', '模型结论', '置信度', '深夜占比',
                '翻案', '票型', 'MSI', 'RI', '提示'])
    for i, r in enumerate(cand, 1):
        w.writerow([i, r['QQ号'], r['昵称'], r['消息数'], r['P(女)'], r['模型结论'], r['置信度'],
                    r.get('深夜占比', ''), r.get('四模型翻案', ''), r.get('票型', ''),
                    r.get('男侧证据指数', ''), r.get('复核指数', ''), r['提示']])

lines = ['# 女性优先标注清单', '',
         '- 来源：标定参考包（P(女)≥0.5 且样本≥100，已排除无文本用户 284256062）',
         '- MSI<35 = 无男侧话语冲突，最可能为女，优先标注',
         '- 标注命令: node scripts/label.js --user <QQ号> --gender female',
         '', '| # | QQ号 | 昵称 | 消息 | P(女) | 置信 | 深夜占比 | 翻案 | 票型 | MSI | RI | 提示 |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|']
for i, r in enumerate(cand, 1):
    msi = r.get('男侧证据指数', '')
    tag = '★' if (msi != '' and float(msi) < 35) else ''
    lines.append(f'| {i} | {r["QQ号"]} | {r["昵称"]} | {r["消息数"]} | {r["P(女)"]} | {r["置信度"]} | '
                 f'{r.get("深夜占比", "")} | {r.get("四模型翻案", "")} | {r.get("票型", "")} | {r.get("男侧证据指数", "")} | '
                 f'{r.get("复核指数", "")} | {r["提示"][:42]} |')
with open('outputs/女性优先标注清单.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'[完成] {len(cand)} 人 → outputs/女性优先标注清单.csv / .md')
print('★ = MSI<35（无男侧冲突，优先）')
