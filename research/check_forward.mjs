import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync('G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset/data/qqchat.db', { readOnly: true });
// 1) 私聊消息总览
const priv = db.prepare("SELECT scene, peer_id, COUNT(*) c FROM messages WHERE scene='private' GROUP BY peer_id").all();
console.log('私聊消息分布:', JSON.stringify(priv));
// 2) 2633083674 的私聊消息里含 forward 段的行
const rows = db.prepare("SELECT id, message_id, time, raw_json FROM messages WHERE scene='private' AND peer_id=2633083674 ORDER BY time DESC LIMIT 30").all();
console.log('\n与 2633083674 的私聊消息(最近30条):', rows.length, '条');
let forwards = [];
for (const r of rows) {
  try {
    const ev = JSON.parse(r.raw_json);
    const fwd = (ev.message ?? []).filter((s) => s.type === 'forward');
    if (fwd.length) forwards.push({ id: r.id, time: r.time, message_id: r.message_id, fwd });
  } catch {}
}
console.log('\n含合并转发的消息:', forwards.length, '条');
for (const f of forwards) console.log(JSON.stringify(f, null, 2).slice(0, 600));
db.close();
