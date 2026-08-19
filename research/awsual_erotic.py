# -*- coding: utf-8 -*-
"""awsual_erotic.py — 复查 769967529 (awsual) 涩情等级并补人工标签

1. 用本地 erotic-bert 逐条预测 awsual 的消息
2. 输出所有 预测等级>=1 的消息 + 文本
3. 按用户指示"涩情等级应为高/露骨(2-3)"写入人工标签：
   预测1→2，预测2→2，预测3→3（人工标注优先于模型/LLM）
4. 更新后重新统计该用户特征
用法: python research/awsual_erotic.py
"""
import json
import os
import sqlite3
from collections import Counter

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

UID = 769967529
OUT = 'research/erotic_labels.jsonl'


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


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = AutoTokenizer.from_pretrained(os.path.join(root, 'models/erotic-bert'))
    model = AutoModelForSequenceClassification.from_pretrained(os.path.join(root, 'models/erotic-bert')).to(device)
    model.eval()

    conn = sqlite3.connect(os.path.join(root, 'data/qqchat.db'))
    conn.row_factory = sqlite3.Row
    rows = [(r['id'], r['user_id'], r['text']) for r in conn.execute(
        'SELECT id, user_id, text FROM messages WHERE user_id=? AND text IS NOT NULL AND LENGTH(text)>0', (UID,))]
    conn.close()
    print(f'awsual 消息: {len(rows)} 条')

    dl = DataLoader(D(rows, tok), batch_size=64)
    preds = {}
    with torch.no_grad():
        for input_ids, mask, mids in dl:
            logits = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
            for m, p in zip(mids.tolist(), logits.argmax(dim=1).cpu().tolist()):
                preds[m] = p

    LEVEL = ['无', '轻微', '明显', '露骨']
    ero_msgs = [(m, t, preds[m]) for m, uid, t in rows if preds.get(m, 0) >= 1]
    ero_msgs.sort(key=lambda x: -x[2])
    print(f'\n=== 模型判定的涩情消息（{len(ero_msgs)} 条）===')
    for m, t, p in ero_msgs:
        print(f'  [{LEVEL[p]}] {t[:60]!r}')

    # 关键词命中但模型判0的（可能被低估）
    import re
    KW = re.compile(r'涩|色(?!彩)|欲|本子|裸|胸|乳|内裤|操|艹|高潮|射|发情|黄油|白丝|泳装|性感|骚|湿|做爱|约炮|摸胸|涩图')
    miss = [(m, t) for m, uid, t in rows if preds.get(m, 0) == 0 and KW.search(t)]
    print(f'\n=== 关键词命中但模型判0（{len(miss)} 条，疑似低估）===')
    for m, t in miss[:15]:
        print(f'  {t[:60]!r}')

    # 写入人工标签：预测>=1 → max(2, 预测)；预测3保持3
    manual = []
    for m, t, p in ero_msgs:
        lvl = max(2, p)
        manual.append({'id': m, 'user_id': UID, 'text': t[:200], 'level': lvl})
    with open(os.path.join(root, OUT), 'a', encoding='utf-8') as f:
        for rec in manual:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'\n[人工标签] 写入 {len(manual)} 条（预测1/2→2级，预测3→3级）→ {OUT}')

    # 更新后用户级统计
    allr = [json.loads(l) for l in open(os.path.join(root, OUT), encoding='utf-8') if l.strip()]
    mine = [r for r in allr if r['user_id'] == UID]
    c = Counter(r['level'] for r in mine)
    print(f'awsual 人工+自动标签合计: {len(mine)} 条, 分布: {dict(c)}')


if __name__ == '__main__':
    main()
