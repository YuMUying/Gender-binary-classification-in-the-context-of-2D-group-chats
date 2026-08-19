# -*- coding: utf-8 -*-
"""tag_harvest.py — 收割图片打标：视觉描述 → v2 分级标签 → 追加贴纸标签表

读 research/harvest_map.jsonl，对每张图 gpt-5.5 描述 + 文本打标，
追加到 outputs/贴纸标签v2.csv（rank=HVxxxx，断点续跑）
用法: $env:RELAY_KEY='sk-...'; python research/tag_harvest.py
"""
import base64
import csv
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

KEY = os.environ.get('RELAY_KEY', '')
URL = 'https://api.vibefree.top/v1/chat/completions'
MODEL = 'gpt-5.5'
MAP = 'research/harvest_map.jsonl'
TAG_CSV = 'outputs/贴纸标签v2.csv'

DESC_PROMPT = """这是一个QQ聊天中的图片/表情包。请仔细观察后用中文输出 JSON（不要其他文字）：
{
 "content": "画面内容：角色类型/数量/装扮/动作/场景，具体一些",
 "style": "画风：Q版/正常比例/抽象扭曲/像素/真人照片/动物拟人/文字图等，以及色彩特点",
 "emotion": "主要情绪（如：害羞/发呆装傻/坏笑/疲惫/无语/得意/生气/哭/撒娇/搞笑等）",
 "atmosphere": "氛围（软萌/沙雕/嘲讽/温馨/色气/日常等）",
 "erotic": "是否涩情/色气/性暗示：是/否，是则说明程度（轻微/明显/露骨）",
 "text": "图中文字内容（无则写无）",
 "overall": "一句话概括"
}"""

TAXO_PROMPT = """根据描述，为这张图片打标签，输出JSON：
{"emotion":"...","style":"...","ero":0,"meme":"有/无","moe":"是/否"}
emotion 只能选一个：撒娇卖萌/发呆装傻/疲惫困倦/无语无奈/委屈哭/生气嫌弃/得意坏笑/开心兴奋/搞怪沙雕/中性
style 只能选一个：Q版/正常比例/抽象/真人/其他
ero 是涩情等级整数：0无/1轻微/2明显/3露骨
meme 指是否有文字梗：有/无
moe 画风是否萌系：是/否
只输出JSON。"""


def call(messages, max_tokens, retries=3):
    body = {'model': MODEL, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                j = json.loads(resp.read().decode())
            content = j['choices'][0]['message']['content']
            s = content.find('{'); e = content.rfind('}')
            if s >= 0 and e > s:
                return json.loads(content[s:e + 1])
            return {'error': content[:120]}
        except Exception as ex:
            if attempt == retries - 1:
                return {'error': str(ex)}
            time.sleep(2 * (attempt + 1))


def load_jpeg_b64(fn):
    from PIL import Image
    im = Image.open(fn)
    im.seek(0)
    im = im.convert('RGB')
    im.thumbnail((640, 640))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def main():
    if not KEY:
        print('请设置 RELAY_KEY'); return
    entries = [json.loads(l) for l in open(MAP, encoding='utf-8') if l.strip()]
    # 断点：已打标的 url
    done_urls = set()
    with open(TAG_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('url'):
                done_urls.add(r['url'])
    todo = [e for e in entries if e['url'] not in done_urls]
    print(f'待打标: {len(todo)}（已完成 {len(entries) - len(todo)}）')

    def work(e):
        try:
            b64 = load_jpeg_b64(e['local'])
        except Exception:
            return e, None
        d = call([{'role': 'user', 'content': [
            {'type': 'text', 'text': DESC_PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
        ]}], 700)
        if 'error' in d:
            return e, None
        t = call([{'role': 'user', 'content': TAXO_PROMPT + '\n\n描述：' + json.dumps(d, ensure_ascii=False)}], 120)
        return e, t

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(work, e): e for e in todo}
        for fut in as_completed(futs):
            e, t = fut.result()
            if t and t.get('emotion'):
                results.append((e, t))
            done += 1
            if done % 100 == 0 or done == len(todo):
                print(f'进度 {done}/{len(todo)}')
            if len(results) >= 100:
                with open(TAG_CSV, 'a', encoding='utf-8', newline='') as f:
                    w = csv.writer(f)
                    for e, t in results:
                        w.writerow(['HV' + e['md5'][:8], e['url'], 0, e.get('summary') or '',
                                    t['emotion'], t['style'], t['ero'], t['meme'], t['moe'], ''])
                results = []
    with open(TAG_CSV, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        for e, t in results:
            w.writerow(['HV' + e['md5'][:8], e['url'], 0, e.get('summary') or '',
                        t['emotion'], t['style'], t['ero'], t['meme'], t['moe'], ''])
    print(f'[完成] 本次新增 {len(results)} 条 → {TAG_CSV}')


if __name__ == '__main__':
    main()
