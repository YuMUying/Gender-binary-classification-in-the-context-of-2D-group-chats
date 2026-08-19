# -*- coding: utf-8 -*-
"""show_erotic.py — 列出某用户的涩情消息（按等级）"""
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

UID = int(sys.argv[1]) if len(sys.argv) > 1 else 3494489531
MIN_LVL = int(sys.argv[2]) if len(sys.argv) > 2 else 3


class D(Dataset):
    def __init__(self, rows, tok, ml=128):
        self.rows = rows
        self.tok = tok
        self.ml = ml

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        t = self.rows[i][2][:500]
        e = self.tok(t, max_length=self.ml, truncation=True, padding='max_length', return_tensors='pt')
        return e['input_ids'][0], e['attention_mask'][0], self.rows[i][0]


conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
rows = [(r['id'], r['user_id'], r['text']) for r in conn.execute(
    'SELECT id, user_id, text FROM messages WHERE user_id=? AND text IS NOT NULL AND LENGTH(text)>0', (UID,))]
conn.close()

tok = AutoTokenizer.from_pretrained('models/erotic-bert')
model = AutoModelForSequenceClassification.from_pretrained('models/erotic-bert')
model.eval()
preds = {}
with torch.no_grad():
    dl = DataLoader(D(rows, tok), batch_size=64)
    for input_ids, mask, mids in dl:
        logits = model(input_ids=input_ids, attention_mask=mask).logits
        for m, p in zip(mids.tolist(), logits.argmax(dim=1).tolist()):
            preds[m] = p

LEVEL = ['无', '轻微', '明显', '露骨']
cst = timezone(timedelta(hours=8))
out = [(m, t, preds.get(m, 0)) for m, uid, t in rows if preds.get(m, 0) >= MIN_LVL]
out.sort(key=lambda x: -x[2])
print(f'{UID} 等级≥{MIN_LVL} 的消息: {len(out)} 条')
for m, t, p in out:
    print(f'[{LEVEL[p]}] {t[:120]!r}')
