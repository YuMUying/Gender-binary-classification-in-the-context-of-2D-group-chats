/**
 * keepalive.mjs — QQ 消息流保活（网络活性触发 + 消息流新鲜度检测 + 低频自愈）
 *
 * 核心认知：NapCat 内部服务(3000/3001/6099/40653)活着 ≠ QQ↔腾讯 MSF 消息流活着。
 * 消息流断 = MSF 长连接空闲被 NAT/服务器切断 + 无UI环境 QQ 内核不主动重连。
 *
 * 策略：
 *   1. 活性触发：每 5 分钟调 get_group_member_list(no_cache=true) 强制向服务器刷新，
 *      让 MSF 发请求维持 NAT 会话（只读、不打扰、不风控）
 *   2. 断流检测：监控 DB 中活跃群的最新消息时间戳（消息流真活着 = 本地库持续进新消息）
 *      - 群3(723216773) 是活跃群，正常持续有消息
 *   3. 低频自愈：判定断流后只重启一次 + 冷却 ≥6 小时（绝不频繁重启触发登录风控）
 *      且仅当"服务层活着但消息流停滞"时触发（服务层也挂了先告警，不轻举妄动）
 *
 * 用法: node research/keepalive.mjs [--no-restart]  （常驻后台；--no-restart 只检测不重启）
 */
import { execSync } from 'node:child_process';
import { appendFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { DatabaseSync } from 'node:sqlite';

const ROOT = path.resolve(import.meta.dirname, '..');
const LOG = path.join(ROOT, 'research', 'keepalive.log');
const DB_PATH = path.join(ROOT, 'data', 'qqchat.db');
const ACTIVE_GROUP = 723216773;          // 活跃群（用于消息流新鲜度）
const ACTIVITY_INTERVAL = 5 * 60 * 1000; // 网络活性触发间隔（5 分钟）
const STALL_MIN = 15;                    // 群消息停滞判定阈值（分钟）

function log(msg) {
  const line = `[${new Date().toLocaleString('zh-CN', { hour12: false })}] ${msg}`;
  console.log(line);
  try { appendFileSync(LOG, line + '\n', 'utf8'); } catch {}
}

function onebotOk() {
  return fetch('http://127.0.0.1:3000/get_login_info', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: '{}', signal: AbortSignal.timeout(8000),
  }).then(r => r.json()).then(j => j?.status === 'ok').catch(() => false);
}

// 触发 MSF 网络活性：强制刷新群成员列表（走服务器）
async function refreshActivity() {
  try {
    const r = await fetch('http://127.0.0.1:3000/get_group_member_list', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: ACTIVE_GROUP, no_cache: true }),
      signal: AbortSignal.timeout(15000),
    });
    const j = await r.json();
    const n = Array.isArray(j?.data) ? j.data.length : 0;
    log(`活性触发: get_group_member_list(no_cache) → ${n} 成员（MSF 会话保持）`);
    return true;
  } catch (e) {
    log(`活性触发失败: ${e.message}`);
    return false;
  }
}

// 消息流新鲜度：DB 活跃群最新消息时间
function dbFreshness() {
  try {
    const db = new DatabaseSync(DB_PATH, { readOnly: true });
    const r = db.prepare(
      "SELECT MAX(time) mt FROM messages WHERE scene='group' AND peer_id=?"
    ).get(ACTIVE_GROUP);
    db.close();
    return r?.mt ?? 0;
  } catch {
    return 0;
  }
}

async function restartHeadless() {
  log('⚠ 消息流断流，执行一次无窗口重启...');
  try {
    execSync(
      `powershell -ExecutionPolicy Bypass -File "${path.join(ROOT, 'restart-headless.ps1')}"`,
      { timeout: 180000, stdio: 'inherit' }
    );
  } catch (e) { log(`重启脚本失败: ${e.message}`); }
  // 等待 OneBot 恢复（登录后才有），最多 3 分钟
  for (let i = 0; i < 30; i++) {
    await sleep(6000);
    if (await onebotOk()) { log('✓ 重启后 OneBot 恢复'); return true; }
  }
  log('✗ 重启后 OneBot 未恢复（可能需扫码，见 WebUI）');
  return false;
}

async function main() {
  log(`保活启动（活性间隔5min / 断流阈值${STALL_MIN}min / 仅告警不自动重启）`);
  let lastActivity = 0;
  let lastRestart = 0;
  let stallWarned = false;
  let lastDbTs = 0;

  while (true) {
    const now = Date.now();
    const svc = await onebotOk();
    const dbTs = dbFreshness();

    // 1) 网络活性触发（每 5 分钟）
    if (now - lastActivity > ACTIVITY_INTERVAL) {
      lastActivity = now;
      if (svc) await refreshActivity();
    }

    // 2) 消息流新鲜度判定
    const ageMin = dbTs > 0 ? (now / 1000 - dbTs) / 60 : 999;
    if (ageMin > STALL_MIN) {
      if (!stallWarned) {
        stallWarned = true;
        log(`⚠ 群 ${ACTIVE_GROUP} 消息停滞 ${ageMin.toFixed(0)} 分钟（服务${svc ? '活着' : '也挂'}）——疑似 MSF 断流`);
      }
    } else {
      if (stallWarned) { stallWarned = false; log(`✓ 消息流恢复（停滞后重新有消息）`); }
    }

    // 3) 断流处理：只告警 + 记录（不自动重启——o3HookMode=0 已修复假死根因，
    //    重启会导致重新登录触发风控，且治标不治本。真断流由人工介入）
    if (svc && ageMin > STALL_MIN && !stallWarned) {
      stallWarned = true;
      log(`⚠ 消息流停滞 ${ageMin.toFixed(0)} 分钟（服务活着）——仅告警，不自动重启（防风控），请人工检查`);
    }
    if (!svc && ageMin > STALL_MIN && !stallWarned) {
      stallWarned = true;
      log(`⚠ 服务层也挂 + 消息流停滞——仅告警，不自动重启，请人工检查`);
    }

    await sleep(60000);
  }
}

main().catch((e) => { console.error('keepalive 崩溃:', e); process.exit(1); });
