# -*- coding: utf-8 -*-
"""calib_ref.py — 标定参考包：为待标注用户计算可解释指数并给出标注提示

指数：
  萌系指数  = 撒娇卖萌贴纸占比*0.5 + [表情]消息占比*0.2 + 语气词密度*0.15 + 颜文字密度*0.15
  抽象指数  = 抽象贴纸占比*0.5 + 抽象词密度*0.3 + 超短句率*0.2
  涩情指数  = 本地模型 any/max/ratio
  风格std   = p_female 标准差
  图率/短句率 = 行为画像
输出 outputs/标定参考包.md / .csv
"""
import csv
import json
import re
import sqlite3
from collections import Counter

MIN_EFF = 100
CJK = re.compile(r'[\u4e00-\u9fff]')

def strftime_hour(ts):
    """unix 秒 → 北京时间小时（字符串 HH）"""
    import time as _t
    return _t.strftime('%H', _t.localtime(ts + 8 * 3600))

# 语气词 / 颜文字 / 抽象词
MOE_WORDS = re.compile(r'呢|啦|喵|捏|嗷|呀|嘛|惹|滴|的说|呜呜|嘤嘤|诶嘿|嘻嘻|ovo|QAQ|qwq|QwQ|OvO|好耶|嘿嘿')
KAOMOJI = re.compile(r'[（(].{0,6}[︶﹏︿•́_•̀ㅂ￣▽▽﹏︿‿◡>﹏︵╥╯□╰눈_눈◕‿◕•̀ㅂ•́].{0,6}[）)]|QAQ|qwq|ovo|TAT|2333|Orz|orz')
ABSTRACT_WORDS = re.compile(r'草|乐|典|绷|蚌|麻了|难绷|典中典|绷不住|哈人|流汗|笑死|难蚌|地狱|逆天|6$|蚌埠')

def load_sticker_tags():
    tags = {}
    try:
        with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('url') and r.get('emotion'):
                    tags[r['url']] = r
    except Exception:
        pass
    return tags

