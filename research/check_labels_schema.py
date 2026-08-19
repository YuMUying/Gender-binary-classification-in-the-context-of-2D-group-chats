# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('data/qqchat.db')
for r in conn.execute('SELECT sql FROM sqlite_master WHERE name="speaker_labels"'):
    print(r[0])
print('---')
for r in conn.execute('SELECT * FROM speaker_labels LIMIT 3'):
    print(dict(r))
conn.close()
