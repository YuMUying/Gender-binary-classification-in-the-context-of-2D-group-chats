/**
 * remap-forward-user.js — 修正合并转发内层消息的用户身份（人工核对后使用）
 *
 * 场景：腾讯/NapCat 在解析转发时把发言人身份映射错误，
 *       人工核对后确认"某时间起的信封中，另一位用户"实为另一个人。
 *
 * 用法：
 *   node scripts/remap-forward-user.js \
 *     --since "2026-08-17T11:50:00+08:00" \
 *     --from-uid 1094950020 --to-uid 3541215132 --to-nickname 星辞
 *
 * 行为：解析该时间后所有转发信封的 content_raw，把 sender.user_id == from-uid
 *       的内层消息改为 to-uid / to-nickname（messages 行与 raw_json 同步更新，
 *       并修正 user_profiles 计数）。
 */
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const since = arg('--since') ? Math.floor(new Date(arg('--since')).getTime() / 1000) : null;
const minTime = arg('--min-time') ? Math.floor(new Date(arg('--min-time')).getTime() / 1000) : null;
const maxTime = arg('--max-time') ? Math.floor(new Date(arg('--max-time')).getTime() / 1000) : null;
const fromUid = arg('--from-uid') ? Number(arg('--from-uid')) : null;
const toUid = arg('--to-uid') ? Number(arg('--to-uid')) : null;
const toNickname = arg('--to-nickname') ?? null;
if (!since || !fromUid || !toUid) {
  console.error('用法: node scripts/remap-forward-user.js --since "2026-08-17T11:50:00+08:00" --from-uid 1094950020 --to-uid 3541215132 --to-nickname 星辞');
  console.error('可选: --min-time / --max-time "2026-07-01T00:00:00+08:00"（按内层消息时间过滤，防止误伤重叠批次的旧身份）');
  process.exit(1);
}

/** 递归收集 content 中 sender.user_id == fromUid 且时间在 [minTime,maxTime] 内的消息 id */
function collect(msgs, out) {
  for (const m of msgs ?? []) {
    const uid = m.sender?.user_id ?? m.user_id;
    const t = m.time ?? 0;
    if (uid === fromUid && (m.real_id ?? m.message_id) != null) {
      if ((minTime === null || t >= minTime) && (maxTime === null || t <= maxTime)) {
        out.add(String(m.real_id ?? m.message_id));
      }
    }
    for (const seg of m.message ?? []) {
      if (seg.type === 'forward' && Array.isArray(seg.data?.content)) {
        collect(seg.data.content, out);
      }
    }
  }
}

const envelopes = db.prepare('SELECT forward_id, envelope_time, content_raw FROM forwards WHERE envelope_time >= ?').all(since);
log.info(`[remap] 命中信封 ${envelopes.length} 个（>= ${new Date(since * 1000).toLocaleString('zh-CN')}）`);
const ids = new Set();
for (const e of envelopes) {
  try { collect(JSON.parse(e.content_raw).messages, ids); }
  catch (err) { log.warn(`[remap] 信封 ${e.forward_id} 解析失败: ${err.message}`); }
}
log.info(`[remap] 其中 sender==${fromUid} 的内层消息 ${ids.size} 条`);

if (!ids.size) { log.info('[remap] 无待修正消息'); db.close(); process.exit(0); }

const ph = ids.size <= 500 ? ids.size : 0;
if (ph === 0) {
  // 分批处理（SQLite 参数上限 999）
  const idArr = [...ids];
  for (let i = 0; i < idArr.length; i += 500) {
    const chunk = idArr.slice(i, i + 500);
    remapChunk(chunk);
  }
} else {
  remapChunk([...ids]);
}

function remapChunk(chunk) {
  const placeholders = chunk.map(() => '?').join(',');
  // 1) messages 表：user_id / nickname
  const rows = db.prepare(`SELECT id, raw_json FROM messages WHERE user_id=? AND message_id IN (${placeholders})`).all(fromUid, ...chunk);
  const upd = db.prepare('UPDATE messages SET user_id=?, nickname=? WHERE id=?');
  const updRaw = db.prepare('UPDATE messages SET raw_json=? WHERE id=?');
  for (const r of rows) {
    upd.run(toUid, toNickname, r.id);
    if (r.raw_json) {
      try {
        const j = JSON.parse(r.raw_json);
        if (j.sender) { j.sender.user_id = toUid; if (toNickname) j.sender.nickname = toNickname; }
        if (j.user_id === fromUid) j.user_id = toUid;
        updRaw.run(JSON.stringify(j), r.id);
      } catch { /* 保留原样 */ }
    }
  }
  log.info(`[remap] 更新 ${rows.length} 行消息`);
}

// 2) 修正 user_profiles 计数
db.prepare(`
  INSERT INTO user_profiles (user_id, nickname, first_seen, last_seen, message_count, updated_at)
  SELECT user_id, MAX(nickname), MIN(time), MAX(time), COUNT(*), ?
  FROM messages WHERE user_id IN (?,?) GROUP BY user_id
  ON CONFLICT(user_id) DO UPDATE SET
    nickname=excluded.nickname, first_seen=excluded.first_seen,
    last_seen=excluded.last_seen, message_count=excluded.message_count, updated_at=excluded.updated_at
`).run(Math.floor(Date.now() / 1000), fromUid, toUid);

log.info('[remap] user_profiles 已重算');
db.close();
