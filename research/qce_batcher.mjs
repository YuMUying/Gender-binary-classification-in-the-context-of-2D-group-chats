/**
 * qce_batcher.mjs — 小批量串行导出（稳定性优先）：目标每批 ~4000 条
 *
 * 流程：export → waitTask → 归档 → 导入 → 收割 → 暂停(≥3min) → 下一批
 *
 * 用法:
 *   node research/qce_batcher.mjs --group 826904606 --max-batches 3 --pause-ms 180000
 *   [--mode missing]        缺失区（DB 最早消息之前），自适应窗口，默认
 *   [--mode known]          已知区（DB 时间戳每 4000 条精确切窗）
 *   [--batch-size 4000]     目标每批条数
 *   [--window-ms 172800000] 缺失区初始窗口（默认 48h）
 *   [--start-back 0]        缺失区断点：往回第 N 个窗口开始
 *   [--dry-run]             只打印计划不执行
 */
import { execSync } from 'node:child_process';
import { mkdirSync, existsSync, copyFileSync, unlinkSync, appendFileSync } from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const TOKEN = '4Trx5OWltB1jKsdlYb6swnbelBExC71DAA34RBqL';
const BASE = 'http://127.0.0.1:40653';
const ROOT = path.resolve(import.meta.dirname, '..');
const ARCHIVE = path.join(ROOT, 'research', 'qce_batches');
const EXPORTS_DIR = process.env['USERPROFILE'] + '\\.qq-chat-exporter\\exports';
const LOG_FILE = path.join(ROOT, 'research', 'qce_batch_log.jsonl');

const args = process.argv.slice(2);
const arg = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const has = (n) => args.includes(n);
const GROUP = Number(arg('--group') ?? 826904606);
const MAX_BATCHES = Number(arg('--max-batches') ?? 3);
const PAUSE_MS = Number(arg('--pause-ms') ?? 180000); // 默认 3 分钟
const BATCH_SIZE = Number(arg('--batch-size') ?? 4000);
const MODE = arg('--mode') ?? 'missing'; // missing | known
const START_BACK = Number(arg('--start-back') ?? 0);
const INIT_WINDOW_MS = Number(arg('--window-ms') ?? 48 * 3600 * 1000);
const DRY_RUN = has('--dry-run');

mkdirSync(ARCHIVE, { recursive: true });

