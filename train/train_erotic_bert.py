# -*- coding: utf-8 -*-
"""train_erotic_bert.py — 涩情分级本地模型训练（0/1/2/3 四类，按用户划分防泄漏）

用法:
  python train/train_erotic_bert.py --labels research/erotic_labels.jsonl \
      --out-dir models/erotic-bert --epochs 5 --batch 16 --lr 2e-5
"""
import argparse
import json
import os
import random
from collections import Counter, defaultdict

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup

LEVELS = ['无', '轻微', '明显', '露骨']


class EroticDataset(Dataset):
    def __init__(self, rows, tokenizer, max_len):
        self.rows = rows
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        text = self.rows[i]['text'][:500]
        enc = self.tok(text, max_length=self.max_len, truncation=True, padding='max_length', return_tensors='pt')
        return enc['input_ids'][0], enc['attention_mask'][0], self.rows[i]['level']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--labels', required=True)
    ap.add_argument('--out-dir', default='models/erotic-bert')
    ap.add_argument('--base', default='hfl/chinese-roberta-wwm-ext')
    ap.add_argument('--epochs', type=int, default=5)
    ap.add_argument('--batch', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--max-len', type=int, default=128)
    ap.add_argument('--val-users', type=int, default=8, help='按用户划分：随机抽出N个用户做验证')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    labels_path = args.labels if os.path.isabs(args.labels) else os.path.join(root, args.labels.replace('../', ''))
    rows = []
    for l in open(labels_path, encoding='utf-8'):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    print(f'[数据] 共 {len(rows)} 条: ' + str(dict(Counter(r['level'] for r in rows))))

    random.seed(args.seed)
    users = sorted(set(r['user_id'] for r in rows))
    random.shuffle(users)
    val_users = set(users[:args.val_users])
    train_rows = [r for r in rows if r['user_id'] not in val_users]
    val_rows = [r for r in rows if r['user_id'] in val_users]
    print(f'[划分] 训练 {len(train_rows)} 条 ({len(users) - args.val_users} 用户) / 验证 {len(val_rows)} 条 ({args.val_users} 用户)')

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'[设备] {device}')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')   # 本地缓存加载，避免联网
    tok = AutoTokenizer.from_pretrained(args.base)
    cfg = AutoConfig.from_pretrained(args.base, num_labels=4)
    model = AutoModelForSequenceClassification.from_pretrained(args.base, config=cfg).to(device)

    train_ds = EroticDataset(train_rows, tok, args.max_len)
    val_ds = EroticDataset(val_rows, tok, args.max_len)
    dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=64)

    # 类别权重（平衡）
    counts = Counter(r['level'] for r in train_rows)
    total = sum(counts.values())
    weights = torch.tensor([total / max(counts.get(i, 0), 1) for i in range(4)], dtype=torch.float).to(device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

    steps_per_epoch = len(dl)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, num_warmup_steps=steps_per_epoch // 10,
                                            num_training_steps=steps_per_epoch * args.epochs)

    def evaluate():
        model.eval()
        y_true, y_pred = [], []
        with torch.no_grad():
            for input_ids, mask, lev in val_dl:
                logits = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
                preds = logits.argmax(dim=1).cpu().tolist()
                y_true += lev.tolist()
                y_pred += preds
        from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
        acc = accuracy_score(y_true, y_pred)
        macro = f1_score(y_true, y_pred, average='macro', zero_division=0)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2, 3])
        return acc, macro, cm, y_true, y_pred

    best_macro = 0
    for ep in range(args.epochs):
        model.train()
        tl = 0
        for bi, (input_ids, mask, lev) in enumerate(dl):
            out = model(input_ids=input_ids.to(device), attention_mask=mask.to(device))
            loss = loss_fn(out.logits, lev.to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tl += loss.item()
        acc, macro, cm, yt, yp = evaluate()
        print(f'[epoch {ep + 1}] loss={tl / len(dl):.4f} val_acc={acc:.3f} macroF1={macro:.3f}')
        print(' 混淆矩阵(行=真, 列=预, 0无/1轻/2明/3露):')
        for i in range(4):
            print(f'   真{LEVELS[i]}({sum(1 for y in yt if y == i)}): ' + ' '.join(f'{cm[i][j]}' for j in range(4)))
        if macro > best_macro:
            best_macro = macro
            os.makedirs(os.path.join(root, args.out_dir), exist_ok=True)
            model.save_pretrained(os.path.join(root, args.out_dir))
            tok.save_pretrained(os.path.join(root, args.out_dir))
            with open(os.path.join(root, args.out_dir, 'metrics.json'), 'w', encoding='utf-8') as f:
                json.dump({'val_acc': acc, 'macro_f1': macro, 'n_train': len(train_rows),
                           'n_val': len(val_rows), 'levels': LEVELS,
                           'train_dist': dict(Counter(r['level'] for r in train_rows))}, f, ensure_ascii=False, indent=2)
    print(f'\n[完成] 最优 macroF1={best_macro:.3f} → {args.out_dir}')


if __name__ == '__main__':
    main()
