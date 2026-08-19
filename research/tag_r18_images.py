# -*- coding: utf-8 -*-
"""tag_r18_images.py — 对已缓存图片做 R18 等级判定（gpt-5.5 视觉）并入库

等级: 0=正常 1=擦边(暗示/性感) 2=露骨R18 3=无法判定
输出: DB 表 image_r18_tags + research/image_r18_tags.jsonl
用法: $env:RELAY_KEY='sk-...'; python research/tag_r18_images.py
"""
import base64
import json
import os
import sqlite3
import time
import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
PIC_DIR = r'C:\Users\Lenovo\Documents\Tencent Files\1394876195\nt_qq\nt_data\Pic'

PROMPT = """请判断这张图片是否包含成人/色情内容。只输出JSON：{"level": 0或1或2, "note": "简短原因(10字内)"}
level 定义：
0 = 正常内容（风景/日常/角色立绘/非暗示内容）
1 = 擦边（性感着装、暗示、暧昧，但无露骨暴露）
2 = 露骨 R18（明显性内容、裸露敏感部位、性行为暗示或描绘）
注意：动漫风格下，泳装/紧身衣/胖次若只是普通展示算1；直接裸露敏感部位或明确性内容算2。
如果无法判断或图片无法解析，输出 {"level": 3, "note": "无法判定"}"""


def judge(file_path, retries=2):
    with open(file_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
        ]}],
        'max_tokens': 200,
        'temperature': 0,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                d = json.loads(content[s:e + 1])
                return int(d.get('level', 3)), str(d.get('note', ''))[:30]
            return 3, '解析失败'
        except Exception as ex:
            if attempt == retries:
                return 3, f'API错误:{str(ex)[:20]}'
            time.sleep(4)


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    # 收集图片文件（大图优先，跳过 0 字节）
    files = []
    for root, _, fns in os.walk(PIC_DIR):
        for fn in fns:
            p = os.path.join(root, fn)
            sz = os.path.getsize(p)
            if sz > 1000:
                files.append((p, sz))
    files.sort(key=lambda x: -x[1])
    print(f'待判定图片: {len(files)} 张')

    conn = sqlite3.connect('data/qqchat.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS image_r18_tags (
        file_name TEXT PRIMARY KEY,
        level INTEGER,
        note TEXT,
        source TEXT,
        tagged_at INTEGER)''')

    results = []
    for i, (p, sz) in enumerate(files):
        fn = os.path.basename(p)
        level, note = judge(p)
        results.append({'file_name': fn, 'level': level, 'note': note})
        conn.execute('INSERT OR REPLACE INTO image_r18_tags VALUES (?,?,?,?,?)',
                     (fn, level, note, 'gpt-5.5', int(time.time())))
        print(f'[{i + 1}/{len(files)}] {fn} ({sz // 1024}KB) → level={level} {note}')
        if (i + 1) % 10 == 0:
            conn.commit()
        time.sleep(1)
    conn.commit()

    with open('research/image_r18_tags.jsonl', 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    from collections import Counter
    print('\n分布:', dict(Counter(r['level'] for r in results)))
    print(f'[完成] {len(results)} 张 → image_r18_tags 表 + research/image_r18_tags.jsonl')
    conn.close()


if __name__ == '__main__':
    main()
