/**
 * gapfill_groups.mjs — 串行增量回补指定群（一次一个群，避免并发压爆 NapCat 内核）
 *
 * 用途：服务离线/断流期间积压的消息，用 gapFill 模式从最新翻到与库内重叠，
 *      把缺口补上。逐群串行执行，群间加冷却延迟。
 *
 * 用法:
 *   node research/gapfill_groups.mjs --groups 826904606,762673304
 *   node research/gapfill_groups.mjs --groups 826904606 --max-pages 1000 --delay-ms 1200 --gap-ms 20000
 *
 * 参数:
 *   --groups    逗号分隔的群号列表（必填）
 *   --max-pages 每群最大翻页数（默认 500，20条/页 ≈ 1万条/群）
 *   --delay-ms  页间延迟（默认 800ms，防限速）
 *   --gap-ms    群与群之间的冷却（默认 15000ms）
 *   --db        数据库路径（默认 data/qqchat.db）
 *   --live      同时开启 WS 实时监听（默认关闭——回补期间只拉历史，避免与实时事件竞争）
 */
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { backfillPeer } from '../src/backfill.js';
import { makeLogger } from '../src/utils.js';

const ROOT = path.resolve(import.meta.dirname, '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const out = { groups: [], maxPages: 500, delayMs: 800, gapMs: 15000, db: path.join(ROOT, 'data', 'qqchat.db'), live: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--groups' && args[i + 1]) out.groups = args[i + 1].split(',').map(Number).filter(Boolean);
    if (args[i] === '--max-pages' && args[i + 1]) out.maxPages = parseInt(args[i + 1], 10);
    if (args[i] === '--delay-ms' && args[i + 1]) out.delayMs = parseInt(args[i + 1], 10);
    if (args[i] === '--gap-ms' && args[i + 1]) out.gapMs = parseInt(args[i + 1], 10);
    if (args[i] === '--db' && args[i + 1]) out.db = args[i + 1];
    if (args[i] === '--live') out.live = true;
  }
  return out;
}

const ARGS = parseArgs();
if (!ARGS.groups.length) {
  console.error('用法: node research/gapfill_groups.mjs --groups 826904606,762673304 [--max-pages 500] [--delay-ms 800] [--gap-ms 15000]');
  process.exit(1);
}

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(ARGS.db);
const bot = new OneBotClient(config.onebot, log);

if (ARGS.live) {
  bot.connect();
} else {
  // 不回填时不连 WS，直接用 HTTP 拉历史
  bot.connect = () => {};
}

async function run() {
  log.info(`[gapfill] 串行回补开始，群: ${ARGS.groups.join(', ')}，maxPages=${ARGS.maxPages}，页延迟=${ARGS.delayMs}ms`);
  for (const g of ARGS.groups) {
    log.info(`[gapfill] === 开始群 ${g}（前群完成后才轮到它）===`);
    try {
      const r = await backfillPeer(db, bot, config.collect.backfill, {
        scene: 'group',
        peerId: g,
        gapFill: true,               // 从最新翻到重叠，补最近断档
        maxPages: ARGS.maxPages,
        log,
        onProgress: (p) => {
          if (p.pages % 25 === 0) log.info(`[gapfill] 群 ${g} 进度: 第 ${p.pages} 页，新增 ${p.inserted}，重复 ${p.dups}`);
        },
      });
      log.info(`[gapfill] 群 ${g} 完成: 翻页 ${r.pages}，新增 ${r.inserted}，重复 ${r.dups}，最新 seq=${r.newestSeq ?? '?'}`);
    } catch (e) {
      log.error(`[gapfill] 群 ${g} 失败: ${e.message}`);
    }
    if (ARGS.groups.indexOf(g) < ARGS.groups.length - 1) {
      log.info(`[gapfill] 群 ${g} 完成，冷却 ${ARGS.gapMs / 1000}s 后处理下一群...`);
      await sleep(ARGS.gapMs);
    }
  }
  log.info('[gapfill] 全部群回补完成');
  db.close();
  bot.close();
  process.exit(0);
}

run().catch((e) => { console.error('gapfill 崩溃:', e); process.exit(1); });
