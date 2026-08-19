/**
 * fetch-private.js — 拉取与某用户的私聊完整历史并入库
 *
 * 用法: node scripts/fetch-private.js --user 1965417382 [--max-pages 100]
 * 入库: scene='private', source='live'，按 message_id 去重（saveMessage）
 */
import { loadConfig } from '../src/config.js';
import { openDb, saveMessage } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { cqToText, makeLogger, sleep } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);
const bot = new OneBotClient(config.onebot, log);

const args = process.argv.slice(2);
const arg = (n) => { const i = args.indexOf(n); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; };
const userId = Number(arg('--user') ?? 0);
const maxPages = Number(arg('--max-pages') ?? 200);
if (!userId) { console.error('用法: node scripts/fetch-private.js --user <QQ号>'); process.exit(1); }

const PAGE = 20;
let saved = 0;

async function saveMsg(m) {
  const text = cqToText(m.message);
  const rec = {
    scene: 'private',
    peer_id: m.user_id ?? userId,
    message_id: m.real_id ?? m.message_id ?? null,
    message_seq: m.real_seq != null ? Number(m.real_seq) : (m.message_seq ?? null),
    user_id: m.sender?.user_id ?? m.user_id,
    nickname: m.sender?.nickname ?? null,
    card: null,
    time: m.time ?? Math.floor(Date.now() / 1000),
    text,
    raw_json: JSON.stringify(m),
    source: 'live',
  };
  if (rec.user_id == null || !text) return;
  if (saveMessage(db, rec) === 'inserted') saved++;
}

async function main() {
  log.info(`[private] 拉取与 QQ ${userId} 的完整私聊历史...`);
  let anchor = null;
  let pages = 0;
  let earliest = 0;
  while (pages < maxPages) {
    const body = { user_id: userId, count: PAGE };
    if (anchor !== null) body.message_seq = anchor;
    let msgs = [];
    try {
      const data = await bot.callApi('get_friend_msg_history', body, 90000);
      msgs = data.messages ?? [];
    } catch (e) {
      log.warn(`[private] 第 ${pages + 1} 页失败: ${e.message}`);
      break;
    }
    if (!msgs.length) break;
    pages++;
    for (const m of msgs) await saveMsg(m);
    const seqs = msgs.map((m) => m.message_seq ?? m.real_seq).filter((s) => s != null);
    if (!seqs.length) break;
    const next = Math.min(...seqs);
    if (next === anchor) break;
    if (next <= earliest) break;
    earliest = next;
    anchor = next;
    log.info(`[private] 第 ${pages} 页: 最新seq=${Math.max(...seqs)} 回溯到 ${next} (累计入库 ${saved})`);
    await sleep(800);
  }
  log.info(`[private] 完成：翻页 ${pages}，入库消息 ${saved} 条`);
  db.close();
  process.exit(0);
}

main().catch((e) => { log.error(`出错: ${e.message}`); db.close(); process.exit(1); });