async function api(pathname, body, timeoutMs = 300000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(BASE + pathname, {
      method: body ? 'POST' : 'GET',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${TOKEN}` },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctl.signal,
    });
    const j = await r.json();
    if (!j.success) throw new Error(JSON.stringify(j.error ?? j));
    return j.data;
  } finally { clearTimeout(t); }
}

function dbTimes() {
  const py = path.join(ROOT, 'research', 'get_group_times.py');
  const out = execSync(`python ${py} ${GROUP}`, { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }).trim();
  return out.split(' ').filter(Boolean).map(Number);
}

function planWindows() {
  const times = dbTimes();
  if (!times.length) throw new Error('DB 无该群消息时间戳');
  const earliest = times[0];
  const wins = [];
  if (MODE === 'known') {
    for (let i = 0; i < times.length; i += BATCH_SIZE) {
      const chunk = times.slice(i, i + BATCH_SIZE);
      wins.push({ start: chunk[0] * 1000 - 2000, end: chunk[chunk.length - 1] * 1000 + 2000, label: `known_${i / BATCH_SIZE}` });
    }
  } else {
    // 缺失区：从 DB 最早消息往前推，自适应窗口宽度（目标 ~BATCH_SIZE 条）
    let winMs = Math.max(INIT_WINDOW_MS, 3600 * 1000);
    let end = earliest * 1000;
    for (let back = START_BACK; back < START_BACK + MAX_BATCHES * 2; back++) {
      const start = end - winMs;
      if (start < 1700000000000) break; // 2023-11 之前不再回退
      wins.push({ start, end, label: `missing_${back}`, adaptive: true });
      end = start;
      // 自适应窗口会被运行时调整，这里用保守中值预规划
      winMs = Math.min(Math.max(winMs, 6 * 3600 * 1000), 14 * 24 * 3600 * 1000);
    }
  }
  return { wins, earliest };
}

async function waitTask(taskId, maxWaitMs = 30 * 60 * 1000) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxWaitMs) {
    const d = await api(`/api/tasks/${taskId}`, null, 30000);
    if (d.status === 'completed') return { ok: true, d };
    if (d.status === 'failed') return { ok: false, d };
    await sleep(10000);
  }
  try { await api(`/api/tasks/${taskId}/cancel`, {}, 15000); } catch {}
  return { ok: false, d: { status: 'timeout', id: taskId } };
}

function harvest() {
  try {
    const out = execSync(`python ${path.join(ROOT, 'research', 'harvest_big.py')}`, { encoding: 'utf8', timeout: 600000, cwd: ROOT });
    const m = out.match(/命中并复制: (\d+)/);
    return m ? Number(m[1]) : -1;
  } catch { return -1; }
}

function importJson(file) {
  try {
    const out = execSync(`python ${path.join(ROOT, 'research', 'import_qce.py')} "${file}" --peer ${GROUP}`, { encoding: 'utf8', timeout: 600000, cwd: ROOT });
    const m = out.match(/新增 (\d+) 条/);
    return m ? Number(m[1]) : -1;
  } catch { return -1; }
}

function log(entry) {
  appendFileSync(LOG_FILE, JSON.stringify(entry) + '\n', 'utf8');
}

const peer = { chatType: 2, peerUid: String(GROUP) };

async function main() {
  const { wins, earliest } = planWindows();
  console.log(`[batcher] 群 ${GROUP} | 模式 ${MODE} | 目标 ${BATCH_SIZE} 条/批 | 最多 ${MAX_BATCHES} 批 | 批间暂停 ${(PAUSE_MS / 1000 / 60).toFixed(1)}min`);
  console.log(`[batcher] DB 最早消息: ${new Date(earliest * 1000).toISOString()} | 计划窗口: ${wins.length}`);
  for (const w of wins.slice(0, MAX_BATCHES)) {
    console.log(`  ${w.label}: ${new Date(w.start).toISOString()} ~ ${new Date(w.end).toISOString()} (${((w.end - w.start) / 3600000).toFixed(1)}h)`);
  }
  if (DRY_RUN) { console.log('[dry-run] 停止'); return; }

  let done = 0, okBatches = 0, failBatches = 0;
  let winMs = Math.max(INIT_WINDOW_MS, 3600 * 1000);
  for (let wi = 0; wi < wins.length && done < MAX_BATCHES; wi++) {
    const w = wins[wi];
    // 缺失区自适应窗口：用上一批实际条数调整
    if (w.adaptive) {
      w.end = Math.min(w.end, (wins[wi - 1]?.start ?? earliest * 1000));
      w.start = w.end - winMs;
    }
    console.log(`\n[批 ${done + 1}/${MAX_BATCHES}] ${w.label}: ${new Date(w.start).toISOString()} ~ ${new Date(w.end).toISOString()} (窗口 ${(winMs / 3600000).toFixed(1)}h)`);
    const entry = { ts: new Date().toISOString(), label: w.label, start: w.start, end: w.end };
    try {
      const t = await api('/api/messages/export', { peer, filter: { startTime: w.start, endTime: w.end }, options: {} }, 30000);
      entry.taskId = t.taskId;
      console.log(`  → 任务 ${t.taskId} 已创建 (${t.fileName})`);
      const res = await waitTask(t.taskId);
      if (res.ok) {
        const d = res.d;
        const rs = d.resourceSummary ?? {};
        const count = d.messageCount ?? 0;
        console.log(`  ✓ 完成: ${count} 条, 资源 尝试${rs.attempted ?? '?'} 下载${rs.downloaded ?? '?'} 失败${rs.failed ?? '?'}`);
        entry.count = count; entry.resourceSummary = rs;
        // 自适应：消息过多→缩小窗口，过少→放大
        if (w.adaptive) {
          if (count > BATCH_SIZE * 1.5) winMs = Math.max(Math.floor(winMs / 2), 1800000);
          else if (count > 0 && count < BATCH_SIZE * 0.5) winMs = Math.min(Math.floor(winMs * 1.5), 30 * 24 * 3600000);
        }
        // 归档：优先 d.filePath，否则 exports 目录 + fileName（跨盘用 copy+delete）
        let archived = null;
        const candidates = [d.filePath, path.join(EXPORTS_DIR, d.fileName || '')];
        for (const src of candidates) {
          if (src && existsSync(src)) {
            try {
              const dst = path.join(ARCHIVE, `${w.label}_${path.basename(src)}`);
              copyFileSync(src, dst);
              try { unlinkSync(src); } catch {}
              archived = dst;
              console.log(`  → 已归档: ${path.basename(dst)}`);
              break;
            } catch (e) { console.log(`  ⚠ 归档失败(${path.basename(src)}): ${e.message}`); }
          }
        }
        // 导入（补 DB 缺失历史）
        if (archived && count > 0) {
          const n = importJson(archived);
          entry.imported = n;
          console.log(`  → 已导入 DB: ${n >= 0 ? n + ' 条新增' : '导入失败'}`);
        }
        okBatches++;
      } else {
        console.log(`  ✗ 批次异常: ${res.d.status}`);
        entry.error = res.d.status;
        failBatches++;
      }
    } catch (e) {
      console.log(`  ✗ 启动失败: ${e.message}`);
      entry.error = e.message;
      failBatches++;
    }
    const h = harvest();
    entry.harvested = h;
    console.log(`  → Pic 收割: ${h >= 0 ? h + ' 新文件' : '执行失败'}`);
    log(entry);
    if (done + 1 < MAX_BATCHES) {
      console.log(`  → 暂停 ${(PAUSE_MS / 60000).toFixed(1)}min...`);
      await sleep(PAUSE_MS);
    }
    done++;
  }
  console.log(`\n[完成] 批次 ${done}（成功 ${okBatches} / 失败 ${failBatches}）| 日志: ${LOG_FILE}`);
}

main().catch((e) => { console.error('[batcher] 致命错误:', e.message); process.exit(1); });
