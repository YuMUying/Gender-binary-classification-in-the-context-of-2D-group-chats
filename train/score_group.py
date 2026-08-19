# -*- coding: utf-8 -*-
"""score_group.py — 对指定群的全部用户批量性别推理，输出 Markdown/CSV 报告

用法：
  python train/score_group.py --group 826904606 --model-dir models/bert-v6 \
      --out-md outputs/群1用户性别推理.md --out-csv outputs/群1用户性别推理.csv
"""
import argparse
import csv
import json
import os
import sqlite3
import statistics

from predict import predict_rows, load_metrics, confidence_for

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--group', type=int, required=True, help='群号')
    ap.add_argument('--model-dir', default='models/bert-v6')
    ap.add_argument('--min-msgs', type=int, default=5, help='低于该消息数的用户不推理（另行列出）')
    ap.add_argument('--out-md', default='outputs/group-score.md')
    ap.add_argument('--out-csv', default='outputs/group-score.csv')
    ap.add_argument('--batch', type=int, default=64)
    ap.add_argument('--max-len', type=int, default=128)
    ap.add_argument('--device', default='auto')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
        db_path = json.load(f).get('database', 'data/qqchat.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)

    device = args.device if args.device != 'auto' else ('cuda' if __import__('torch').cuda.is_available() else 'cpu')
    from transformers import AutoConfig, AutoTokenizer, AutoModelForSequenceClassification
    from train_bert import GenderModel

    ckpt = __import__('torch').load(os.path.join(args.model_dir, 'model.pt'), map_location=device, weights_only=False)
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    cfg = AutoConfig.from_pretrained(args.model_dir)
    cfg.num_labels = 2
    base = AutoModelForSequenceClassification.from_config(cfg)
    model = GenderModel(base, cfg.hidden_size, 1, 0.0).to(device)
    model.load_state_dict(ckpt['state'], strict=False)
    model.eval()
    threshold, _ = load_metrics(args.model_dir)

    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row

    # 群内用户：发言数、最新全局昵称、最新群名片
    users = {}
    for r in conn.execute("""
        SELECT user_id, COUNT(*) c FROM messages
        WHERE scene='group' AND peer_id=? GROUP BY user_id""", (args.group,)):
        users[r['user_id']] = {'n': r['c']}
    for uid in users:
        nick = conn.execute("SELECT nickname FROM user_profiles WHERE user_id=?" , (uid,)).fetchone()
        users[uid]['nickname'] = nick['nickname'] if nick and nick['nickname'] else ''
        card = conn.execute("""
            SELECT card FROM messages WHERE peer_id=? AND user_id=? AND card IS NOT NULL AND card != ''
            ORDER BY time DESC LIMIT 1""", (args.group, uid)).fetchone()
        users[uid]['card'] = card['card'] if card else ''
    # 标签
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels"):
        if r['user_id'] in users:
            users[r['user_id']]['label'] = r['gender']

    # 消息行（仅群内消息，供打分）
    rows = [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, nickname, card
        FROM messages WHERE scene='group' AND peer_id=? AND LENGTH(text) > 0
        ORDER BY time ASC""", (args.group,)).fetchall()]
    conn.close()
    print(f'[数据] 群 {args.group}：用户 {len(users)} 人，消息 {len(rows)} 条')

    # 训练/验证集归属
    train_set = set()
    val_set = set()
    for fname, s in [('data/train.jsonl', train_set), ('data/val.jsonl', val_set)]:
        p = os.path.join(root, fname)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        s.add(json.loads(line)['user_id'])

    # 打分
    per_user = predict_rows(model, tokenizer, rows, device, args.batch, args.max_len,
                            ckpt.get('use_nickname', False), ckpt.get('use_context', False))

    report = []
    skipped = []
    for uid, info in users.items():
        ps = per_user.get(uid, [])
        n_msgs = len(ps)
        if n_msgs < args.min_msgs:
            skipped.append({'user_id': uid, **info, 'n': n_msgs})
            continue
        mean = sum(ps) / n_msgs
        med = statistics.median(ps)
        std = statistics.pstdev(ps) if n_msgs > 1 else 0.0
        pred = 'female' if mean >= threshold else 'male'
        conf = confidence_for(n_msgs, mean, threshold)
        label = info.get('label', '')
        if uid in train_set:
            split = 'train'
        elif uid in val_set:
            split = 'val'
        else:
            split = 'unlabeled'
        report.append({
            'user_id': uid, 'nickname': info.get('nickname', ''), 'card': info.get('card', ''),
            'n_msgs': n_msgs, 'mean': round(mean, 4), 'median': round(med, 4), 'std': round(std, 4),
            'pred': pred, 'conf': conf, 'label': label, 'split': split,
        })

    report.sort(key=lambda r: (-int(r['n_msgs'])))
    skipped.sort(key=lambda r: -int(r['n']))

    # CSV
    os.makedirs(os.path.dirname(args.out_csv) or '.', exist_ok=True)
    with open(args.out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['user_id', 'nickname', 'card', 'n_msgs', 'mean', 'median',
                                          'std', 'pred', 'conf', 'label', 'split'])
        w.writeheader()
        w.writerows(report)

    # Markdown
    conf_cn = {'high': '高', 'low-data': '低(样本不足)', 'borderline': '临界(需复核)'}
    split_cn = {'train': '✅ 训练集', 'val': '🔶 测试集', 'unlabeled': '❌ 未标注'}
    lines = []
    lines.append(f'# 群 {args.group} 用户性别推理报告')
    lines.append('')
    lines.append(f'- 模型：{os.path.basename(args.model_dir)}（校准阈值 {threshold:.3f}）')
    lines.append(f'- 设备：{device}｜群内用户 {len(users)} 人，其中达到推理门槛（≥{args.min_msgs} 条）{len(report)} 人')
    lines.append(f'- 结论统计：男 {sum(1 for r in report if r["pred"]=="male")} 人 / 女 {sum(1 for r in report if r["pred"]=="female")} 人')
    lines.append('')
    lines.append('| QQ号 | 全局昵称 | 群昵称 | 发言数 | 女概率均值 | 结论 | 置信度 | 训练集 | 已标注 |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for r in report:
        lines.append(f'| {r["user_id"]} | {r["nickname"]} | {r["card"]} | {r["n_msgs"]} | {r["mean"]:.3f} '
                     f'| {r["pred"]} | {conf_cn[r["conf"]]} | {split_cn[r["split"]]} | {r["label"] or "—"} |')
    if skipped:
        lines.append('')
        lines.append(f'## 样本不足（<{args.min_msgs} 条，未推理，共 {len(skipped)} 人）')
        lines.append('')
        lines.append('| QQ号 | 全局昵称 | 群昵称 | 消息数 |')
        lines.append('|---|---|---|---|')
        for s in skipped:
            lines.append(f'| {s["user_id"]} | {s.get("nickname","")} | {s.get("card","")} | {s["n"]} |')
    os.makedirs(os.path.dirname(args.out_md) or '.', exist_ok=True)
    with open(args.out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'[完成] 报告 {len(report)} 人 → {args.out_md}')
    print(f'       CSV → {args.out_csv}')

if __name__ == '__main__':
    main()
