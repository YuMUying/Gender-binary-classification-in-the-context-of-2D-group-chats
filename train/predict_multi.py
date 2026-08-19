# -*- coding: utf-8 -*-
"""predict_multi.py — 多版本模型全库打分 → 跨版本分歧度（误判风险代理）

用法: python train/predict_multi.py --models bert-v4,bert-v5,bert-v6,bert-v7
输出 outputs/score-multi.csv: user_id, n_messages, p_v4, p_v5, p_v6, p_v7,
     mean, std, range, flip_count, pred_v7, disagreement(高/中/低)
"""
import argparse
import csv
import json
import math
import os
import statistics
import sqlite3

import torch

from predict import load_metrics, predict_rows

MODELS = ['bert-v4', 'bert-v5', 'bert-v6', 'bert-v7']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', default=','.join(MODELS))
    ap.add_argument('--batch', type=int, default=96)
    ap.add_argument('--max-len', type=int, default=128)
    ap.add_argument('--out', default='outputs/score-multi.csv')
    ap.add_argument('--device', default='auto')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    device = args.device if args.device != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu')
    model_list = [m.strip() for m in args.models.split(',') if m.strip()]

    # 数据
    with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
        db_path = json.load(f).get('database', 'data/qqchat.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, nickname, card
        FROM messages WHERE scene IN ('group','private') AND LENGTH(text) > 0
        ORDER BY time ASC""").fetchall()]
    labels = {}
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
        labels[r['user_id']] = r['gender']
    conn.close()
    print(f'[数据] {len(rows)} 条消息, 模型: {model_list}, 设备: {device}')

    from transformers import AutoConfig, AutoTokenizer, AutoModelForSequenceClassification
    from train_bert import GenderModel

    per_model = {}
    for m in model_list:
        model_dir = os.path.join(root, 'models', m)
        ckpt = torch.load(os.path.join(model_dir, 'model.pt'), map_location=device, weights_only=False)
        tok = AutoTokenizer.from_pretrained(model_dir)
        cfg = AutoConfig.from_pretrained(model_dir)
        cfg.num_labels = 2
        base = AutoModelForSequenceClassification.from_config(cfg)
        model = GenderModel(base, cfg.hidden_size, 1, 0.0).to(device)
        model.load_state_dict(ckpt['state'], strict=False)
        model.eval()
        use_nickname = ckpt.get('use_nickname', False)
        use_context = ckpt.get('use_context', False)
        use_avatar = ckpt.get('use_avatar', False)
        use_profile = ckpt.get('use_profile', False)
        per_user = predict_rows(model, tok, rows, device, args.batch, args.max_len,
                                use_nickname, use_context, use_avatar, use_profile)
        per_model[m] = per_user
        print(f'  {m}: 完成 ({len(per_user)} 用户)')

    # v7 阈值
    _, metrics = load_metrics(os.path.join(root, 'models', model_list[-1]))
    threshold = metrics.get('threshold', 0.5)

    uids = set()
    for d in per_model.values():
        uids |= set(d.keys())

    out_rows = []
    for u in sorted(uids):
        ps = {m: (sum(per_model[m].get(u, [])) / max(len(per_model[m].get(u, [])), 1)) if per_model[m].get(u) else None
              for m in model_list}
        vals = [v for v in ps.values() if v is not None]
        if not vals:
            continue
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        rng = max(vals) - min(vals)
        p7 = ps.get(model_list[-1])
        pred7 = 'female' if p7 is not None and p7 >= threshold else 'male'
        flips = 0
        if p7 is not None:
            for m in model_list[:-1]:
                p = ps.get(m)
                if p is not None:
                    if (p >= threshold) != (p7 >= threshold):
                        flips += 1
        # 分歧度分级
        if std >= 0.10 or flips >= 2 or rng >= 0.25:
            disagree = '高'
        elif std >= 0.05 or flips == 1 or rng >= 0.12:
            disagree = '中'
        else:
            disagree = '低'
        row = {'user_id': u, 'n_messages': len(per_model[model_list[0]].get(u, [])),
               'mean': round(mean, 4), 'std': round(std, 4), 'range': round(rng, 4),
               'flip_count': flips, 'pred_v7': pred7, 'disagreement': disagree}
        for m in model_list:
            row[f'p_{m}'] = round(ps[m], 4) if ps[m] is not None else ''
        row['label'] = labels.get(u, '')
        out_rows.append(row)

    out_rows.sort(key=lambda r: -r['std'])
    with open(os.path.join(root, args.out), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    from collections import Counter
    print(f'[完成] {len(out_rows)} 用户 → {args.out}')
    print('分歧度分布:', dict(Counter(r['disagreement'] for r in out_rows)))
    print('高分歧用户数:', sum(1 for r in out_rows if r['disagreement'] == '高'))


if __name__ == '__main__':
    main()
