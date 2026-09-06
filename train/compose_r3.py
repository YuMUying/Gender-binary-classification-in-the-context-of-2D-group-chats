# -*- coding: utf-8 -*-
"""compose_r3: v17组装的r3变体 — 在compose_v17基础上加"中间人格合成"通道
val划分逻辑/rng与compose_v17.py逐行一致(seed 17), 指标与r1/r2可比
"""
import json
import io
import os
import sys
import random
import argparse
import collections
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS = os.path.join(ROOT, 'trainsets')

# val扩容 3→5/类 (2026-09-02 定案, 固化清单; 锁定协议: 原9人永不动, 新增6人审核后固化)
# F+2: 22-电自-张格(现实女·老乡群), 槭久(二次元·庭院) — 补现实/二次元两维度
# SM+2: 呜喵～, ?(厚度top2)
# M+2: 江墨白, 酒神爵 (排除用户本人U1894与语体重叠的U2214)
# val扩容 v3 (2026-09-03): F 5->9人 (补班群课业腔2人 + 乙女群交易腔2人)
# 锁定协议: 原5人不动; 旧15人口径历史数字已存档, 新口径起全量重测
# 新增: 邵鉴楠U1613(课业腔) 彭斓U1022(课业+私聊) ReiU058(乙女交易腔) minuoU836(乙女日常)
# val v4 / s0v5.4 (2026-09-04): 干净val裁决局
# 移除: 言葉U667+神樱汐梦U1093(faudit降级unknown, val残留1192条假F) + minuoU836(33条太薄)
# 补位: 唐杨雯菲U2172(老乡群现实同学腔654条) + XafubU239(绘旅人310条, 乙女群补位·用户授权自行定)
VAL_FEMALE = [U2193, U2165, U1835,
              U1613, U1022, U058, U2172, U239]
