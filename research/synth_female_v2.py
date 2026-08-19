# -*- coding: utf-8 -*-
"""synth_female_v2.py — LLM 合成不同风格女性样本（独立文件，不混入主库）

风格：正常女 / 抽象女 / 萌系女 / 群聊糙女（对齐群内女性真实分布）/ 深夜女
输出：data/synth-female-v2.jsonl（user_id 9000100000+ 隔离段，source=llm-v2）
用法: $env:RELAY_KEY='sk-...'; python research/synth_female_v2.py [--per-style 400]
"""
import argparse
import json
import os
import sqlite3
import time
import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
OUT = 'data/synth-female-v2.jsonl'

STYLES = {
    'normal': '一个普通中国年轻女性，日常聊天风格：聊生活、工作、追剧追番、游戏、朋友吐槽，语气自然女性化但绝不刻意，不卖萌不装嫩，像真实的群聊发言',
    'abstract': '一个混二次元群聊的年轻女性，抽象玩梗风格：说话简短、爱用网络梗、阴阳怪气、吐槽、无厘头，可能带一点粗口但不过分，非常口语化',
    'moe': '一个撒娇卖萌的年轻女性：语气词多（呢/啦/喵/嘛/捏/呜呜/嘤），语气软、可爱，爱用颜文字和叠词',
    'rough': '一个在熟人二次元群里放得很开的年轻女性：说话粗犷、会讲脏话（卧槽/妈的/草）、爱开车开玩笑、荤段子调侃、自称兄弟，语气豪爽（注意：她确实是女性，这是群内真实风格）',
    'night': '一个深夜还在聊天的年轻女性：感性、emo、情绪化，聊心事、感情、孤独感、深夜感想，语气低沉真诚',
}

STYLE_NOTE = {
    'normal': '每条10-60字，日常口语，不要重复开头',
    'abstract': '每条5-40字，简短有梗，像群聊里随手打的',
    'moe': '每条10-50字，可爱但不要油腻',
    'rough': '每条10-60字，放得开但不过度，不是色情内容',
    'night': '每条15-80字，真诚的深夜感想',
}

def gen_batch(style, n, retries=3):
    json_example = '[{"text": "..."}, ...]'
    prompt = f"""你是语料生成器。请以【{STYLES[style]}】的身份生成 {n} 条独立的QQ群聊消息（她发的单条消息，不是对话）。
{STYLE_NOTE[style]}
要求：真实自然、多样化、不重复模板；禁止自我介绍；禁止出现"作为一个AI/女生"等表述；禁止明显违反内容安全（不允许色情露骨、政治敏感）。
只输出JSON数组，如 {json_example}"""
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 3000,
        'temperature': 1.0,
    }
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
                texts = [x['text'].strip() for x in arr if isinstance(x, dict) and x.get('text')]
                return [t for t in texts if 3 <= len(t) <= 200]
            return []
        except Exception as ex:
            if attempt == retries - 1:
                print(f'  [{style}] 批次失败: {ex}')
                return []
            time.sleep(3 * (attempt + 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-style', type=int, default=400)
    args = ap.parse_args()
    if not KEY:
        print('请设置 RELAY_KEY'); return

    # 已有真实文本（去重用）
    conn = sqlite3.connect('data/qqchat.db')
    real = {r[0] for r in conn.execute("SELECT text FROM messages WHERE text IS NOT NULL AND LENGTH(text) BETWEEN 3 AND 200")}
    conn.close()
    print(f'真实文本池: {len(real)}')

    # 已有合成
    seen = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            try:
                seen.add(json.loads(l)['text'])
            except Exception:
                pass
    print(f'已有合成: {len(seen)}')

    all_rows = []
    uid_base = 9000100000
    for style, desc in STYLES.items():
        got = 0
        batch_no = 0
        while got < args.per_style and batch_no < 30:
            batch_no += 1
            need = min(40, args.per_style - got)
            texts = gen_batch(style, need)
            new = [t for t in texts if t not in seen and t not in real]
            for t in new:
                all_rows.append({'text': t, 'label': 'female', 'user_id': uid_base + len(all_rows),
                                 'group_id': 0, 'time': int(time.time()), 'source': 'llm-v2', 'style': style})
                seen.add(t)
            got += len(new)
            print(f'  [{style}] 批次{batch_no}: 生成{len(texts)} 新增{len(new)} (累计{got}/{args.per_style})')
            if len(texts) == 0:
                break
            time.sleep(1)
        print(f'[{style}] 完成: {got} 条')

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n[完成] {len(all_rows)} 条 → {OUT}')

if __name__ == '__main__':
    main()
