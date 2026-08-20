# -*- coding: utf-8 -*-
"""xnn_predict.py — XNN 男娘指数全库推理（BERT 概率 + 统计混合）

输入: models/xnn-bert（BERT 模型）、outputs/xnn_index.csv（统计指数）
输出: outputs/xnn_final.csv（混合指数 0-100）

混合规则（与用户确认）：统计为主 0.65 + BERT 0.35
（统计特征（词级区分度）目前比 BERT 更可靠）
"""
import csv
import json
import math
import os
import sqlite3
import statistics
from collections import defaultdict

import torch
from torch.utils.data import DataLoader

from common import prepare_text

STAT_W = 0.65   # 统计指数权重
BERT_W = 0.35   # BERT 概率权重


def load_model(model_dir, device):
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    ckpt = torch.load(os.path.join(model_dir, "model.pt"), map_location=device, weights_only=False)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    cfg = AutoConfig.from_pretrained(model_dir)
    cfg.num_labels = 2
    base = AutoModelForSequenceClassification.from_config(cfg)
    from train_foi import FoiModel
    model = FoiModel(base, 1, 0.0).to(device)
    model.load_state_dict(ckpt["state"], strict=False)
    model.eval()
    return model, tokenizer, ckpt


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="models/xnn-bert")
    ap.add_argument("--out", default="outputs/xnn_final.csv")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--min-per-user", type=int, default=50)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    model, tokenizer, ckpt = load_model(args.model_dir, device)
    use_nickname = ckpt.get("use_nickname", False)
    print(f"[模型] {args.model_dir} | {device}")

    # 读全库消息
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
        db_path = json.load(f).get('database', 'data/qqchat.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    msgs = [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, nickname, card
        FROM messages WHERE scene IN ('group','private') AND LENGTH(text) > 0
        ORDER BY user_id, time ASC""").fetchall()]
    # orientation 标签对照
    labels = {}
    for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
        labels[r['user_id']] = r['orientation']
    conn.close()
    print(f"[数据] 全库 {len(msgs)} 条消息")

    # 按用户分批推理
    by_user = defaultdict(list)
    for m in msgs:
        by_user[m['user_id']].append(m)

    # 统计指数表
    stat_map = {}
    with open(os.path.join(root, 'outputs', 'xnn_index.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                stat_map[int(row['QQ号'])] = float(row['XNN男娘指数'])
            except (ValueError, KeyError):
                continue

    results = []
    for uid, umsgs in by_user.items():
        if len(umsgs) < args.min_per_user:
            continue
        # BERT 推理
        texts = [{'text': m['text'], 'nickname': m.get('nickname'), 'card': m.get('card')} for m in umsgs]
        probs = []
        for i in range(0, len(texts), args.batch):
            batch = texts[i:i + args.batch]
            enc = tokenizer([prepare_text(r, use_nickname) for r in batch],
                            max_length=args.max_len, truncation=True, padding="max_length",
                            return_tensors="pt")
            with torch.no_grad():
                logits, _ = model(enc["input_ids"].to(device), enc["attention_mask"].to(device))
            probs.extend(torch.softmax(logits, dim=1)[:, 1].cpu().tolist())
        p_mean = sum(probs) / len(probs)
        # BERT 指数：概率 → 0-100（0.2→0, 0.8→100）
        bert_foi = 100 * max(0, min(1, (p_mean - 0.2) / 0.6))
        # 混合
        stat_foi = stat_map.get(uid)
        if stat_foi is not None:
            mix = STAT_W * stat_foi + BERT_W * bert_foi
            src = 'both'
        else:
            mix = bert_foi
            src = 'bert'
        results.append({
            'user_id': uid, 'n_messages': len(umsgs),
            'stat_foi': round(stat_foi, 1) if stat_foi is not None else '',
            'bert_foi': round(bert_foi, 1),
            'xnn_index': round(mix, 1),
            'source': src,
            'orientation': labels.get(uid, ''),
        })

    results.sort(key=lambda r: -r['xnn_index'])
    os.makedirs(os.path.dirname(args.out), exist_ok=True) if os.path.dirname(args.out) else None
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['user_id', 'n_messages', 'stat_foi', 'bert_foi', 'xnn_index', 'source', 'orientation'])
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"\n[完成] {args.out}（{len(results)} 用户）")
    print("\n=== 真实 orientation 用户 ===")
    for r in results:
        if r['orientation']:
            print(f"  {r['user_id']} [{r['orientation']}] n={r['n_messages']} stat={r['stat_foi']} bert={r['bert_foi']} XNN={r['xnn_index']}")
    print("\n=== TOP 20 ===")
    for r in results[:20]:
        print(f"  {r['user_id']} n={r['n_messages']} XNN={r['xnn_index']} [{r['source']}] {r['orientation']}")


if __name__ == "__main__":
    main()
