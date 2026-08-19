# -*- coding: utf-8 -*-
"""integrate_indices.py — 综合指数：男侧证据指数(MSI) + 复核指数(RI)

男侧证据指数 MSI（越高越可能是男，0-100）：
  性发泄率/男基准×2 + 粗口率/女基准差×2 + 叫爹率×1 + 求本子曾用×1.5 + 曾要色图×3
  + 涩情露骨3→+20 / 明显2→+10（本地模型互证）
复核指数 RI（越高越需要人工看，0-100）：
  判女但MSI高→+35 | 四模型翻案×3→+30 /×2→+20 /×1→+10 | 网络性别冲突→+15
  | 涩情露骨且判女→+15 | 风格std>0.15→+10
输出：标定参考包.csv 新增列 + 验证（64 已标注用户上 MSI 的男女分离度、RI 与错误的相关）
"""
import csv
import json
import re
import sqlite3

# ---------- 话语统计 ----------
PAT = {
    '性发泄': re.compile(r'操死|干死|操你|干你|草你|艹你|肏|日你|想操|想干|想日|射你|舔你|吸你|上你|扑倒'),
    '粗口': re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦|草了'),
    '叫爹': re.compile(r'爸爸|爹|爹地|亲爹|爸爸桑'),
    '本子': re.compile(r'(本子|黄油|里番)(求|来|发|要|安排)?|求(本子|黄油|里番)'),
    '要色图': re.compile(r'(求|要|发|来|来点|来张|来个|来几|求个|求点|搞点|给点|安排)(涩|色)图|'
                        r'(涩|色)图(发|求|来|要|安排|速速|交出来|谢谢|感谢|好人一生平安)|好人一生平安|无内鬼|车牌|番号'),
}

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
user_stats = {}
for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
    uid = r['user_id']
    s = user_stats.setdefault(uid, {'n': 0, 'sex': 0, 'curse': 0, 'dad': 0, 'benzi': 0, 'askpic': 0})
    s['n'] += 1
    t = r['text'] or ''
    if PAT['性发泄'].search(t): s['sex'] += 1
    if PAT['粗口'].search(t): s['curse'] += 1
    if PAT['叫爹'].search(t): s['dad'] += 1
    if PAT['本子'].search(t): s['benzi'] += 1
    if PAT['要色图'].search(t): s['askpic'] += 1
# 网络性别
nets = {r['user_id']: r['network_gender'] for r in conn.execute('SELECT user_id, network_gender FROM profile_genders')}
conn.close()

