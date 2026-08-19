// 同步辅助：WAL 检查点 + 复制数据文件
import { execSync } from 'node:child_process';
import { DatabaseSync } from 'node:sqlite';
import { copyFileSync, rmSync, existsSync } from 'node:fs';

const MAIN = 'G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset';
const PORT = 'G:/Deepseek/DeepSeek_WorkPlace/qq-gender-portable';

// 1) 主库 WAL 检查点
const db = new DatabaseSync(MAIN + '/data/qqchat.db');
console.log('checkpoint:', JSON.stringify(db.prepare('PRAGMA wal_checkpoint(TRUNCATE)').get()));
db.close();

// 2) 复制数据库
copyFileSync(MAIN + '/data/qqchat.db', PORT + '/data/qqchat.db');
for (const suf of ['-wal', '-shm']) {
  if (existsSync(PORT + '/data/qqchat.db' + suf)) rmSync(PORT + '/data/qqchat.db' + suf);
}

// 3) 复制导出文件
for (const f of ['train.jsonl', 'val.jsonl', 'test-weak.jsonl', 'synth-female.jsonl', 'train.jsonl.meta.json']) {
  copyFileSync(MAIN + '/data/' + f, PORT + '/data/' + f);
}
for (const f of ['_tmp-train.jsonl', '_tmp-train.jsonl.meta.json']) {
  if (existsSync(PORT + '/data/' + f)) rmSync(PORT + '/data/' + f);
}

// 4) 验证
const p = new DatabaseSync(PORT + '/data/qqchat.db', { readOnly: true });
console.log('便携库消息数:', p.prepare('SELECT COUNT(*) c FROM messages').get().c);
console.log('标签数:', p.prepare('SELECT COUNT(*) c FROM speaker_labels').get().c);
console.log('forward 消息:', p.prepare("SELECT COUNT(*) c FROM messages WHERE source='forward'").get().c);
console.log('forwards 信封:', p.prepare('SELECT COUNT(*) c FROM forwards').get().c);
p.close();