def main():
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    tags = load_sticker_tags()
    print(f'贴纸标签: {len(tags)} 个')

    # 未标注用户（群1/2，有效≥100）
    users = conn.execute("""
        SELECT m.user_id, COUNT(*) c,
               SUM(CASE WHEN LENGTH(m.text) >= 4 THEN 1 ELSE 0 END) eff,
               MAX(m.nickname) nick
        FROM messages m
        WHERE m.scene='group' AND m.peer_id IN (826904606, 762673304)
          AND m.user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
        GROUP BY m.user_id HAVING eff >= ?""", (MIN_EFF,)).fetchall()
    uids = set(r['user_id'] for r in users)
    print(f'待标注用户: {len(users)}')

    # 逐用户指数
    stats = {}
    for r in conn.execute("SELECT user_id, raw_json, text, time FROM messages WHERE raw_json IS NOT NULL"):
        uid = r['user_id']
        if uid not in uids:
            continue
        s = stats.setdefault(uid, {'n': 0, 'img': 0, 'moe_tag': 0, 'abs_tag': 0, 'tag_n': 0,
                                   'face': 0, 'moe_w': 0, 'kao': 0, 'abs_w': 0, 'short': 0, 'chars': 0,
                                   'night': 0})
        s['n'] += 1
        # 深夜占比（0-6点，UTC+8）：行为画像维度，仅作人工标定参考，不进模型
        try:
            if strftime_hour(r['time']) in ('00', '01', '02', '03', '04', '05'):
                s['night'] += 1
        except Exception:
            pass
        try:
            j = json.loads(r['raw_json'])
        except Exception:
            j = None
        has_img = False
        if j:
            for seg in (j.get('message') or []):
                if isinstance(seg, dict) and seg.get('type') == 'image':
                    url = (seg.get('data') or {}).get('url') or ''
                    has_img = True
                    t = tags.get(url)
                    if t:
                        s['tag_n'] += 1
                        if t['emotion'] == '撒娇卖萌':
                            s['moe_tag'] += 1
                        if t['style'] == '抽象':
                            s['abs_tag'] += 1
        if has_img:
            s['img'] += 1
        txt = r['text'] or ''
        if CJK.search(txt):
            s['chars'] += len(txt)
        if '[表情' in txt:
            s['face'] += 1
        if MOE_WORDS.search(txt):
            s['moe_w'] += 1
        if KAOMOJI.search(txt):
            s['kao'] += 1
        if ABSTRACT_WORDS.search(txt):
            s['abs_w'] += 1
        if len(txt) <= 3:
            s['short'] += 1
    conn.close()

    # 打分 / 涩情 / 网络
    scores = {}
    with open('outputs/score-v10-wb-all.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            scores[int(r['user_id'])] = r
    ero = {}
    with open('outputs/erotic_features_all.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            ero[int(r['user_id'])] = r
    net = {}
    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    for r in conn.execute('SELECT user_id, network_gender FROM profile_genders'):
        net[r['user_id']] = r['network_gender']
    conn.close()

    def card(uid, gid):
        conn = sqlite3.connect('data/qqchat.db')
        conn.row_factory = sqlite3.Row
        r = conn.execute("""SELECT card FROM messages WHERE peer_id=? AND user_id=? AND card IS NOT NULL AND card!=''
                            ORDER BY time DESC LIMIT 1""", (gid, uid)).fetchone()
        conn.close()
        return r['card'] if r else ''

    G_CN = {'male': '男', 'female': '女', 'none': '无标签'}

    def hint(u, p, pred, st, s, e):
        tips = []
        moe = st['moe_index']
        abstract = st['abs_index']
        if p >= 0.5:
            if moe >= 0.5:
                tips.append('⚠️疑似男声女气(模型判女+萌系↑)，重点核实')
            else:
                tips.append('模型判女，核实是否为女或男声女气')
        if e and int(e.get('ero_max', 0)) == 3 and pred == 'female':
            tips.append('⚠️涩情露骨=男侧信号，与判女冲突')
        ng = net.get(u, 'none')
        if ng in ('male', 'female') and ((ng == 'male' and pred == 'female') or (ng == 'female' and pred == 'male')):
            tips.append('⚠️网络性别与模型冲突')
        if p < 0.15 and not tips:
            tips.append('低价值(稳定男侧)，除非你确认其为女')
        if abstract >= 0.5:
            tips.append('抽象梗图流')
        return '；'.join(tips) if tips else '—'

    items = []
    for r in users:
        uid = r['user_id']
        s = stats.get(uid)
        sc = scores.get(uid)
        if not s or not sc:
            continue
        n = s['n']
        p = float(sc['prob_female_mean'])
        pred = sc['predicted']
        conf = sc['confidence']
        moe = (s['moe_tag'] / max(s['tag_n'], 1)) * 0.5 + (s['face'] / n) * 0.2 + (s['moe_w'] / n) * 0.15 + (s['kao'] / n) * 0.15
        abstract = (s['abs_tag'] / max(s['tag_n'], 1)) * 0.5 + (s['abs_w'] / n) * 0.3 + (s['short'] / n) * 0.2
        e = ero.get(uid)
        items.append({
            'uid': uid, 'nick': r['nick'] or '', 'card1': card(uid, 826904606), 'card2': card(uid, 762673304),
            'n': r['c'], 'p': p, 'pred': pred, 'conf': conf,
            'net': G_CN.get(net.get(uid, 'none'), net.get(uid, 'none')),
            'ero_any': e['ero_any'] if e else '?', 'ero_max': e['ero_max'] if e else '?',
            'ero_ratio': e['ero_ratio'] if e else '?',
            'moe': moe, 'abstract': abstract, 'short_rate': s['short'] / n,
            'img_rate': s['img'] / n, 'std': sc['prob_female_std'],
            'night_ratio': s['night'] / n,
            'hint': hint(uid, p, pred, {'moe_index': moe, 'abs_index': abstract}, s, e),
        })
    items.sort(key=lambda x: -x['p'])

    lines = ['# 标定参考包（待标注用户 + 可解释指数）', '',
             '- 指数均为统计量，用于辅助人工标定；模型已隐式学习文本特征，指数主要服务"人"的决策',
             '- 萌系指数 = 撒娇卖萌贴纸占比×0.5 + [表情]消息占比×0.2 + 语气词密度×0.15 + 颜文字密度×0.15',
             '- 抽象指数 = 抽象贴纸占比×0.5 + 抽象词密度×0.3 + 超短句率×0.2',
             '- 标注命令: node scripts/label.js --user <QQ号> --gender male|female',
             '', '| QQ号 | 昵称 | 群名片 | 消息 | P(女) | 结论 | 置信 | 网络 | 涩情any/max/占比 | 萌系 | 抽象 | 短句率 | 图率 | 深夜占比 | std | 提示 |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for it in items:
        lines.append(f'| {it["uid"]} | {it["nick"]} | {it["card1"] or it["card2"]} | {it["n"]} | {it["p"]:.3f} | '
                     f'{it["pred"]} | {it["conf"]} | {it["net"]} | {it["ero_any"]}/{it["ero_max"]}/{it["ero_ratio"]} | '
                     f'{it["moe"]:.2f} | {it["abstract"]:.2f} | {it["short_rate"]:.2f} | {it["img_rate"]:.2f} | '
                     f'{it["night_ratio"]:.2f} | {it["std"]} | {it["hint"]} |')
    md_text = '\n'.join(lines)
    # 写入安全校验：行数必须与 items 一致，防止覆盖/截断事故
    assert md_text.count('\n| ') >= len(items), f'MD 行数校验失败: {md_text.count(chr(10) + "| ")} < {len(items)}'
    with open('outputs/标定参考包.md', 'w', encoding='utf-8') as f:
        f.write(md_text)
    with open('outputs/标定参考包.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['QQ号', '昵称', '群名片', '消息数', 'P(女)', '模型结论', '置信度', '网络性别',
                    '涩情any', '涩情max', '涩情占比', '萌系指数', '抽象指数', '超短句率', '图率', '深夜占比', '风格std', '提示'])
        for it in items:
            w.writerow([it['uid'], it['nick'], it['card1'] or it['card2'], it['n'], round(it['p'], 3),
                        it['pred'], it['conf'], it['net'], it['ero_any'], it['ero_max'], it['ero_ratio'],
                        round(it['moe'], 2), round(it['abstract'], 2), round(it['short_rate'], 2),
                        round(it['img_rate'], 2), round(it['night_ratio'], 2), it['std'], it['hint']])
    print(f'[完成] {len(items)} 人 → outputs/标定参考包.md / .csv')
    # 写后验证：CSV 行数（防数据丢失回归）
    with open('outputs/标定参考包.csv', encoding='utf-8') as f:
        n_rows = sum(1 for _ in f) - 1
    assert n_rows == len(items), f'CSV 行数校验失败: {n_rows} != {len(items)}'
    print(f'[校验] CSV 行数 {n_rows} == items {len(items)} ✔')
    n_warn = sum(1 for it in items if '⚠️' in it['hint'])
    print(f'高优先级提示用户: {n_warn} 人')


if __name__ == '__main__':
    main()

