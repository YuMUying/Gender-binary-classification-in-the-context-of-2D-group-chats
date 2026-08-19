# -*- coding: utf-8 -*-
"""extract_inline_forward.py — 从转发信封 JSON 中提取嵌套内联消息入库（source='forward'）

与 src/utils.js 的 cqToText 占位符规则保持一致；按 message_id 去重，可反复运行。
用法: python research/extract_inline_forward.py
"""
import json
import re
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA busy_timeout=15000')


def cq_to_text(segments):
    out = []
    for s in segments or []:
        d = s.get('data') or {}
        t = s.get('type')
        if t == 'text':
            out.append(d.get('text') or '')
        elif t == 'at':
            out.append(f"@{d.get('name') or d.get('qq') or ''}")
        elif t == 'face':
            out.append(f"[表情:{d.get('id') or ''}]")
        elif t == 'image':
            out.append(f"[图片:{d.get('summary') or ''}]")
        elif t == 'record':
            out.append('[语音]')
        elif t == 'video':
            out.append('[视频]')
        elif t == 'file':
            out.append(f"[文件:{d.get('name') or ''}]")
        elif t == 'reply':
            txt = d.get('text')
            out.append(f"「引用:{txt[:50]}」" if txt else '')
        elif t == 'forward':
            out.append('[合并转发]')
        elif t == 'json':
            out.append(f"[JSON:{d.get('data') or ''}]")
        elif t == 'xml':
            out.append('[XML]')
        elif t == 'markdown':
            out.append(d.get('content') or '')
    return ' '.join(x for x in out if x).strip()


def walk(msgs, depth, inserted, dup):
    if depth > 8:
        return
    for m in msgs or []:
        scene = 'group' if m.get('message_type') == 'group' else 'private'
        uid = (m.get('sender') or {}).get('user_id') or m.get('user_id')
        if scene == 'group':
            peer = m.get('group_id') or uid
        else:
            peer = uid
        if peer is None or uid is None:
            continue
        mid = m.get('real_id') or m.get('message_id') or m.get('msgId') or m.get('msg_id')
        if mid is None:
            continue
        text = cq_to_text(m.get('message'))
        rec = {
            'scene': scene, 'peer_id': peer,
            'message_id': str(mid),
            'message_seq': m.get('real_seq') if m.get('real_seq') is not None else m.get('message_seq'),
            'group_name': m.get('group_name'),
            'user_id': uid,
            'nickname': (m.get('sender') or {}).get('nickname'),
            'card': (m.get('sender') or {}).get('card'),
            'time': m.get('time') or 0,
            'text': text,
            'raw_json': json.dumps(m, ensure_ascii=False),
            'source': 'forward',
        }
        try:
            cur = conn.execute("""
                INSERT OR IGNORE INTO messages (scene, peer_id, message_id, message_seq, group_name,
                    user_id, nickname, card, time, text, raw_json, source)
                VALUES (:scene, :peer_id, :message_id, :message_seq, :group_name,
                    :user_id, :nickname, :card, :time, :text, :raw_json, :source)""", rec)
            if cur.rowcount:
                inserted[0] += 1
            else:
                dup[0] += 1
        except Exception as e:
            print(f'[!] 写入失败 {uid} {mid}: {e}')
        # 递归嵌套
        for seg in m.get('message') or []:
            if seg.get('type') == 'forward' and isinstance((seg.get('data') or {}).get('content'), list):
                walk(seg['data']['content'], depth + 1, inserted, dup)


envelopes = conn.execute('SELECT content_raw FROM forwards').fetchall()
inserted, dup = [0], [0]
for e in envelopes:
    try:
        walk(json.loads(e['content_raw']).get('messages'), 0, inserted, dup)
    except Exception as ex:
        print(f'[!] 信封解析失败: {ex}')
conn.commit()
print(f'[完成] 新增入库 {inserted[0]} 条（重复跳过 {dup[0]} 条）')
conn.close()
