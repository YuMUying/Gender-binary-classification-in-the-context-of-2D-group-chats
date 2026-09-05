# -*- coding: utf-8 -*-
import json, io, sys, torch, sqlite3, collections
sys.stdout.reconfigure(encoding='utf-8')
torch.set_num_threads(8)
ROOT = os.environ.get("QQBOT_ROOT", ".")
from transformers import BertForSequenceClassification, BertTokenizerFast
tok = BertTokenizerFast.from_pretrained('hfl/chinese-roberta-wwm-ext')
dev = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'device={dev}')
con = sqlite3.connect(ROOT + r'\main\main.db', timeout=60)
lab = {r[0]: r[1] for r in con.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
con.close()
# 语料按用户聚合
agg = collections.defaultdict(list)
for line in io.open(ROOT + r'\trainsets\export-s0v58-raw.jsonl', encoding='utf-8-sig'):
    r = json.loads(line)
    u = r.get('user_id')
    if u in lab and isinstance(u, int):
        if len(agg[u]) < 600:  # 每用户采样上限600条(评估用)
            agg[u].append(str(r.get('text', ''))[:128])
print(f'待推理用户: {len(agg)}')
# 三seed模型
models = []
for seed in (7, 8, 9):
    ckpt = torch.load(ROOT + rf'\models\r3-s0v56\seed{seed}\model.pt', map_location=dev, weights_only=False)
    m = BertForSequenceClassification.from_pretrained(ckpt['model_name'], num_labels=3)
    m.load_state_dict(ckpt['state'])
    m.to(dev).eval()
    models.append(m)
B = 256
pf = collections.defaultdict(float)
with torch.no_grad():
    for u, texts in agg.items():
        ps = []
        for mi in range(0, len(texts), B):
            batch = texts[mi:mi+B]
            enc = tok(batch, padding=True, truncation=True, max_length=128, return_tensors='pt').to(dev)
            logits = sum(m(**enc).logits for m in models) / len(models)
            p = logits.softmax(-1).cpu()
            ps.extend(p[:, 2].tolist())  # P_female=index2?
        pf[u] = sum(ps) / len(ps)
print('P_female分布(三seed均值, 每用户消息级平均):')
# 分账本组统计
import statistics
bands = collections.Counter()
bylab = collections.defaultdict(list)
for u, v in pf.items():
    bylab[lab[u]].append(v)
    if v < 0.15:
        bands['auto(<0.15)'] += 1
    elif v <= 0.35:
        bands['ABSTAIN(0.15-0.35)'] += 1
    else:
        bands['female(>0.35)'] += 1
print(f'全体{len(pf)}用户: {dict(bands)}')
for g in ('female', 'male'):
    vs = bylab[g]
    n_ab = sum(1 for v in vs if 0.15 <= v <= 0.35)
    n_f = sum(1 for v in vs if v > 0.35)
    print(f'  真实{g}({len(vs)}人): P_female mean={statistics.mean(vs):.3f} median={statistics.median(vs):.3f} | 拒绝带{n_ab}({n_ab*100/len(vs):.1f}%) 判F带{n_f}({n_f*100/len(vs):.1f}%)')
# 落盘
import csv
with io.open(ROOT + r'\staging\abstain-eval-s0v56.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['user_id', 'true_label', 'p_female'])
    for u, v in sorted(pf.items(), key=lambda x: -x[1]):
        w.writerow([u, lab[u], f'{v:.4f}'])
print('明细已存staging/abstain-eval-s0v56.csv')
