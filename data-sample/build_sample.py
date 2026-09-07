# -*- coding: utf-8 -*-
"""脱敏样例数据集构建脚本（论文公开数据 B 档，v1，2026-09-08）

用法:
    python build_sample.py --db <main.db 路径> --out <输出目录> [--audit 300]

产出:
    data/annotations_deidentified.csv    标注账本脱敏表（190 人: 别名/软度/社群/名片性别/标注性别）
    data/messages_sample_deidentified.csv 消息样例（约 3 万条: 序号/日期/社群类别/说话人别名/清洗后文本）
    audit/random_audit.csv               人工抽审子样本（默认 300 条）
    manifest.json                        行数/日期范围/规则版本/校验和

脱敏规则（详见 SCRUBBING_PROTOCOL.md）:
    R1 剔除账本内 190 名说话人、作者本人账号、uid<=0、机器人账号的消息（文本不可回溯到被标注个体）
    R2 说话人 -> 随机别名（消息样例 SPK_xxxx，标注表 LED_xxx，两套独立映射互不可连）
    R3 昵称/群名片字段整体不导出
    R4 时间戳粗化到"日"
    R5 群号 -> 类别标签（anime-1..4 / otome-1..3），不保留真实群号与群名
    R6 文本清洗: URL/邮箱/手机号/QQ号类数字串/全角数字/残留@提及 -> 占位符
固定种子 42，全部随机映射可复现。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

SEED = 42
AUTHOR_UID = 2633083674          # 作者本人，排除
BOT_UIDS = {0, 2854196310}       # 系统与群机器人
ANIME = {826904606: 'anime-1', 682478774: 'anime-2', 762673304: 'anime-3', 723216773: 'anime-4'}
OTOME = {2164061969: 'otome-1', 903326799: 'otome-2', 916932460: 'otome-3'}
ANIME_CAPS = {826904606: 6000, 682478774: 4000, 762673304: 3500, 723216773: 1500}
TZ = timezone(timedelta(hours=8))  # UTC+8

# 清洗规则（规则版本 R6-2026-09-08）
RE_URL = re.compile(r'(https?://\S+|www\.\S+)')
RE_MAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+')
RE_PHONE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
RE_QQNUM = re.compile(r'(?<!\d)\d{5,11}(?!\d)')
RE_AT = re.compile(r'@\S+')
RE_WS = re.compile(r'\s+')
FW = {chr(f + 0xFEE0): chr(f) for f in range(0x30, 0x3A)}  # 全角数字->半角


def scrub(text):
    s = text.translate(FW)
    s = RE_URL.sub('[链接]', s)
    s = RE_MAIL.sub('[邮箱]', s)
    s = RE_PHONE.sub('[号码]', s)
    s = RE_QQNUM.sub('[数字]', s)
    s = RE_AT.sub('@', s)
    s = RE_WS.sub(' ', s).strip()
    return s


def day_of(ts):
    try:
        ts = int(ts)
        return datetime.fromtimestamp(ts, TZ).strftime('%Y-%m-%d')
    except (TypeError, ValueError):
        return 'unknown'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--audit', type=int, default=300)
    ap.add_argument('--ledger-csv', required=True, help='frozen ledger snapshot CSV (user_id,true_label,p_female)')
    a = ap.parse_args()
    rng = random.Random(SEED)

    con = sqlite3.connect(a.db, timeout=600)
    con.execute('PRAGMA journal_mode=WAL')

    exclude_uids = {uid for (uid,) in con.execute('SELECT user_id FROM speaker_labels')} | BOT_UIDS | {AUTHOR_UID}
    snap = {int(r['user_id']): r['true_label'] for r in csv.DictReader(io.open(a.ledger_csv, encoding='utf-8-sig'))}

    # ---- 消息样例 ----
    msgs = []
    for peer, cat in ANIME.items():
        cap = ANIME_CAPS[peer]
        pool = con.execute(
            '''SELECT user_id, time, text FROM messages
               WHERE peer_id=? AND scene='group' AND user_id>0 AND text IS NOT NULL
                 AND LENGTH(TRIM(text))>0''', (peer,)).fetchall()
        pool = [r for r in pool if r[0] not in exclude_uids]
        rng.shuffle(pool)
        for uid, ts, text in pool[:cap]:
            msgs.append((cat, uid, ts, text))
    for peer, cat in OTOME.items():
        pool = con.execute(
            '''SELECT user_id, time, text FROM messages
               WHERE peer_id=? AND scene='group' AND user_id>0 AND text IS NOT NULL
                 AND LENGTH(TRIM(text))>0''', (peer,)).fetchall()
        pool = [r for r in pool if r[0] not in exclude_uids]
        msgs.extend((cat, uid, ts, text) for uid, ts, text in pool)

    # 说话人别名（仅样例内一致）
    spk = sorted({uid for _, uid, _, _ in msgs})
    rng.shuffle(spk)
    alias = {u: f'SPK_{i+1:04d}' for i, u in enumerate(spk)}
    msgs.sort(key=lambda r: (r[2] if r[2] else 0))

    os.makedirs(os.path.join(a.out, 'data'), exist_ok=True)
    os.makedirs(os.path.join(a.out, 'audit'), exist_ok=True)

    rows = []
    for i, (cat, uid, ts, text) in enumerate(msgs, 1):
        rows.append({'msg_id': i, 'day': day_of(ts), 'group': cat,
                     'speaker': alias[uid], 'text': scrub(text)})
    with io.open(os.path.join(a.out, 'data', 'messages_sample_deidentified.csv'),
                 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['msg_id', 'day', 'group', 'speaker', 'text'])
        w.writeheader(); w.writerows(rows)

    # ---- 标注账本脱敏表 ----
    prof = {u: g for u, g in con.execute('SELECT user_id, network_gender FROM profile_genders')}
    led_uids = sorted(snap)
    rng.shuffle(led_uids)
    led_alias = {u: f'LED_{i+1:03d}' for i, u in enumerate(led_uids)}
    arows = []
    for u in led_uids:
        msgs_u = con.execute(
            '''SELECT peer_id, COUNT(*) c FROM messages WHERE user_id=? GROUP BY peer_id''', (u,)).fetchall()
        an = sum(c for p, c in msgs_u if p in ANIME)
        ot = sum(c for p, c in msgs_u if p in OTOME)
        other = sum(c for _, c in msgs_u) - an - ot
        comm = 'otome' if ot > an and ot > other else ('anime' if an >= other else 'other')
        soft = con.execute(
            '''SELECT AVG(CASE WHEN text GLOB '*qwq*' OR text GLOB '*awa*' OR text GLOB '*呜*'
                OR text GLOB '*喵*' OR text GLOB '*嘛*' OR text GLOB '*捏*' OR text GLOB '*啦*'
                OR text GLOB '*呀*' OR text GLOB '*哼*' OR text GLOB '*～*' OR text GLOB '*~*'
                THEN 1.0 ELSE 0.0 END) FROM messages
                WHERE user_id=? AND text IS NOT NULL AND LENGTH(text)>=2''', (u,)).fetchone()[0] or 0.0
        g = snap.get(u, 'unknown')
        arows.append({'alias': led_alias[u], 'softness': round(float(soft), 3),
                      'community': comm,
                      'card_gender': prof.get(u, '') or 'unknown',
                      'label': g or 'unknown'})
    with io.open(os.path.join(a.out, 'data', 'annotations_deidentified.csv'),
                 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['alias', 'softness', 'community', 'card_gender', 'label'])
        w.writeheader(); w.writerows(arows)
    con.close()

    # ---- 人工抽审子样本 ----
    audit_rng = random.Random(SEED + 1)
    audit_idx = sorted(audit_rng.sample(range(len(rows)), min(a.audit, len(rows))))
    with io.open(os.path.join(a.out, 'audit', 'random_audit.csv'), 'w',
                 encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['msg_id', 'day', 'group', 'text'])
        for i in audit_idx:
            r = rows[i]
            w.writerow([r['msg_id'], r['day'], r['group'], r['text']])

    # ---- manifest ----
    days = sorted({r['day'] for r in rows if r['day'] != 'unknown'})
    by_group = {}
    for r in rows:
        by_group[r['group']] = by_group.get(r['group'], 0) + 1
    manifest = {
        'version': 'v1',
        'generated': '2026-09-08',
        'rules_version': 'R6-2026-09-08',
        'seed': SEED,
        'messages': {'total': len(rows), 'by_group': by_group,
                     'days_covered': len(days),
                     'day_min': days[0] if days else None, 'day_max': days[-1] if days else None},
        'annotations': {'speakers': len(arows)},
        'excluded_from_messages': ['190 labeled ledger speakers (text only; fields released separately)',
                                   'author account', 'system/bot accounts', 'empty texts'],
        'note': 'Otome groups are released in full (non-ledger portion) so the cross-community scan can be reproduced.',
    }
    blob = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
    manifest['sha256_manifest'] = hashlib.sha256(blob).hexdigest()
    with io.open(os.path.join(a.out, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"消息样例 {len(rows)} 条（{by_group}）；标注表 {len(arows)} 人；抽审 {len(audit_idx)} 条")


if __name__ == '__main__':
    main()
