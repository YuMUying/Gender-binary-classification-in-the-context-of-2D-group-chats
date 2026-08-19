# -*- coding: utf-8 -*-
"""analyze_errors.py — v7 判错用户 + 新增达标用户分析"""
import csv
import sqlite3

# v7 错误用户
rows = list(csv.DictReader(open('outputs/score-v7-all.csv', encoding='utf-8')))
errs = [r for r in rows if r.get('correct') == '0']
print(f'=== v7 判错用户: {len(errs)} 个 ===')
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']
for r in sorted(errs, key=lambda x: -float(x['prob_female_mean'])):
    print(f"{r['user_id']} | {nick.get(int(r['user_id']), '?')[:12]} | {r['n_messages']}条 | P(女)={r['prob_female_mean']} | "
          f"std={r['prob_female_std']} | 判{r['predicted']} | 标注={r['label']}")

# 参考包里的新用户（对比：之前 70 人，现在 75 人——找新出现的）
ref = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
print(f'\n参考包: {len(ref)} 人')
# 与已标注用户重叠检查（参考包应全部未标注）
labeled = {r['user_id'] for r in conn.execute("SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')")}
overlap = [r for r in ref if int(r['QQ号']) in labeled]
print(f'与已标注重叠（异常）: {len(overlap)}')
for r in overlap:
    print('  ', r['QQ号'], r['昵称'], r['消息数'], 'P(女)=', r['P(女)'])

# 5 个新增达标用户：查 eff>=100 但之前不在的——通过 score-v7-all 的 n_messages 无法直接对比，
# 用 6-15 之前活跃的用户（缺失区新增消息带来的样本）
print('\n=== 缺失区(6-15前)活跃的未标注用户 Top ===')
for r in conn.execute("""
    SELECT user_id, COUNT(*) c FROM messages 
    WHERE scene='group' AND peer_id=826904606 AND time < 1781537480 
      AND user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
    GROUP BY user_id HAVING c >= 50 ORDER BY c DESC LIMIT 15"""):
    print(f"  {r['user_id']} | {nick.get(r['user_id'], '?')[:12]} | 缺失区{r['c']}条")
conn.close()
