# -*- coding: utf-8 -*-
"""gender_speech.py — 性别话语统计：称呼类 + 性发泄类（供人工标定参考）

对每个已标注用户统计：
  A. 称呼他人：老婆/妈妈/小萝莉/爹/哥哥姐姐 等
  B. 性发泄/粗口性：操死/干死/操你/想操/舔/射 等
输出：分性别"使用过该词的用户占比" + "人均使用率"，用于人工标定时交叉判断
"""
import re
import sqlite3
from collections import Counter, defaultdict

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

# 话语模式组
PATTERNS = {
    '叫老婆': re.compile(r'老婆(?!婆)|娘子|夫人|媳妇|wife'),
    '叫妈妈': re.compile(r'妈妈|妈咪|妈妈桑|亲妈'),
    '叫爸爸/爹': re.compile(r'爸爸|爹|爹地|亲爹|爸爸桑'),
    '叫小萝莉/妹妹': re.compile(r'小萝莉|萝莉|妹妹|女儿'),
    '叫哥哥/姐姐': re.compile(r'哥哥|姐姐|欧尼|お姉|兄长'),
    '性发泄(操死你类)': re.compile(r'操死|干死|操你|干你|草你|艹你|肏|日你|想操|想干|想日|射你|舔你|吸你|上你|扑倒'),
    '性化索取(来点萝莉等)': re.compile(r'来(?:点|几个|只|个|一下)?[^\s]{0,6}(萝莉|猫娘|女仆|护士|黑丝|白丝|涩图|色图)|发(?:涩|色)图|涩图'),
    '粗口(卧槽等)': re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦'),
}

user_texts = defaultdict(list)
for r in conn.execute("SELECT user_id, text FROM messages WHERE text IS NOT NULL AND LENGTH(text) > 0"):
    uid = r['user_id']
    if uid in labels:
        user_texts[uid].append(r['text'] or '')
conn.close()

print(f'已标注用户: {len(labels)}（男{sum(1 for l in labels.values() if l=="male")}/女{sum(1 for l in labels.values() if l=="female")}）\n')
print(f'{"话语组":<22}{"男使用占比":<12}{"女使用占比":<12}{"方向":<8}示例用户')
print('-' * 80)

for name, pat in PATTERNS.items():
    male_use, female_use = [], []
    male_users, female_users = [], []
    for uid, g in labels.items():
        texts = user_texts[uid]
        n = len(texts)
        if n == 0:
            continue
        hits = sum(1 for t in texts if pat.search(t))
        rate = hits / n
        if g == 'male':
            male_use.append(rate)
            if hits:
                male_users.append(uid)
        else:
            female_use.append(rate)
            if hits:
                female_users.append(uid)
    m_ratio = len(male_users) / max(len(male_use), 1)
    f_ratio = len(female_users) / max(len(female_use), 1)
    m_mean = sum(male_use) / max(len(male_use), 1)
    f_mean = sum(female_use) / max(len(female_use), 1)
    direction = '男>女' if m_ratio > f_ratio else ('女>男' if f_ratio > m_ratio else '≈')
    ex = f'男例:{male_users[:2]} 女例:{female_users[:2]}'
    print(f'{name:<20}{m_ratio:<12.0%}{f_ratio:<12.0%}{direction:<8}{ex}')
    print(f'{"":<20}(人均使用率 男={m_mean:.4f} 女={f_mean:.4f})')

# 交叉判定规则提示
print()
print('=== 人工标定参考规则（基于以上统计，随标注量更新）===')
print('若目标用户大量使用"性发泄类"话语 → 男性倾向显著（见上方占比）')
print('若目标用户高频叫别人"老婆/老公" → 男性倾向（ACG圈男性玩梗）')
print('"叫妈妈/小萝莉/妹妹" 需看语境：女用户也可能用（需结合其他信号）')
