/**
 * export-foi-dataset.js — 导出 FOI（男娘/小众性取向）二分类数据集
 *
 * 标签规则（与性别分类不同的维度）：
 *   foi = 1  → speaker_labels.orientation ∈ {男娘+双, 双, 同性恋} 且 gender=male
 *   foi = 0  → speaker_labels.gender=male 且无 orientation（正常男性）
 *
 * 用法：
 *   node scripts/export-foi-dataset.js --out data/foi-train.jsonl --out-val data/foi-val.jsonl
 *       [--min-per-user 50] [--max-per-user 2000] [--val-ratio 0.2] [--seed 42]
 *       [--split-by-user] [--use-context 0] [--no-nickname]
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { loadConfig, ROOT } from '../src/config.js';
import { openDb } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const has = (name) => args.includes(name);

const out = arg('--out') ?? 'data/foi-train.jsonl';
const outVal = arg('--out-val') ?? 'data/foi-val.jsonl';
const minPerUser = arg('--min-per-user') ? Number(arg('--min-per-user')) : 50;
const maxPerUser = arg('--max-per-user') ? Number(arg('--max-per-user')) : 2000;
const valRatio = arg('--val-ratio') ? Number(arg('--val-ratio')) : 0.2;
const seed = arg('--seed') ? Number(arg('--seed')) : 42;
const splitByUser = has('--split-by-user');
const noNickname = has('--no-nickname');

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

// 阳性用户：orientation 且有 male 性别
const posUsers = new Map();   // user_id -> {orientation, confidence}
for (const r of db.prepare(`
  SELECT user_id, orientation, label_confidence FROM speaker_labels
  WHERE orientation IS NOT NULL AND orientation != '' AND gender='male'`).all()) {
  posUsers.set(r.user_id, { orientation: r.orientation, confidence: r.label_confidence ?? 'low' });
}
// 阴性用户：male 且无 orientation
const negUsers = new Set();
for (const r of db.prepare(`
  SELECT user_id FROM speaker_labels WHERE gender='male'`).all()) {
  if (!posUsers.has(r.user_id)) negUsers.add(r.user_id);
}
log.info(`[foi] 阳性用户 ${posUsers.size} 人（男娘/双/同性恋），阴性 ${negUsers.size} 人（正常男）`);

function rowsForUser(userId, cap = Infinity) {
  const rows = db.prepare(`
    SELECT user_id, peer_id AS group_id, time, text, CAST(message_id AS TEXT) AS message_id, nickname, card
    FROM messages m WHERE user_id=? AND scene IN ('group','private')
      AND LENGTH(text) >= 2 ORDER BY time ASC`).all(userId);
  return rows.slice(0, cap);
}

function buildRow(r, label, extra = {}) {
  const row = { text: r.text, user_id: r.user_id, group_id: r.group_id, time: r.time, label };
  if (!noNickname) {
    if (r.nickname != null) row.nickname = r.nickname;
    if (r.card != null && r.card !== '') row.card = r.card;
  }
  Object.assign(row, extra);
  return row;
}

// 用户信息（含消息数）
const allUsers = [];
for (const [uid, info] of posUsers) {
  const n = db.prepare(`SELECT COUNT(*) c FROM messages WHERE user_id=? AND scene IN ('group','private') AND LENGTH(text)>=2`).get(uid).c;
  if (n >= minPerUser) allUsers.push({ user_id: uid, label: 'foi', confidence: info.confidence, n });
}
for (const uid of negUsers) {
  const n = db.prepare(`SELECT COUNT(*) c FROM messages WHERE user_id=? AND scene IN ('group','private') AND LENGTH(text)>=2`).get(uid).c;
  if (n >= minPerUser) allUsers.push({ user_id: uid, label: 'normal', n });
}
log.info(`[foi] 满足 min-per-user=${minPerUser} 的用户: 阳性 ${allUsers.filter(u=>u.label==='foi').length} / 阴性 ${allUsers.filter(u=>u.label==='normal').length}`);

// 按用户分层划分（阳性每折至少留 1 人训练）
const rng = mulberry32(seed);
let trainUsers = [], valUsers = [];
if (splitByUser) {
  for (const lab of ['foi', 'normal']) {
    const pool = shuffle(allUsers.filter((u) => u.label === lab), rng);
    const n = Math.min(pool.length - 1, Math.max(1, Math.round(pool.length * Math.min(Math.max(valRatio, 0), 0.4))));
    valUsers.push(...pool.slice(0, n));
    trainUsers.push(...pool.slice(n));
  }
} else {
  trainUsers = allUsers;
}

const trainLines = [], valLines = [];
let tCount = 0, vCount = 0;
for (const u of trainUsers) {
  const rows = rowsForUser(u.user_id, maxPerUser);
  const extra = u.label === 'foi' ? { label_confidence: u.confidence } : {};
  for (const r of rows) { trainLines.push(JSON.stringify(buildRow(r, u.label, extra))); tCount++; }
}
for (const u of valUsers) {
  const rows = rowsForUser(u.user_id, maxPerUser);
  const extra = u.label === 'foi' ? { label_confidence: u.confidence } : {};
  for (const r of rows) { valLines.push(JSON.stringify(buildRow(r, u.label, extra))); vCount++; }
}

mkdirSync(path.dirname(out), { recursive: true });
writeFileSync(out, trainLines.join('\n') + (trainLines.length ? '\n' : ''), 'utf8');
log.info(`导出 train: ${out}（${tCount} 行, 用户 ${trainUsers.length}）`);
if (valLines.length) {
  mkdirSync(path.dirname(outVal), { recursive: true });
  writeFileSync(outVal, valLines.join('\n') + (valLines.length ? '\n' : ''), 'utf8');
  log.info(`导出 val: ${outVal}（${vCount} 行, 用户 ${valUsers.length}）`);
}
db.close();
process.exit(0);
