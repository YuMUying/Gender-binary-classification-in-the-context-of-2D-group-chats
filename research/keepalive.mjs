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
 *   3. 低频自愈：判定断流后只重启一次 + 冷却 ≥6 小时（绝不频繁重启触发登录风控）
 *      且仅当"服务层活着但消息流停滞"时触发（服务层也挂了先告警，不轻举妄动）
 *
 * 账号参数：--account <uin> 选择监控目标
 *   - 2740088195: 活跃群 [826904606, 762673304]（274 号可访问的群）
 *   - 1394876195: 活跃群 [723216773, 826904606]（139 号的历史目标群）
 *   --account 缺省 = 2740088195（当前主账号）
 *
 * 用法: node research/keepalive.mjs --account 2740088195   （常驻后台）
 *       node research/keepalive.mjs --account 1394876195 --no-restart
 */
import { execSync } from 'node:child_process';
import { appendFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { DatabaseSync } from 'node:sqlite';

const ROOT = path.resolve(import.meta.dirname, '..');

// ---------- 消息保活配置（每小时发一条到保活群，打断 MSF 空闲计时） ----------
const MSG_KEEPALIVE_GROUP = 1105502844;   // 自己人小群（保活测试群）
const MSG_KEEPALIVE_INTERVAL = 60 * 60 * 1000;  // 每小时一次
const MSG_KEEPALIVE_ENABLED = true;

// 水群语料池（多样化，避免固定文本被识别为机器人）
const CHAT_POOL = [
  '今天天气不错啊',
  '刚看到个有意思的，大家有空看看',
  '摸鱼中，有人一起水吗',
  '最近在折腾点小东西，还挺有意思',
  '这个点了还有人吗',
  '周末打算干点啥',
  '刚吃完饭，瘫着不想动',
  '有没有人打游戏啊',
  '今晚月色真美（划掉）',
  '冒个泡，证明我还活着',
  '日常打卡，滴——',
  '刚处理完一堆事，歇会儿',
  '看到个段子笑死我了',
  '有人知道那个新出的东西吗',
  '摸鱼使我快乐',
];

// ---------- 账号 → 配置映射 ----------
const ACCOUNTS = {
  '2740088195': {
    activeGroups: [826904606, 762673304],   // 274 号在的群（消息流新鲜度用）
    restartScript: 'restart-274.ps1',
    onebotPort: 3000,
    label: '274(雲、)',
  },
  '1394876195': {
    activeGroups: [723216773, 826904606],   // 139 号历史目标群
    restartScript: 'restart-139.ps1',
    onebotPort: 3000,
    label: '139(❤️杂鱼)',
  },
};

function parseArgs() {
  const args = process.argv.slice(2);
  const out = { account: '2740088195', noRestart: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--account' && args[i + 1]) out.account = args[i + 1];
    if (args[i] === '--no-restart') out.noRestart = true;
  }
  return out;
}

const ARGS = parseArgs();
const ACCT = ACCOUNTS[ARGS.account];
if (!ACCT) {
  console.error(`未知账号 ${ARGS.account}，可用: ${Object.keys(ACCOUNTS).join(', ')}`);
  process.exit(1);
}

const LOG = path.join(ROOT, 'research', `keepalive-${ARGS.account}.log`);
const DB_PATH = path.join(ROOT, 'data', 'qqchat.db');
const ACTIVITY_INTERVAL = 5 * 60 * 1000; // 网络活性触发间隔（5 分钟）
const STALL_MIN = 15;                    // 群消息停滞判定阈值（分钟）
const RESTART_COOLDOWN = 6 * 60 * 60 * 1000; // 重启冷却 6 小时
const DB_STALL_WARN_SEC = 30 * 60;       // DB 无任何写入超过 30 分钟也告警（账号离线信号）

function log(msg) {
  const line = `[${new Date().toLocaleString('zh-CN', { hour12: false })}][${ACCT.label}] ${msg}`;
  console.log(line);
  try { appendFileSync(LOG, line + '\n', 'utf8'); } catch {}
}

function onebotOk(port) {
  return fetch(`http://127.0.0.1:${port}/get_login_info`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: '{}', signal: AbortSignal.timeout(8000),
  }).then(r => r.json()).then(j => j?.status === 'ok').catch(() => false);
}

