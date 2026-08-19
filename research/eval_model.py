# -*- coding: utf-8 -*-
"""eval_model.py — 评估新模型：验证集用户级准确率 + 难例检查

用法：
  python train/predict.py --model-dir models/bert-v7 --from-db --min-per-user 0 --out outputs/score-v7-all.csv
  python research/eval_model.py --csv outputs/score-v7-all.csv --model-dir models/bert-v7
"""
import argparse
import csv
import json
import os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True, help='predict.py --from-db 输出的 CSV')
    ap.add_argument('--model-dir', default='models/bert-v7')
    ap.add_argument('--val', default='data/val.jsonl')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, args.model_dir, 'metrics.json'), encoding='utf-8') as f:
            threshold = json.load(f).get('threshold', 0.5)
    except Exception:
        threshold = 0.5

    # 预测 CSV
    pred = {}
    with open(args.csv, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            pred[int(r['user_id'])] = r

    # 验证集用户（含标签）
    val_users = {}
    with open(os.path.join(root, args.val), encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            val_users.setdefault(r['user_id'], r['label'])

    print(f'模型: {args.model_dir} | 阈值: {threshold:.3f} | 验证集用户: {len(val_users)} 人')
    print(f'{"QQ":<12}{"真实":<7}{"预测":<7}{"P(女)均值":<10}{"std":<7}{"条数":<6}{"置信度":<8}标记')
    rows = []
    for uid, label in sorted(val_users.items(), key=lambda x: -x[0]):
        r = pred.get(uid)
        if not r:
            print(f'{uid:<12}{label:<7}未打分')
            continue
        p = float(r['prob_female_mean'])
        pred_lab = r['predicted']
        mark = '✓' if pred_lab == label else '✗'
        rows.append((uid, label, pred_lab))
        print(f'{uid:<12}{label:<7}{pred_lab:<7}{p:<10.3f}{r["prob_female_std"]:<7}{r["n_messages"]:<6}{r["confidence"]:<8}{mark}')
    if rows:
        correct = sum(1 for _, t, p in rows if t == p)
        print(f'\n验证集用户级准确率: {correct}/{len(rows)} = {correct/len(rows):.2%}')
        f_ok = sum(1 for _, t, p in rows if t == 'female' and t == p)
        m_ok = sum(1 for _, t, p in rows if t == 'male' and t == p)
        f_n = sum(1 for _, t, _ in rows if t == 'female')
        m_n = sum(1 for _, t, _ in rows if t == 'male')
        print(f'女: {f_ok}/{f_n} | 男: {m_ok}/{m_n}')

    # 难例检查
    hard = [3441452166, 1399716483, 972242500, 2604093609]
    print('\n=== 难例 ===')
    for uid in hard:
        r = pred.get(uid)
        if r:
            print(f'{uid}: P(女)={float(r["prob_female_mean"]):.3f} 预测={r["predicted"]} 标注={r.get("label") or "未标"} 条数={r["n_messages"]} 置信度={r["confidence"]}')
        else:
            print(f'{uid}: 未打分')

if __name__ == '__main__':
    main()
