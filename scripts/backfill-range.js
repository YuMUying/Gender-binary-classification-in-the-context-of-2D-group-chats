#!/usr/bin/env node
/**
 * backfill-range.js — 补收指定时间段的历史消息（独立进程，可后台运行）
 *
 * 用法:
 *   node scripts/backfill-range.js --scene group --peer 0 \
 *        --from 2026-08-20 --to 2026-08-25 \
 *        --db data/qqchat-274.db --http http://127.0.0.1:3000 \
 *        [--self 0] [--token xxx] [--delay 3000] [--max-pages 30000]
 *
 * 特性:
 *   - 锚点独立：不读写 sync_state，与主回填/调度器并发安全（WAL + INSERT OR IGNORE）
 *   - 断点友好：优先从库内 time<=to 的最新 seq 起翻，避免从头扫
 *   - 进度文件：data/range-job-<scene>-<peer>.json（pi_tasks 工具读取展示）
 *   - 停止条件：翻到 from 之前 / 锚点不再前移 / API"不存在"(内存库底部) / 安全页数上限
 */
import { DatabaseSync } from 'node:sqlite';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { saveMessage } from '../src/db.js';
import { cqToText } from '../src/utils.js';
import { shouldExclude } from '../src/filter.js';

// ---------- 参数 ----------
const argv = process.argv.slice(2);
const arg = (k, d = null) => {
  const i = argv.indexOf(`--${k}`);
  return i >= 0 ? argv[i + 1] : d;
};
const scene = arg('scene', 'group');
const peer = Number(arg('peer'));
const dbFile = arg('db');
const httpUrl = arg('http').replace(/\/+$/, '');
const httpToken = arg('token', '');
const selfId = Number(arg('self', 0)) || null;
const delayMs = Number(arg('delay', 3000));
const maxPages = Number(arg('max-pages', 30000));
const pageSize = Number(arg('page-size', 20));

// 日期 → epoch（Pi 本地时区）；--from/--to 支持 YYYY-MM-DD 或纯秒数
const dayStart = (s) => Math.floor(new Date(`${s}T00:00:00`).getTime() / 1000);
const dayEnd = (s) => Math.floor(new Date(`${s}T23:59:59`).getTime() / 1000);
const from = /^\d+$/.test(arg('from')) ? Number(arg('from')) : dayStart(arg('from'));
const to = /^\d+$/.test(arg('to')) ? Number(arg('to')) : dayEnd(arg('to'));
if (!peer || !dbFile || !httpUrl || !Number.isFinite(from) || !Number.isFinite(to)) {
  console.error('参数不完整: --scene --peer --from --to --db --http 必填');
  process.exit(2);
}

const progressFile = path.join(path.dirname(dbFile), `range-job-${scene}-${peer}.json`);
const progress = {
  scene, peer, from, to, pid: process.pid, running: true,
  pages: 0, inserted: 0, dups: 0, anchorSeq: null, oldestTime: null,
  startedAt: Date.now(), finishedAt: null, error: null,
  range: { from, to },
};
const saveProgress = () => {
  try { writeFileSync(progressFile, JSON.stringify(progress)); } catch { /* 尽力而为 */ }
};

// ---------- API ----------
async function fetchPage(anchor) {
  const api = scene === 'group' ? 'get_group_msg_history' : 'get_friend_msg_history';
  const body = scene === 'group'
    ? { group_id: peer, count: pageSize, reverse_order: true }
    : { user_id: peer, count: pageSize, reverse_order: true };
  if (anchor != null) body.message_seq = anchor;
  const res = await fetch(`${httpUrl}/${api}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(httpToken ? { Authorization: `Bearer ${httpToken}` } : {}),
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  });
  const json = await res.json();
  if (json.status !== 'ok') throw new Error(`API ${api} retcode=${json.retcode} ${json.wording ?? json.msg ?? ''}`);
  return json.data?.messages ?? [];
}

// ---------- 主循环 ----------
const db = new DatabaseSync(dbFile);
db.exec('PRAGMA busy_timeout = 15000;');

// 锚点: 库内 time<=to 的最新 seq（没有则从最新开始翻, 多翻的靠去重消化）
let anchor = null;
{
  const row = db.prepare(
    `SELECT message_seq FROM messages
     WHERE scene=? AND peer_id=? AND message_seq IS NOT NULL AND time<=?
     ORDER BY time DESC, message_seq DESC LIMIT 1`).get(scene, peer, to);
  anchor = row?.message_seq ?? null;
  progress.anchorSeq = anchor;
  saveProgress();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let done = false;
for (let page = 0; page < maxPages && !done; page++) {
  let msgs;
  try {
    msgs = await fetchPage(anchor);
  } catch (e) {
    if (/不存在|retcode=100|retcode=404/i.test(e.message) && anchor != null) {
      progress.error = '已翻到客户端内存库底部'; done = true; break;
    }
    progress.error = `拉取失败: ${e.message}`; done = true; break;
  }
  if (!msgs.length) { progress.error = '空页, 停止'; done = true; break; }

  progress.pages++;
  let pageOldestTime = Infinity;
  const nextAnchor = msgs[0]?.message_seq ?? msgs[0]?.seq ?? null;
  for (const m of msgs) {
    const t = m.time ?? Math.floor(Date.now() / 1000);
    if (t < pageOldestTime) pageOldestTime = t;
    const rec = {
      scene, peer_id: peer,
      message_id: m.message_id ?? null,
      message_seq: m.message_seq ?? m.seq ?? null,
      group_name: null,
      user_id: m.sender?.user_id ?? m.user_id ?? null,
      nickname: m.sender?.nickname ?? null,
      card: m.sender?.card ?? null,
      role: m.sender?.role ?? null,
      time: t, text: cqToText(m.message),
      raw_json: JSON.stringify(m), source: 'range-backfill',
      segments: m.message ?? [],
    };
    if (rec.user_id == null || !rec.text) continue;
    if (shouldExclude(rec, { selfId })) continue;
    if (saveMessage(db, rec) === 'inserted') progress.inserted++;
    else progress.dups++;
    if (t < from) { /* 该消息早于目标区间, 已顺手入库(去重无害), 页结束后停 */ }
  }

  progress.oldestTime = pageOldestTime === Infinity ? progress.oldestTime : pageOldestTime;
  progress.anchorSeq = nextAnchor;
  saveProgress();

  // 停止条件
  if (pageOldestTime !== Infinity && pageOldestTime < from) { done = true; break; }   // 已覆盖目标起点
  if (nextAnchor == null || nextAnchor === anchor) { progress.error = '锚点不再前移, 停止'; done = true; break; }
  anchor = nextAnchor;
  if (delayMs > 0) await sleep(delayMs);
}
if (!progress.error && progress.pages >= maxPages) progress.error = '达到页数上限';
progress.running = false;
progress.finishedAt = Date.now();
saveProgress();
console.log(`完成: 页=${progress.pages} 新增=${progress.inserted} 重复=${progress.dups} error=${progress.error ?? '无'}`);
