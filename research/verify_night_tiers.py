# -*- coding: utf-8 -*-
import json
import sqlite3

# 模拟 nightWeight 保护逻辑（与 export-dataset.js 一致）
def nightWeight(ratio):
    if ratio <= 0.3:
        return 0.5
    if ratio <= 0.6:
        return 0.7
    return 0.9

print('=== 保护档位有效样本比 ===')
for r in [0.1, 0.25, 0.3, 0.35, 0.5, 0.6, 0.65, 0.8, 0.95]:
    eff = (1 - r) + r * nightWeight(r)
    print(f'深夜占比={r:.2f} → 降权={nightWeight(r)} → 有效样本比={eff:.2f}')

print('\n=== 训练用户中全量消息 <200 的深夜占比（应触发降权档位）===')
conn = sqlite3.connect('data/qqchat.db')
seen = set()
for l in open('data/_night-test-train.jsonl', encoding='utf-8'):
    r = json.loads(l)
    seen.add(r['user_id'])
small = []
for uid in seen:
    rr = conn.execute(
        "SELECT COUNT(*) c, SUM(CASE WHEN strftime('%H', time, 'unixepoch', '+8 hours') IN "
        "('00','01','02','03','04','05') THEN 1 ELSE 0 END) night FROM messages WHERE user_id=?", (int(uid),)).fetchone()
    if rr[0] < 200:
        small.append((uid, rr[0], rr[1] / max(rr[0], 1)))
small.sort(key=lambda x: -x[2])
print(f'少样本训练用户: {len(small)} 人')
for uid, c, ratio in small[:20]:
    print(f'  {uid}: 全量{c}条 深夜占比={ratio:.2f} → 应降权 {nightWeight(ratio)}')
conn.close()
