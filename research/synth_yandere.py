# -*- coding: utf-8 -*-
"""synth_yandere.py — 病娇/阴郁暴躁女 合成（追加到 synth-female-v2.jsonl，隔离 user_id 9000100006）

风格：病娇（偏执占有/控制欲）+ 暴躁挑衅 + 阴郁感
注意：避免自杀/自残等极端内容，聚焦性格语气
用法: $env:RELAY_KEY='sk-...'; python research/synth_yandere.py [--n 400]
"""
import argparse
import json
import os
import time
import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
OUT = 'data/synth-female-v2.jsonl'

STYLE = '一个二次元群里的"病娇"女性：表面阴郁、说话带压迫感和占有欲，偶尔暴躁挑衅、阴阳怪气；对人（尤其特定对象）有偏执的在意和控制欲，会半开玩笑地威胁（"你要是敢回别人消息试试"）；语气低沉带黑暗感，但不涉及自杀自残、不违法内容'

def gen_batch(n, retries=3):
    json_example = '[{"text": "..."}, ...]'
    prompt = f"""你是语料生成器。请以【{STYLE}】的身份生成 {n} 条独立的QQ群聊消息（她发的单条消息）。
每条5-40字，真实自然、多样化；可以是怼人、阴阳怪气、威胁（玩笑性质）、占有欲发言、阴郁感想。
禁止：自杀/自残/血腥/违法犯罪/色情露骨内容；禁止自我介绍；禁止"作为一个AI"表述。
只输出JSON数组，如 {json_example}"""
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 3000, 'temperature': 1.0}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('['); e = content.rfind(']')
            if s >= 0 and e > s:
                arr = json.loads(content[s:e + 1])
                return [x['text'].strip() for x in arr if isinstance(x, dict) and x.get('text') and 3 <= len(x['text']) <= 200]
            return []
        except Exception as ex:
            if attempt == retries - 1:
                print(f'批次失败: {ex}')
                return []
            time.sleep(3 * (attempt + 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=400)
    args = ap.parse_args()
    if not KEY:
        print('请设置 RELAY_KEY'); return

    # 已有文本去重
    seen = set()
    existing = []
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            try:
                r = json.loads(l)
                seen.add(r['text'])
                existing.append(r)
            except Exception:
                pass
    print(f'已有: {len(existing)} 条')

    got = 0
    batch_no = 0
    new_rows = []
    while got < args.n and batch_no < 30:
        batch_no += 1
        need = min(40, args.n - got)
        texts = gen_batch(need)
        new = [t for t in texts if t not in seen]
        for t in new:
            new_rows.append({'text': t, 'label': 'female', 'user_id': 9000100006,
                             'group_id': 0, 'time': int(time.time()), 'source': 'llm-v2', 'style': 'yandere'})
            seen.add(t)
        got += len(new)
        print(f'批次{batch_no}: 生成{len(texts)} 新增{len(new)} (累计{got}/{args.n})')
        if not texts:
            break
        time.sleep(1)

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in existing + new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'[完成] 病娇新增 {len(new_rows)} 条, 总计 {len(existing) + len(new_rows)} → {OUT}')

if __name__ == '__main__':
    main()