VAL_SOFT = [U1552, U446, U1851, U1057, U1419]  # U1109苍中蓝实为女性已移出(2026-09-02), 换U1419迷迭香
VAL_MALE = [U1385, U1887, U2723, U2079, U924]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--synth-users', type=int, default=0)
    ap.add_argument('--middle', action='store_true', help='加入llm-synth-middle.jsonl中间人格通道')
    ap.add_argument('--suffix', default='')
    ap.add_argument('--style-override', default=None, help='C2/C3 style_class override json')
    ap.add_argument('--input', default='v17-real-all.jsonl', help='原始导出jsonl(默认v17-real-all)')
    ap.add_argument('--female-to-train', default='', help='从val移到train的F用户(诊断实验2026-09-05): 逗号分隔uid')
    ap.add_argument('--female-test-extra', default='', help='额外F测试用户(从train抽出): 逗号分隔uid')
    ap.add_argument('--dreamlike-aug', default='', help='LLM人格卡合成语料jsonl(带表情指纹)')
    ap.add_argument('--exclude-style', default='', help='留出的合成卡style_user(逗号分隔uid, 其克隆不进train)')
    args = ap.parse_args()

    con = sqlite3.connect(os.path.join(ROOT, 'main', 'main.db'))
    style = dict(con.execute("SELECT user_id, style_class FROM speaker_labels"))
    # --style-override: C2/C3方法论对比实验用(2026-09-04), 从json覆盖style_class
    if args.style_override:
        _ovd = json.load(io.open(args.style_override, encoding='utf-8-sig'))
        for k, v in _ovd.items():
            style[int(k)] = v if v else None
        print(f'[override] style覆盖{len(_ovd)}人')
    # === @提及清洗(2026-09-02): 全库昵称字典最长匹配, "@昵称 " -> "@" ===
    # 动机: @后注入的是被@用户的签名(名片/昵称), 造成风格交叉污染; 替换为裸@保留互动信号
    import re as _re
    _cl = lambda s: _re.sub(r'[\x00-\x1f\x7f\ufffd]', '', s)
    names = set()
    for (n,) in con.execute("SELECT DISTINCT nickname FROM messages WHERE nickname IS NOT NULL AND nickname != ''"):
        n2 = _cl(n)
        if 1 <= len(n2) <= 40: names.add(n2)
    for (n,) in con.execute("SELECT DISTINCT card FROM messages WHERE card IS NOT NULL AND card != ''"):
        n2 = _cl(n)
        if 1 <= len(n2) <= 40: names.add(n2)
    _max_len = max(len(n) for n in names)
    _sp = _re.compile(r'[^\s@]{1,32}')
    _quote_re = _re.compile(r'\[回复[^\]]{1,60}\]\s*')
    _ws_re = _re.compile(r' {2,}')
    def strip_mentions(text):
        if '[回复' in text:
            text = _quote_re.sub('', text)  # QQ引用头: [回复 昵称: 原消息] 含他人昵称
        if '@' not in text:
            return text
        out, i, L = [], 0, len(text)
        while i < L:
            j = text.find('@', i)
            if j < 0:
                out.append(text[i:]); break
            out.append(text[i:j]); i = j
            hit = 0
            for l in range(min(_max_len, L - j - 1), 0, -1):
                if text[j+1:j+1+l] in names:
                    hit = l; break
            if hit:
                i = j + 1 + hit
                if i < L and text[i] in ' \u3000':
                    i += 1
                out.append('@')
            else:
                m = _sp.match(text, j + 1)  # 未知昵称: 吞到首个空白(保守)
                i = m.end() if m else j + 1
                out.append('@')
        return _ws_re.sub(' ', ''.join(out))
    con.close()

    rows = [json.loads(l) for l in io.open(os.path.join(TS, args.input), encoding='utf-8-sig')]
    rows = [r for r in rows if isinstance(r.get('user_id'), int) and r['user_id'] > 0]  # s0v58: 过滤node导出的空uid行
    users = sorted({r['user_id'] for r in rows})
    print(f'real: {len(rows)}行 / {len(users)}用户')
    eff = collections.Counter(r['user_id'] for r in rows)

    rng = random.Random(17)
    val_users = set(VAL_FEMALE) | set(VAL_SOFT) | set(VAL_MALE)
    # 诊断实验(2026-09-05): F难例塞回train + 风格近似F抽出当测试
    if args.female_to_train:
        _f2t = {int(u) for u in args.female_to_train.split(',')}
        val_users -= _f2t
        print(f'[diag] F移回train: {sorted(_f2t)} (val余{len(val_users)}人)')
    if args.female_test_extra:
        _fte = {int(u) for u in args.female_test_extra.split(',')}
        val_users |= _fte
        print(f'[diag] F测试追加: {sorted(_fte)}')
    print('val 留出用户:', sorted(val_users))

    tr, va = [], []
    for r in rows:
        r['label'] = style.get(r['user_id'], r.get('label'))
        r['text'] = strip_mentions(r['text'])
        r.setdefault('weight', 1.0)
        (va if r['user_id'] in val_users else tr).append(r)

    cur_ids = set(users)
    ext = []
    for l in io.open(os.path.join(TS, 'gender-v15-train.jsonl'), encoding='utf-8-sig'):
        d = json.loads(l)
        if d['user_id'] not in cur_ids and d['user_id'] not in val_users:
            d['label'] = 'female' if d.get('label') == 'female' else 'male'
            d['text'] = strip_mentions(d['text'])
            d['weight'] = 0.6
            ext.append(d)
    print(f'external(v15, w0.6): {len(ext)}行')

    aug = []
    for l in io.open(os.path.join(TS, 'llm_style_aug.jsonl'), encoding='utf-8-sig'):
        d = json.loads(l)
        su = d.get('style_user')
        if su in style and style[su] is not None and su not in val_users:
            d['label'] = style[su]
            d['weight'] = 0.6
            aug.append(d)
    print(f'style_aug(w0.6): {len(aug)}行')

    if args.dreamlike_aug:
        excl = {int(u) for u in args.exclude_style.split(',')} if args.exclude_style else set()
        n_dl = 0
        for l in io.open(args.dreamlike_aug, encoding='utf-8-sig'):
            d = json.loads(l)
            if d.get('style_user') in excl:
                continue  # 留出卡: 克隆不进train, 保证val测试对纯净
            d['text'] = strip_mentions(d['text'])
            d['weight'] = 0.4  # 合成卡降权(与style_aug同档)
            aug.append(d)
            n_dl += 1
        print(f'dreamlike_aug(w0.4): +{n_dl}行 (留出style_user={sorted(excl)})')

    alltr = tr + ext + aug

    shots_p = os.path.join(TS, 'shots-female.jsonl')
    if os.path.exists(shots_p):
        n_shots = 0
        for l in io.open(shots_p, encoding='utf-8-sig'):
            s = json.loads(l)
            if s.get('pending') or s.get('user_id') is None:
                continue
            if s['user_id'] in val_users:
                continue
            alltr.append(s)
            n_shots += 1
        print(f'shots(w1.0): {n_shots}行')

    if os.path.exists(os.path.join(TS, 'llm-synth-users.jsonl')) and args.synth_users > 0:
        all_synth = [json.loads(l) for l in io.open(os.path.join(TS, 'llm-synth-users.jsonl'), encoding='utf-8-sig')]
        su_all = sorted({s['user_id'] for s in all_synth})
        su_class = {}
        for s in all_synth:
            su_class.setdefault(s['user_id'], s['label'])
        f_ids = [u for u in su_all if su_class[u] == 'female']
        s_ids = [u for u in su_all if su_class[u] == 'soft_male']
        k_f = round(args.synth_users * len(f_ids) / (len(f_ids) + len(s_ids)))
        picked = set(f_ids[:k_f]) | set(s_ids[:args.synth_users - k_f])
        synth = [s for s in all_synth if s['user_id'] in picked and s['user_id'] not in val_users]
        for s in synth:
            s.setdefault('weight', 0.5)
        alltr.extend(synth)
        print(f'synth老通道(取{len(picked)}人): {len(synth)}行')

    if args.middle:
        mid = []
        for l in io.open(os.path.join(TS, 'llm-synth-middle.jsonl'), encoding='utf-8-sig'):
            d = json.loads(l)
            if d['user_id'] in val_users:
                continue
            d.setdefault('weight', 0.5)
            mid.append(d)
        alltr.extend(mid)
        mu = {d['user_id'] for d in mid}
        print(f'middle(中间人格{len(mu)}人): {len(mid)}行')

    random.Random(7).shuffle(alltr)

    def dump(path, rs):
        with io.open(path, 'w', encoding='utf-8') as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')

    suf = f'-{args.suffix}' if args.suffix else ''
    dump(os.path.join(TS, f'gender-v17-train{suf}.jsonl'), alltr)
    dump(os.path.join(TS, f'gender-v17-val{suf}.jsonl'), va)

    for name, rs in (('train', alltr), ('val', va)):
        c = collections.Counter(r['label'] for r in rs)
        us = {r['user_id'] for r in rs}
        print(f'{name}: {len(rs)}行 {dict(c)} 用户{len(us)}')
    leak = {r['user_id'] for r in va} & {r['user_id'] for r in tr}
    assert not leak, f'泄漏: {leak}'
    print('泄漏检查: 通过')


if __name__ == '__main__':
    main()
