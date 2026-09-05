/**
 * export-context.js — CLI：从数据库导出指定 QQ 号的发言及其上下文（历史回溯）
 *
 * 用法：
 *   node scripts/export-context.js --user 123456789                       # 该用户全部发言+上下文 → JSONL
 *   node scripts/export-context.js --user 123456789 --window 5 --limit 200
 *   node scripts/export-context.js --user 123456789 --since 2026-01-01
 *   node scripts/export-context.js --user 123456789 --format readable --out data/ctx-readable.txt
 *   node scripts/export-context.js --user 123456789 --group 888888888     # 只看某群
 *
 * 输出（jsonl 每行）：{"time":..., "group_id":..., "center":{...}, "context":[{...前N+自己+后N...}]}
 * readable 格式适合人工标注性别时通读。
 */
import { writeFileSync, appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { loadConfig } from '../src/config.js';
import { openDb, getContext } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const has = (name) => args.includes(name);

const userId = arg('--user') ? Number(arg('--user')) : null;
if (!userId) {
  console.error('用法: node scripts/export-context.js --user <QQ号> [--window N] [--group G] [--limit N] [--since YYYY-MM-DD] [--format jsonl|readable] [--out FILE]');
  process.exit(1);
}

const windowSize = arg('--window') ? Number(arg('--window')) : 5;
const groupId = arg('--group') ? Number(arg('--group')) : null;
const limit = arg('--limit') ? Number(arg('--limit')) : Infinity;
const since = arg('--since') ? Math.floor(new Date(arg('--since')).getTime() / 1000) : null;
const format = arg('--format') ?? 'jsonl';
const out = arg('--out') ?? `data/context-export-${userId}.${format === 'readable' ? 'txt' : 'jsonl'}`;

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

async function main() {
  let sql = `SELECT message_id, peer_id, time FROM messages WHERE user_id=? AND scene='group'`;
  const params = [userId];
  if (groupId != null) { sql += ' AND peer_id=?'; params.push(groupId); }
  if (since != null) { sql += ' AND time>=?'; params.push(since); }
  sql += ' ORDER BY id ASC';
  if (Number.isFinite(limit)) { sql += ' LIMIT ?'; params.push(limit); }

  const centers = db.prepare(sql).all(...params);
  log.info(`找到 ${centers.length} 条中心消息，逐条提取上下文...`);

  mkdirSync(path.dirname(out), { recursive: true });
  let written = 0;

  for (const c of centers) {
    const ctx = getContext(db, c.peer_id, c.message_id, windowSize);
    if (!ctx) continue;

    if (format === 'readable') {
      appendFileSync(out, `\n=== ${fmtTime(ctx.center.time)} 群${c.peer_id} | 中心: ${ctx.center.nickname}(${ctx.center.user_id}) ===\n`, 'utf8');
      for (const m of [...ctx.before, ctx.center, ...ctx.after]) {
        const tag = m.message_id === ctx.center.message_id ? ' >>>' : '    ';
        const nameStr = `${m.nickname ?? '?'}${m.card && m.card !== m.nickname ? `·${m.card}` : ''}`;
        appendFileSync(out, `${tag} [${fmtTime(m.time)}] ${nameStr}(${m.user_id}): ${m.text}\n`, 'utf8');
      }
    } else {
      appendFileSync(out, JSON.stringify({
        time: ctx.center.time,
        group_id: c.peer_id,
        center: {
          message_id: ctx.center.message_id, user_id: ctx.center.user_id,
          nickname: ctx.center.nickname, card: ctx.center.card, text: ctx.center.text,
        },
        context: [...ctx.before, ctx.center, ...ctx.after].map((m) => ({
          user_id: m.user_id, nickname: m.nickname, card: m.card, text: m.text, time: m.time,
          is_center: m.message_id === ctx.center.message_id,
        })),
      }) + '\n', 'utf8');
    }
    written++;
  }
  log.info(`导出完成: ${out}（${written} 条中心消息）`);
  db.close();
  process.exit(0);
}

main().catch((e) => { log.error(`导出失败: ${e.message}`); db.close(); process.exit(1); });
