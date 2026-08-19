# -*- coding: utf-8 -*-
"""check_envelope2.py — 检查信封内容中的视频/大文件"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== media_files schema ===')
r = conn.execute("SELECT sql FROM sqlite_master WHERE name='media_files'").fetchone()
print(r[0] if r else '无 media_files 表')

print('\n=== 8-17 的合并转发信封内容扫描（video/文件元素）===')
rows = conn.execute("""
    SELECT forward_id, envelope_user, fetched_at, content_raw FROM forwards 
    WHERE fetched_at > 1786950000 ORDER BY fetched_at""").fetchall()
print(f'该时段 forwards: {len(rows)} 条')
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        msgs = j.get('messages') or []
        for m in msgs:
            segs = m.get('message') or []
            for seg in segs:
                if not isinstance(seg, dict):
                    continue
                t = seg.get('type')
                d = seg.get('data') or {}
                if t in ('video', 'file', 'record'):
                    print(f'  forward={str(r["forward_id"])[:20]} user={m.get("user_id")} '
                          f'type={t} name={d.get("name") or d.get("file") or d.get("path") or ""} '
                          f'size={d.get("file_size") or d.get("size") or "?"}')
    except Exception as e:
        print(f'  解析失败 {str(r["forward_id"])[:20]}: {e}')

print('\n=== 信封内容里的图片/视频资源 url 统计 ===')
vid_urls = set()
for r in rows:
    try:
        j = json.loads(r['content_raw'])
        for m in (j.get('messages') or []):
            for seg in (m.get('message') or []):
                if isinstance(seg, dict) and seg.get('type') == 'video':
                    d = seg.get('data') or {}
                    vid_urls.add(d.get('url') or d.get('file') or str(d)[:80])
    except Exception:
        pass
print(f'信封中 video 元素数: {len(vid_urls)}')
for u in list(vid_urls)[:10]:
    print('  ', u[:100])
conn.close()