// 触发 MSF 网络活性：对每个活跃群调用 mark_msg_as_read（内核已读模拟）
// 与 get_group_member_list 相比：这是"用户查看消息"的真实行为信号，
// 服务器看到的是正常拉取/已读流量而非只读 API 探测。
async function refreshActivity() {
  let ok = false;
  for (const gid of ACCT.activeGroups) {
    try {
      const r = await fetch(`http://127.0.0.1:${ACCT.onebotPort}/mark_msg_as_read`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: gid }),
        signal: AbortSignal.timeout(15000),
      });
      const j = await r.json();
      const success = j?.status === 'ok';
      log(`已读模拟: mark_msg_as_read 群${gid} → ${success ? 'OK' : j?.wording ?? j?.msg ?? '失败'}`);
      if (success) ok = true;
    } catch (e) {
      log(`已读模拟 群${gid} 失败: ${e.message}`);
    }
  }
  return ok;
}

// 消息流新鲜度：活跃群中最新消息时间
function dbFreshness() {
  try {
    const db = new DatabaseSync(DB_PATH, { readOnly: true });
    let newest = 0;
    for (const gid of ACCT.activeGroups) {
      const r = db.prepare(
        "SELECT MAX(time) mt FROM messages WHERE scene='group' AND peer_id=?"
      ).get(gid);
      if (r?.mt && r.mt > newest) newest = r.mt;
    }
    db.close();
    return newest;
  } catch {
    return 0;
  }
}

// 全库最新写入（collected_at 反映收集器是否在收）
function dbCollectFreshness() {
  try {
    const db = new DatabaseSync(DB_PATH, { readOnly: true });
    const r = db.prepare("SELECT MAX(collected_at) mt FROM messages").get();
    db.close();
    return r?.mt ?? 0;
  } catch {
    return 0;
  }
}

// 收集器入库速率：最近 1 小时新增消息数（进程健康度第二指标）
function collectRateLastHour() {
  try {
    const db = new DatabaseSync(DB_PATH, { readOnly: true });
    const since = Math.floor(Date.now() / 1000) - 3600;
    const r = db.prepare("SELECT COUNT(*) c FROM messages WHERE collected_at >= ?").get(since);
    db.close();
    return r?.c ?? 0;
  } catch {
    return -1;
  }
}

// 消息流状态字符串（供保活消息使用）
function msgFlowStatus() {
  const now = Date.now();
  const dbTs = dbFreshness();
  const ageMin = dbTs > 0 ? (now / 1000 - dbTs) / 60 : 999;
  if (ageMin > STALL_MIN) return `消息流已停 ${ageMin.toFixed(0)} 分钟`;
  if (dbTs > 0) return `消息流正常（${ageMin.toFixed(0)} 分钟前有消息）`;
  return '消息流状态未知';
}

// 发送保活消息：水群语料 + 进程情况（消息流 + 收集器入库速率）
async function sendKeepaliveMsg() {
  if (!MSG_KEEPALIVE_ENABLED) return false;
  try {
    const chat = CHAT_POOL[Math.floor(Math.random() * CHAT_POOL.length)];
    const rate = collectRateLastHour();
    const flow = msgFlowStatus();
    const rateStr = rate < 0 ? '未知' : `${rate} 条`;
    const msg = `${chat}\n（保活信号 | ${flow} | 近1h入库 ${rateStr} 条）`;
    const r = await fetch(`http://127.0.0.1:${ACCT.onebotPort}/send_group_msg`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: MSG_KEEPALIVE_GROUP, message: msg }),
      signal: AbortSignal.timeout(15000),
    });
    const j = await r.json();
    const ok = j?.status === 'ok';
    log(`保活消息 → 群${MSG_KEEPALIVE_GROUP}: ${ok ? 'OK' : '失败'}（${chat}）`);
    return ok;
  } catch (e) {
    log(`保活消息发送失败: ${e.message}`);
    return false;
  }
}

async function restartHeadless() {
  log('⚠ 消息流断流，执行一次无窗口重启...');
  try {
    execSync(
      `powershell -ExecutionPolicy Bypass -File "${path.join(ROOT, ACCT.restartScript)}"`,
      { timeout: 180000, stdio: 'inherit' }
    );
  } catch (e) { log(`重启脚本失败: ${e.message}`); }
  // 等待 OneBot 恢复（登录后才有），最多 3 分钟
  for (let i = 0; i < 30; i++) {
    await sleep(6000);
    if (await onebotOk(ACCT.onebotPort)) { log('✓ 重启后 OneBot 恢复'); return true; }
  }
  log('✗ 重启后 OneBot 未恢复（可能需扫码，见 WebUI）');
  return false;
}