# ---------- 外部特征 ----------
ero = {}
with open('outputs/erotic_features_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        ero[int(r['user_id'])] = r
flips = {}
with open('outputs/score-multi-v10.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        flips[int(r['user_id'])] = int(r['flip_count'])
scores = {}
with open('outputs/score-v10-wb-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

# 已标注用户的基准（男侧话语均值，用于归一化）
base = {'male': {'sex': 0.0009, 'curse': 0.0015, 'dad': 0.0002}}
# 重新精确计算基准
bm = {'sex': 0, 'curse': 0, 'dad': 0, 'n': 0}
for uid, g in labels.items():
    if g != 'male':
        continue
    s = user_stats.get(uid)
    if not s or not s['n']:
        continue
    bm['sex'] += s['sex'] / s['n']
    bm['curse'] += s['curse'] / s['n']
    bm['dad'] += s['dad'] / s['n']
    bm['n'] += 1
for k in ('sex', 'curse', 'dad'):
    base['male'][k] = bm[k] / max(bm['n'], 1)
print(f"男侧基准: sex={base['male']['sex']:.4f} curse={base['male']['curse']:.4f} dad={base['male']['dad']:.4f}")


def compute(uid):
    s = user_stats.get(uid, {'n': 0, 'sex': 0, 'curse': 0, 'dad': 0, 'benzi': 0, 'askpic': 0})
    n = max(s['n'], 1)
    sex_r, curse_r, dad_r = s['sex'] / n, s['curse'] / n, s['dad'] / n
    e = ero.get(uid, {})
    ero_max = int(e.get('ero_max', 0) or 0)
    # MSI（0-100）
    msi = 0.0
    msi += min(sex_r / base['male']['sex'], 1.5) * 22      # 性发泄
    msi += min(curse_r / base['male']['curse'], 1.5) * 22   # 粗口
    msi += min(dad_r / base['male']['dad'], 1.5) * 12       # 叫爹
    if s['benzi']:
        msi += 12                                          # 求本子曾用
    if s['askpic']:
        msi += 18                                          # 曾要色图（强标记）
    if ero_max >= 3:
        msi += 14
    elif ero_max == 2:
        msi += 7
    msi = min(msi, 100)
    # RI（0-100）
    ri = 0.0
    sc = scores.get(uid, {})
    p = float(sc.get('prob_female_mean', 0.5))
    pred = sc.get('predicted', 'male')
    if pred == 'female' and msi >= 35:
        ri += 35
    f = flips.get(uid, 0)
    ri += {3: 30, 2: 20, 1: 10}.get(f, 0)
    net = nets.get(uid, 'none')
    if net in ('male', 'female') and ((net == 'male' and pred == 'female') or (net == 'female' and pred == 'male')):
        ri += 15
    if pred == 'female' and ero_max == 3:
        ri += 15
    try:
        if float(sc.get('prob_female_std', 0) or 0) > 0.15:
            ri += 10
    except Exception:
        pass
    ri = min(ri, 100)
    return msi, ri


def update_reference_package():
    # ---------- 更新参考包 ----------
    rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
    fn = list(rows[0].keys()) + ['男侧证据指数', '复核指数', '综合提示']
    with open('outputs/标定参考包.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        for r in rows:
            uid = int(r['QQ号'])
            msi, ri = compute(uid)
            tips = []
            if msi >= 60:
                tips.append('MSI高(强男侧)')
            elif msi >= 35:
                tips.append('MSI中(男侧)')
            if ri >= 50:
                tips.append('⚠️必复核')
            elif ri >= 25:
                tips.append('建议复核')
            r['男侧证据指数'] = f'{msi:.0f}'
            r['复核指数'] = f'{ri:.0f}'
            r['综合提示'] = '；'.join(tips)
            w.writerow(r)
    print(f'[完成] 参考包新增两指数（{len(rows)} 人）')


if __name__ == '__main__':
    update_reference_package()
    # ---------- 验证 ----------
    import statistics
    print('\n=== 验证 1：MSI 在已标注用户上的男女分离度 ===')
    m_msi, f_msi = [], []
    for uid, g in labels.items():
        msi, _ = compute(uid)
        (m_msi if g == 'male' else f_msi).append(msi)
    print(f'男 (n={len(m_msi)}): MSI均值={statistics.mean(m_msi):.1f} 中位={statistics.median(m_msi):.1f}')
    print(f'女 (n={len(f_msi)}): MSI均值={statistics.mean(f_msi):.1f} 中位={statistics.median(f_msi):.1f}')
    print(f'MSI>=35 中女性占比: {sum(1 for x in f_msi if x >= 35)}/{len(f_msi)}；MSI<20 中男性占比: {sum(1 for x in m_msi if x < 20)}/{len(m_msi)}')

    print('\n=== 验证 2：RI 与 v7 错误的相关 ===')
    err_ri, ok_ri = [], []
    for uid, g in labels.items():
        _, ri = compute(uid)
        sc = scores.get(uid, {})
        if sc.get('correct') == '0':
            err_ri.append(ri)
        elif sc.get('correct') == '1':
            ok_ri.append(ri)
    print(f'错误用户 (n={len(err_ri)}): RI均值={statistics.mean(err_ri):.1f}')
    print(f'正确用户 (n={len(ok_ri)}): RI均值={statistics.mean(ok_ri):.1f}')

