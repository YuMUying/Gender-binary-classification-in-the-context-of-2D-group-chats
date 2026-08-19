/**
 * bulk-collect.js — CLI：一次性大规模历史采集（支持指定群聊 / 个人聊天）
 *
 * 用法：
 *   node scripts/bulk-collect.js --group 123456789                        # 采集指定群
 *   node scripts/bulk-collect.js --friend 987654321                       # 采集与指定好友的个人聊天
 *   node scripts/bulk-collect.js --all                                    # 采集 config 里所有群和好友
 *   node scripts/bulk-collect.js --group 123456789 --max 50000            # 本会话最多采集 5 万条
 *   node scripts/bulk-collect.js --group 123456789 --until-seq 3000       # 采集到 seq 3000 为止
 *   node scripts/bulk-collect.js --group 123456789 --until-date 2024-01-01
 *   node scripts/bulk-collect.js --group 123456789 --no-media             # 只采文本，不下载媒体
 *
 * 可随时 Ctrl+C 中断，进度已持久化在 sync_state 表，重跑自动续传（message_id 去重）。
 */
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { backfillPeer } from '../src/backfill.js';
import { MediaDownloader } from '../src/media.js';
import { trackContext } from '../src/context.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);
const bot = new OneBotClient(config.onebot, log);
const media = new MediaDownloader(db, config, log);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const has = (name) => args.includes(name);

const all = has('--all');
const noMedia = has('--no-media');
const groupId = arg('--group') ? Number(arg('--group')) : null;
const friendId = arg('--friend') ? Number(arg('--friend')) : null;
const maxPerGroup = arg('--max') ? Number(arg('--max')) : undefined;
const untilSeq = arg('--until-seq') ? Number(arg('--until-seq')) : undefined;
const untilDate = arg('--until-date');   // YYYY-MM-DD：挖到该日期为止
const untilTime = untilDate ? Math.floor(new Date(untilDate).getTime() / 1000) : undefined;

const targets = [];
if (all) {
  for (const g of (config.collect.groups ?? [])) targets.push({ scene: 'group', peerId: g });
  for (const f of (config.collect.friends ?? [])) targets.push({ scene: 'private', peerId: f });
} else if (groupId != null) {
  targets.push({ scene: 'group', peerId: groupId });
} else if (friendId != null) {
  targets.push({ scene: 'private', peerId: friendId });
}
if (!targets.length) {
  console.error('用法: node scripts/bulk-collect.js --group <群号> | --friend <QQ号> | --all');
  console.error('可选: [--max N] [--until-seq S] [--until-date YYYY-MM-DD] [--no-media]');
  process.exit(1);
}

if (!noMedia && config.collect?.media?.enabled) media.requeuePending();   // --no-media 时不恢复媒体下载队列

const mediaEnabled = !noMedia && config.collect?.media?.enabled && config.collect?.media?.backfillDownload;

async function main() {
  let total = { pages: 0, inserted: 0, dups: 0 };
  for (const t of targets) {
    const kind = t.scene === 'private' ? '好友' : '群';
    log.info(`\n========== 开始采集${kind} ${t.peerId} (媒体下载: ${mediaEnabled ? '开' : '关'}) ==========`);
    const r = await backfillPeer(db, bot, config.collect.backfill, {
      scene: t.scene,
      peerId: t.peerId,
      maxPerGroup,
      untilSeq,
      untilTime,
      log,
      onInserted: (rec) => {
        if (mediaEnabled) media.enqueue(rec, rec.segments);
        if (rec.scene === 'group' && config.context?.enabled && config.context?.onBackfill !== false) {
          trackContext(db, config.context, rec, log);
        }
      },
      onProgress: (p) => {
        log.info(`  ${kind} ${t.peerId}: 翻页 ${p.pages} | 新增 ${p.inserted} | 重复 ${p.dups} | 当前最旧 seq=${p.oldestSeq ?? '?'}`);
      },
    });
    total.pages += r.pages; total.inserted += r.inserted; total.dups += r.dups;
    log.info(`========== ${kind} ${t.peerId} 完成: 新增 ${r.inserted} 条，重复 ${r.dups} 条 ==========`);
  }
  log.info(`\n全部完成: 翻页 ${total.pages}，新增 ${total.inserted}，重复 ${total.dups}`);
  // 等待媒体队列排空
  const deadline = Date.now() + 60 * 60 * 1000;
  while (media.queue.length && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1000));
  }
  log.info(`媒体下载队列剩余 ${media.queue.length} 个（可稍后重跑或由服务端重试）`);
  media.stop();
  db.close();
  process.exit(0);
}

main().catch((e) => {
  log.error(`采集中断: ${e.message}`);
  media.stop();
  db.close();
  process.exit(1);
});