# -*- coding: utf-8 -*-
"""import_qce.py — 导入 qce 导出的群消息 JSON 到数据库

用法: python research/import_qce.py <导出的json路径> [--peer 826904606]
去重策略：
  1) 预查 (scene, peer_id, user_id, time, text) 是否已存在 → 跳过（防与 DB 已有行重复）
  2) INSERT OR IGNORE（uq_msg 唯一索引 scene+peer_id+message_id 防 qce 文件间重复）
  3) 二次去重：同 user_id+time+text 的 qce 行清理
"""
import json
import re
import sqlite3
import sys
import time


def clean_text(content):
    """把导出消息 content 转成纯文本（dict{text,elements} / 字符串 / 列表）"""
    if content is None:
        return ''
    if isinstance(content, dict):
        t = content.get('text')
        if t:
            return t
        # text 为空时从 elements 拼
        parts = []
        for seg in content.get('elements') or []:
            if not isinstance(seg, dict):
                continue
            st = seg.get('type') or ''
            d = seg.get('data') or {}
            if st == 'text':
                parts.append(d.get('text') or '')
            elif st == 'at':
                parts.append('@' + str(d.get('uin') or d.get('qq') or ''))
            elif st == 'face':
                parts.append(f"[表情:{d.get('id', '')}]")
            elif st in ('image', 'pic'):
                parts.append('[图片]')
            elif st in ('video', 'audio', 'file'):
                parts.append(f'[{st}]')
            else:
                parts.append(f'[{st}]')
        return ' '.join(p for p in parts if p).strip()
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, dict):
                t = seg.get('type') or seg.get('segmentType') or ''
                d = seg.get('data') or seg.get('content') or ''
                if t in ('text', 'at', ''):
                    if isinstance(d, str):
                        parts.append(d)
                    elif isinstance(d, dict):
                        parts.append(d.get('text') or d.get('qq') or '')
                elif t == 'face':
                    parts.append(f"[表情:{d.get('id', '') if isinstance(d, dict) else d}]")
                elif t == 'image':
                    parts.append('[图片]')
                else:
                    parts.append(f'[{t}]')
            else:
                parts.append(str(seg))
        return ' '.join(parts).strip()
    return str(content)


def extract_peer(path, arg_peer):
    if arg_peer:
        return int(arg_peer)
    m = re.search(r'[_-](friend|group|temp)_(\d+)', path)
    if m:
        return int(m.group(2))
    m2 = re.search(r'(\d{5,12})', path)
    if m2:
        return int(m2.group(1))
    return None


def main():
    if len(sys.argv) < 2:
        print('用法: python research/import_qce.py <json> [--peer 群号]'); return
    path = sys.argv[1]
    arg_peer = None
    if '--peer' in sys.argv:
        arg_peer = sys.argv[sys.argv.index('--peer') + 1]

    data = json.load(open(path, encoding='utf-8'))
    msgs = data.get('messages') or []
    chat = data.get('chatInfo') or {}
    peer_id = extract_peer(path, arg_peer)
    if peer_id is None:
        print(f'[错误] 无法从文件名/参数确定 peer_id: {path}')
        return
    self_uin = str(chat.get('selfUin') or '2740088195')
    group_name = chat.get('name')
    print(f'读取 {path}')
    print(f'消息数: {len(msgs)} | peer_id={peer_id} | 群名={group_name} | selfUin={self_uin}')

    conn = sqlite3.connect('data/qqchat.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=15000')

    inserted = 0
    dup_file = 0       # 与 qce 文件内/文件间重复（uq_msg 命中）
    existing = 0       # DB 已有同 user+time+text
    n_self = 0
    n_empty = 0
    INS_SQL = '''INSERT OR IGNORE INTO messages
        (scene, peer_id, message_id, message_seq, group_name, user_id, nickname, card, time, text, raw_json, source, collected_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'''

    CHK_SQL = '''SELECT 1 FROM messages WHERE scene='group' AND peer_id=? AND user_id=? AND time=? AND text=? LIMIT 1'''

    now = int(time.time())
    for m in msgs:
        sender = m.get('sender') or {}
        uid = sender.get('uin') or sender.get('user_id') or sender.get('uid')
        if uid is None:
            uid = m.get('userUin') or m.get('userId')
        if uid is None:
            continue
        if str(uid) in (self_uin, 'u_RWybSE8wn35flVR_J5qd3g'):
            n_self += 1
            continue
        mid = str(m.get('id') or m.get('messageId') or '')
        if not mid:
            continue
        # timestamp 为毫秒（13位）→ 秒；秒级（10位）原样
        t = m.get('timestamp') or 0
        try:
            t = int(t)
            if t > 100000000000:   # 毫秒
                t = t // 1000
        except (TypeError, ValueError):
            t = int(time.time())
        txt = clean_text(m.get('content'))
        if not txt:
            n_empty += 1
            continue
        nick = sender.get('nickname') or sender.get('nick') or None
        card = sender.get('card') or None
        seq = m.get('seq')
        # 预查 DB 已有（内容级去重）
        hit = conn.execute(CHK_SQL, (peer_id, str(uid), t, txt[:2000])).fetchone()
        if hit:
            existing += 1
            continue
        r = conn.execute(INS_SQL, (
            'group', peer_id, mid, seq, group_name, str(uid),
            nick, card, t, txt[:2000], json.dumps(m, ensure_ascii=False)[:4000], 'qce', now))
        if r.rowcount:
            inserted += 1
        else:
            dup_file += 1
    conn.commit()

    # 二次去重：同 user_id+time+text 的 qce 行（不同 message_id）
    print('二次去重...')
    rows = conn.execute("""
        SELECT id, user_id, time, text FROM messages
        WHERE source='qce' ORDER BY id""").fetchall()
    seen = {}
    del_ids = []
    for r in rows:
        key = (r['user_id'], r['time'], r['text'][:200])
        if key in seen:
            del_ids.append(r['id'])
        else:
            seen[key] = r['id']
    if del_ids:
        conn.executemany('DELETE FROM messages WHERE id=?', [(i,) for i in del_ids])
        conn.commit()
    print(f'[完成] 新增 {inserted} 条（DB已存在 {existing}，文件内重复 {dup_file}，跳过机器人 {n_self}，空文本 {n_empty}，二次去重删除 {len(del_ids)}）')
    total = conn.execute('SELECT COUNT(*) c FROM messages').fetchone()['c']
    print(f'messages 总数: {total:,}')
    conn.close()


if __name__ == '__main__':
    main()
