/**
 * fetch-profile-genders.js — 全量拉取 QQ 资料性别入库（网络性别，弱信号）
 *
 * 用法：
 *   node scripts/fetch-profile-genders.js                    # 全量拉取（跳过已入库）
 *   node scripts/fetch-profile-genders.js --refresh          # 强制刷新全部
 *   node scripts/fetch-profile-genders.js --override 0:female --override 0:none
 *                                                             # 人工指定的网络性别（male|female|none）
 *
 * 说明：get_stranger_info 的资料性别是用户自报字段（可能娱乐性填写），
 *       仅作弱信号/交叉核对用，绝不作为训练标签。
 */
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { makeLogger, sleep } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);
const bot = new OneBotClient(config.onebot, log);

const args = process.argv.slice(2);
const has = (n) => args.includes(n);
function arg(n) { const i = args.indexOf(n); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }

const refresh = has('--refresh');
const timeoutMs = arg('--timeout-ms') ? Number(arg('--timeout-ms')) : 12000;
const delayMs = arg('--delay-ms') ? Number(arg('--delay-ms')) : 150;
const overrides = [];
for (const a of args) {
  const m = /^--override\s+(\d+):(male|female|none)$/.exec(a);
  if (m) overrides.push({ user_id: Number(m[1]), gender: m[2] });
}

db.exec(`CREATE TABLE IF NOT EXISTS profile_genders (
  user_id INTEGER PRIMARY KEY,
  network_gender TEXT NOT NULL,
  sex_raw TEXT,
  profile_nickname TEXT,
  source TEXT DEFAULT 'api',
  fetched_at INTEGER NOT NULL
)`);

function mapSex(raw) {
  const s = String(raw ?? '').toLowerCase();
  if (s === 'male' || s === '男') return 'male';
  if (s === 'female' || s === '女') return 'female';
  return 'none';
}

async function fetchAll() {
  const users = db.prepare(`
    SELECT user_id FROM user_profiles
    UNION
    SELECT DISTINCT user_id FROM messages
  `).all().map((r) => r.user_id);

  const done = refresh ? new Set() : new Set(db.prepare('SELECT user_id FROM profile_genders').all().map((r) => r.user_id));
  const todo = users.filter((u) => !done.has(u));
  log.info(`[profile] 待拉取 ${todo.length} 人（总数 ${users.length}，已入库 ${done.size}）`);

  let ok = 0, fail = 0, none = 0, male = 0, female = 0;
  const upsert = db.prepare(`
    INSERT INTO profile_genders (user_id, network_gender, sex_raw, profile_nickname, source, fetched_at)
    VALUES (?,?,?,?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
      network_gender=excluded.network_gender, sex_raw=excluded.sex_raw,
      profile_nickname=excluded.profile_nickname, source=excluded.source, fetched_at=excluded.fetched_at
  `);
  const t0 = Date.now();
  for (let i = 0; i < todo.length; i++) {
    const uid = todo[i];
    try {
      const d = await bot.callApi('get_stranger_info', { user_id: uid }, timeoutMs);
      const g = mapSex(d?.sex);
      upsert.run(uid, g, d?.sex ?? null, d?.nickname ?? null, 'api', Math.floor(Date.now() / 1000));
      if (g === 'male') male++; else if (g === 'female') female++; else none++;
      ok++;
    } catch (e) {
      fail++;
      log.warn(`[profile] ${uid} 拉取失败: ${e.message}`);
    }
    if ((i + 1) % 100 === 0) {
      log.info(`[profile] 进度 ${i + 1}/${todo.length}（ok=${ok} fail=${fail}）`);
    }
    await sleep(delayMs);
  }
  log.info(`[profile] 完成: ok=${ok} fail=${fail} | male=${male} female=${female} none=${none} | 耗时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

function applyOverrides() {
  const upsert = db.prepare(`
    INSERT INTO profile_genders (user_id, network_gender, sex_raw, profile_nickname, source, fetched_at)
    VALUES (?,?,?,?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
      network_gender=excluded.network_gender, sex_raw=excluded.sex_raw,
      profile_nickname=excluded.profile_nickname, source=excluded.source, fetched_at=excluded.fetched_at
  `);
  for (const o of overrides) {
    upsert.run(o.user_id, o.gender, null, null, 'manual', Math.floor(Date.now() / 1000));
    log.info(`[profile] 人工覆盖 ${o.user_id} → ${o.gender}`);
  }
}

await fetchAll();
if (overrides.length) applyOverrides();

const stats = db.prepare('SELECT network_gender, COUNT(*) c FROM profile_genders GROUP BY network_gender').all();
log.info('[profile] 入库统计: ' + stats.map((s) => `${s.network_gender}=${s.c}`).join(' '));
db.close();
