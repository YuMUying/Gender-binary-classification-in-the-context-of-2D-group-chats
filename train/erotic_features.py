# -*- coding: utf-8 -*-
"""erotic_features.py — 用本地 erotic-bert 对全库用户消息打分 → 用户级涩情特征

输出 outputs/erotic_features_all.csv：
  user_id, total, ero_any, ero_max, ero_ratio, ero_msg_1/2/3 计数, label(已知时)
用法: python train/erotic_features.py [--model-dir models/erotic-bert] [--batch 96]
"""
import argparse
import csv
import json
import os
import sqlite3
from collections import defaultdict

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer


class MsgDataset(Dataset):
    def __init__(self, rows, tokenizer, max_len):
        self.rows = rows
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        text = self.rows[i][2][:500]
        enc = self.tok(text, max_length=self.max_len, truncation=True, padding='max_length', return_tensors='pt')
        return enc['input_ids'][0], enc['attention_mask'][0], self.rows[i][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-dir', default='models/erotic-bert')
    ap.add_argument('--batch', type=int, default=96)
    ap.add_argument('--max-len', type=int, default=128)
    ap.add_argument('--out', default='outputs/erotic_features_all.csv')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = AutoTokenizer.from_pretrained(os.path.join(root, args.model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(os.path.join(root, args.model_dir)).to(device)
    model.eval()
    print(f'[模型] {args.model_dir} | {device}')

    conn = sqlite3.connect(os.path.join(root, 'data/qqchat.db'))
    conn.row_factory = sqlite3.Row
    rows = [tuple(r) for r in conn.execute(
        "SELECT user_id, id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0")]
    labels = {}
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
        labels[r['user_id']] = r['gender']
    conn.close()
    print(f'[数据] {len(rows)} 条消息')

    ds = MsgDataset(rows, tok, args.max_len)
    dl = DataLoader(ds, batch_size=args.batch)
    per_user = defaultdict(list)
    with torch.no_grad():
        for input_ids, mask, uids in dl:
            logits = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
            preds = logits.argmax(dim=1).cpu().tolist()
            for u, p in zip(uids.tolist(), preds):
                per_user[u].append(p)

    out_rows = []
    for u, levels in per_user.items():
        total = len(levels)
        c1 = sum(1 for x in levels if x == 1)
        c2 = sum(1 for x in levels if x == 2)
        c3 = sum(1 for x in levels if x == 3)
        any_ero = 1 if (c1 + c2 + c3) else 0
        mx = max(levels) if levels else 0
        out_rows.append({
            'user_id': u, 'total': total,
            'ero_any': any_ero, 'ero_max': mx,
            'ero_ratio': round((c1 + c2 + c3) / total, 4),
            'lvl1': c1, 'lvl2': c2, 'lvl3': c3,
            'label': labels.get(u, ''),
        })
    out_rows.sort(key=lambda r: -r['total'])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(os.path.join(root, args.out), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['user_id', 'total', 'ero_any', 'ero_max', 'ero_ratio',
                                          'lvl1', 'lvl2', 'lvl3', 'label'])
        w.writeheader()
        w.writerows(out_rows)
    print(f'[完成] {len(out_rows)} 用户 → {args.out}')

    # 分性别统计（已标注）
    from collections import Counter
    for g in ('male', 'female'):
        grp = [r for r in out_rows if r['label'] == g]
        if not grp:
            continue
        any1 = sum(1 for r in grp if r['ero_any'])
        mx3 = sum(1 for r in grp if r['ero_max'] == 3)
        mx2 = sum(1 for r in grp if r['ero_max'] == 2)
        print(f'{g} ({len(grp)}人): 参与={any1} ({any1/len(grp):.0%}) 露骨3={mx3} 明显2={mx2}')


if __name__ == '__main__':
    main()
