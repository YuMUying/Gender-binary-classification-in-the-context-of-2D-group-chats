# -*- coding: utf-8 -*-
"""speech_index.py — 标定话语指数：性发泄/粗口/叫爹三类话语，合并进标定参考包

对每个待标注用户计算：
  性发泄率 = 命中"操死你类"话语的消息占比
  粗口率   = 命中"卧槽类"粗口的消息占比
  叫爹率   = 命中"爸爸/爹"称呼的消息占比
  话语指数 = 性发泄率*2 + 粗口率*2 + 叫爹率*1 （男性倾向加权分）
输出：更新 outputs/标定参考包.csv/.md（新增 4 列 + 提示）
"""
import csv
import re
import sqlite3

PAT = {
    '性发泄': re.compile(r'操死|干死|操你|干你|草你|艹你|肏|日你|想操|想干|想日|射你|舔你|吸你|上你|扑倒'),
    '粗口': re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦|草了'),
    '叫爹': re.compile(r'爸爸|爹|爹地|亲爹|爸爸桑'),
}

# 已标注用户的性别基准（用于指数解释：高于该性别均值 = 男侧信号）
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

# 全库逐用户统计（含未标注）
user_stats = {}
for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
    uid = r['user_id']
    s = user_stats.setdefault(uid, {'n': 0, 'sex': 0, 'curse': 0, 'dad': 0})
    s['n'] += 1
    t = r['text'] or ''
    if PAT['性发泄'].search(t):
        s['sex'] += 1
    if PAT['粗口'].search(t):
        s['curse'] += 1
    if PAT['叫爹'].search(t):
        s['dad'] += 1
conn.close()

# 已标注用户分性别均值（基准）
base = {'male': {'sex': 0, 'curse': 0, 'dad': 0, 'n': 0}, 'female': {'sex': 0, 'curse': 0, 'dad': 0, 'n': 0}}
for uid, g in labels.items():
    s = user_stats.get(uid)
    if not s or s['n'] == 0:
        continue
    b = base[g]
    b['n'] += 1
    b['sex'] += s['sex'] / s['n']
    b['curse'] += s['curse'] / s['n']
    b['dad'] += s['dad'] / s['n']
for g in ('male', 'female'):
    b = base[g]
    for k in ('sex', 'curse', 'dad'):
        b[k] /= max(b['n'], 1)
print(f"基准(人均率): 男 sex={base['male']['sex']:.4f} curse={base['male']['curse']:.4f} dad={base['male']['dad']:.4f} | "
      f"女 sex={base['female']['sex']:.4f} curse={base['female']['curse']:.4f} dad={base['female']['dad']:.4f}")

# 更新参考包 CSV
rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
fn = list(rows[0].keys()) + ['性发泄率', '粗口率', '叫爹率', '话语指数', '话语提示']
with open('outputs/标定参考包.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    for r in rows:
        uid = int(r['QQ号'])
        s = user_stats.get(uid, {'n': 0, 'sex': 0, 'curse': 0, 'dad': 0})
        n = max(s['n'], 1)
        sex_r, curse_r, dad_r = s['sex'] / n, s['curse'] / n, s['dad'] / n
        idx = sex_r * 2 + curse_r * 2 + dad_r
        tips = []
        # 与女侧基准比较：显著高于女性均值 → 男侧信号
        if sex_r > base['female']['sex'] * 2 + 0.001:
            tips.append('性发泄↑(男侧)')
        if curse_r > base['female']['curse'] * 2 + 0.001:
            tips.append('粗口↑(男侧)')
        if dad_r > base['female']['dad'] * 2 + 0.001:
            tips.append('叫爹↑(男侧)')
        r['性发泄率'] = f'{sex_r:.4f}'
        r['粗口率'] = f'{curse_r:.4f}'
        r['叫爹率'] = f'{dad_r:.4f}'
        r['话语指数'] = f'{idx:.4f}'
        r['话语提示'] = '；'.join(tips) if tips else ''
        w.writerow(r)
print(f'[完成] 标定参考包.csv 已新增话语指数列（{len(rows)} 人）')

# 更新 md：在提示列追加话语提示（简化：只更新表头说明）
md = open('outputs/标定参考包.md', encoding='utf-8').read()
if '话语指数' not in md:
    md += '\n\n## 话语指数（v2 新增）\n- 性发泄率/粗口率/叫爹率：对应话语的消息占比（正则统计）\n- 话语指数 = 性发泄×2 + 粗口×2 + 叫爹×1\n- 显著高于女性基准(sex=%.4f, curse=%.4f, dad=%.4f) → 男侧信号\n' % (
        base['female']['sex'], base['female']['curse'], base['female']['dad'])
    open('outputs/标定参考包.md', 'w', encoding='utf-8').write(md)
print('[完成] 标定参考包.md 已追加说明')
