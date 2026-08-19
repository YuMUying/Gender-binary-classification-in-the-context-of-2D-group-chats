import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/data/qqchat.db', { readOnly: true });
for (const uid of [2121888461, 843573361]) {
  const r = db.prepare("SELECT COUNT(*) c, SUM(CASE WHEN LENGTH(text)>=4 THEN 1 ELSE 0 END) eff, MAX(nickname) n FROM messages WHERE user_id=?").get(uid);
  console.log(`QQ ${uid} (${r.n ?? '?'}): 总 ${r.c} 条 / 有效 ${r.eff ?? 0} 条`);
}
db.close();
