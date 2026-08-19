# -*- coding: utf-8 -*-
"""LLM 少样本直判：对测试集每个用户做性别判定（与 BERT 对照/融合）
用法：python train/judge_llm.py --test ../data/val.jsonl --train ../data/train.jsonl
"""
import argparse
import json
import random
import sys
import time
import urllib.request
from collections import defaultdict

from common import load_jsonl, LABEL_MAP, ID2LABEL


def load_config():
    cfg_path = 'llm-config.json'
    cfg = {}
    try:
        with open(cfg_path, encoding='utf-8-sig') as f:
            cfg = json.load(f)
    except Exception:
        pass
    import os
    return {
        "base_url": os.environ.get("LLM_BASE_URL") or cfg.get("base_url") or "https://api.deepseek.com/v1",
        "api_key": os.environ.get("LLM_API_KEY") or cfg.get("api_key") or "",
        "model": os.environ.get("LLM_MODEL") or cfg.get("model") or "deepseek-chat",
    }


def chat(cfg, messages, tries=3):
    body = json.dumps({"model": cfg["model"], "messages": messages, "max_tokens": 300, "temperature": 0.0}).encode()
    url = cfg["base_url"].rstrip('/') + '/chat/completions'
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, method='POST', headers={
                'Content-Type': 'application/json', 'Authorization': f'Bearer {cfg["api_key"]}'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())['choices'][0]['message']['content']
        except Exception as e:
            print('LLM err', e, file=sys.stderr)
            time.sleep(2)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', default='../data/train.jsonl')
    ap.add_argument('--test', default='../data/val.jsonl')
    ap.add_argument('--per-user', type=int, default=20, help='每人取样消息数')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()
    cfg = load_config()
    rng = random.Random(args.seed)

    train = load_jsonl(args.train)
    test = load_jsonl(args.test)

    # 构建 few-shot 样例：3男3女，每人 6 条
    by_user = defaultdict(list)
    for r in train:
        by_user[(r['user_id'], r['label'])].append(r['text'])
    exemplars = []
    for label, want in [('male', 3), ('female', 3)]:
        users = [(k, v) for k, v in by_user.items() if k[1] == label]
        rng.shuffle(users)
        for (uid, _), texts in users[:want]:
            for t in rng.sample(texts, min(6, len(texts))):
                exemplars.append(f"[{label}] {t}")
    rng.shuffle(exemplars)
    ex_text = '\n'.join(exemplars)

    # 测试用户分组
    test_users = defaultdict(list)
    test_label = {}
    for r in test:
        test_users[r['user_id']].append(r['text'])
        test_label[r['user_id']] = r['label']

    correct = 0
    rows = []
    for uid, texts in sorted(test_users.items(), key=lambda kv: -len(kv[1])):
        sample = rng.sample(texts, min(args.per_user, len(texts)))
        prompt = ("下面是某个 QQ 群成员的若干条发言。请根据发言风格判断该成员的性别（男/女）。"
                  "参考样例（已标注性别）：\n" + ex_text +
                  "\n\n待判断成员的部分发言：\n" + '\n'.join(sample) +
                  "\n\n请只输出 JSON：{\"gender\": \"male\" 或 \"female\", \"confidence\": 0到1}")
        out = chat(cfg, [{"role": "user", "content": prompt}])
        pred, conf = None, None
        if out:
            try:
                m = json.loads(out[out.find('{'):out.rfind('}') + 1])
                pred = 'female' if '女' in str(m.get('gender', '')) or m.get('gender') == 'female' else 'male'
                conf = float(m.get('confidence', 0.5))
            except Exception:
                pred = 'female' if '女' in out else 'male'
                conf = 0.5
        else:
            pred, conf = 'male', 0.0
        hit = pred == test_label[uid]
        correct += hit
        rows.append((uid, test_label[uid], pred, conf, len(texts)))
        print(f'QQ {uid} 真={test_label[uid]} 判={pred} conf={conf} ({len(texts)}条) {"✓" if hit else "✗"}')
        time.sleep(0.5)

    print(f'\nLLM 判定用户级: {correct}/{len(rows)} ({correct/len(rows):.1%})')
    fs = [r for r in rows if r[1] == 'female']
    ms = [r for r in rows if r[1] == 'male']
    print(f'女性 {sum(1 for r in fs if r[1] == r[2])}/{len(fs)} | 男性 {sum(1 for r in ms if r[1] == r[2])}/{len(ms)}')


if __name__ == '__main__':
    main()