async function main() {
  const restartMode = ARGS.noRestart ? '仅告警不重启' : `自动重启(冷却${RESTART_COOLDOWN / 3600000}h)`;
  log(`保活启动（账号 ${ARGS.account}，群 ${ACCT.activeGroups.join(',')}，活性5min / 断流${STALL_MIN}min / ${restartMode}）`);
  let lastActivity = 0;
  let lastRestart = 0;
  let lastMsgKeepalive = 0;
  let stallWarned = false;
  let collectStallWarned = false;

  while (true) {
    const now = Date.now();
    const svc = await onebotOk(ACCT.onebotPort);
    const dbTs = dbFreshness();
    const collectTs = dbCollectFreshness();

    // 0) 消息保活（每小时发一条到保活群，打断 MSF 空闲计时）
    if (MSG_KEEPALIVE_ENABLED && now - lastMsgKeepalive > MSG_KEEPALIVE_INTERVAL) {
      lastMsgKeepalive = now;
      await sendKeepaliveMsg();
    }

    // 1) 网络活性触发（每 5 分钟）
    if (now - lastActivity > ACTIVITY_INTERVAL) {
      lastActivity = now;
      if (svc) await refreshActivity();
    }

    // 2) 消息流新鲜度判定（活跃群停滞）
    const ageMin = dbTs > 0 ? (now / 1000 - dbTs) / 60 : 999;
    if (ageMin > STALL_MIN) {
      if (!stallWarned) {
        stallWarned = true;
        log(`⚠ 群消息停滞 ${ageMin.toFixed(0)} 分钟（服务${svc ? '活着' : '也挂'}）——疑似 MSF 断流`);
      }
    } else {
      if (stallWarned) { stallWarned = false; log(`✓ 消息流恢复（停滞后重新有消息）`); }
    }

    // 2b) 收集器写入新鲜度（collected_at 停滞 = 收集器可能挂了）
    const collectAgeSec = collectTs > 0 ? now / 1000 - collectTs : 999;
    if (collectAgeSec > DB_STALL_WARN_SEC) {
      if (!collectStallWarned) {
        collectStallWarned = true;
        log(`⚠ 收集器 ${(collectAgeSec / 60).toFixed(0)} 分钟未写入新消息——检查收集器进程`);
      }
    } else if (collectStallWarned) {
      collectStallWarned = false;
      log(`✓ 收集器写入恢复`);
    }

    // 3) 断流处理（自动重启独立于告警标志——修复：stallWarned 置位后重启分支被永久跳过）
    if (ageMin > STALL_MIN) {
      if (svc) {
        const msg = `消息流停滞 ${ageMin.toFixed(0)} 分钟（服务活着）——${ARGS.noRestart ? '仅告警' : '将尝试重启'}`;
        if (!stallWarned) { stallWarned = true; log(`⚠ ${msg}`); }
        if (!ARGS.noRestart && now - lastRestart > RESTART_COOLDOWN) {
          lastRestart = now;
          log(`→ 执行自动重启（距上次 ${((now - lastRestart) / 3600000).toFixed(1)}h）`);
          await restartHeadless();
        } else if (!ARGS.noRestart) {
          log(`  距上次重启 ${((now - lastRestart) / 3600000).toFixed(1)}h，冷却期内跳过`);
        }
      } else {
        const msg = `服务层也挂 + 消息流停滞——${ARGS.noRestart ? '仅告警' : '将尝试重启'}`;
        if (!stallWarned) { stallWarned = true; log(`⚠ ${msg}`); }
        if (!ARGS.noRestart && now - lastRestart > RESTART_COOLDOWN) {
          lastRestart = now;
          log(`→ 执行自动重启（服务层挂）`);
          await restartHeadless();
        }
      }
    } else if (stallWarned) {
      stallWarned = false;
      log(`✓ 消息流恢复（停滞后重新有消息）`);
    }

    await sleep(60000);
  }
}

main().catch((e) => { console.error('keepalive 崩溃:', e); process.exit(1); });
