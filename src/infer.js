/**
 * infer.js — 性别推理响应（私聊 + 群聊）
 *
 * 【私聊规则】（原有，不改）
 *   触发：私聊来自 2633083674，文本匹配 /^推理\s+(\d+)/
 *   输出：性别/概率/置信度/是否已标注(含标签)/分歧指数；男或标注男附男娘指数
 *
 * 【群聊规则】（826904606，机器人被@才触发）
 *   命令1：推理 <QQ号> 或 推理 @某人
 *     - 目标必须在群内（get_group_member_info 校验），不在群 → 无数据
 *     - 输出：性别/概率/置信度/是否已标注(仅是否)/分歧指数；不含男娘指数
 *     - 模型判女 → 直接回复"模型判女"+概率+置信度
 *   命令2：xnn <QQ号> 或 xnn @某人
 *     - 输出男娘指数（无 Kalman 平滑版）
 *
 * 【并发控制】所有命令按消息到达时间戳入队，串行处理（时间戳顺序）。
 */
import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// ---- 配置 ----
const TRIGGER_QQ = 2633083674;          // 私聊触发器
const GROUP_IDS = [826904606, 1015142523];  // 群聊命令启用群（826904606 主群 + 1015142523 调试小群）
const RE_PRIVATE = /^推理\s*[:：]?\s*(\d{5,12})/;
const RE_GROUP_INFER = /^推理\s*[:：]?\s*(?:@?\s*(\d{5,12})|.+)/;   // 推理 <qq> 或 推理 @某人
const RE_XNN = /^xnn\s*[:：]?\s*(?:@?\s*(\d{5,12})|.+)/;            // xnn <qq> 或 xnn @某人
const SAMPLE_N = 100;
const INFER_TIMEOUT_MS = 30000;
const V10_WB_THRESHOLD = 0.73;

// ---- Python 推理子进程 ----
let py = null;
let pyQueue = [];
let pyReady = false;

/** 加载静态结果表（score-multi-v10.csv 缓存） */
let staticScores = null;
function loadStaticScores() {
  if (staticScores) return staticScores;
  const p = path.join(ROOT, 'outputs', 'score-multi-v10.csv');
  staticScores = new Map();
  if (!existsSync(p)) return staticScores;
  try {
    const lines = readFileSync(p, 'utf8').split('\n');
    const cols = lines[0].trim().split(',');
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].trim().split(',');
      if (vals.length < cols.length) continue;
      const row = {};
      cols.forEach((c, j) => (row[c.trim()] = vals[j]?.trim() ?? ''));
      if (row.user_id) staticScores.set(row.user_id, row);
    }
  } catch (e) { /* ignore */ }
  return staticScores;
}

/** 加载 FOI 混合指数表（无 Kalman 平滑版） */
let foiMap = null;
function loadFoiMap() {
  if (foiMap) return foiMap;
  const p = path.join(ROOT, 'outputs', 'foi_final.csv');
  foiMap = new Map();
  if (!existsSync(p)) return foiMap;
  try {
    const lines = readFileSync(p, 'utf8').split('\n');
    const cols = lines[0].trim().split(',');
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].trim().split(',');
      if (vals.length < cols.length) continue;
      const row = {};
      cols.forEach((c, j) => (row[c.trim()] = vals[j]?.trim() ?? ''));
      if (row.user_id) foiMap.set(row.user_id, row);
    }
  } catch (e) { /* ignore */ }
  return foiMap;
}

/** 常驻 Python 推理子进程（懒启动） */
function ensurePy() {
  if (py) return py;
  pyReady = false;
  const pyPath = path.join(ROOT, 'train', 'infer_one.py');
  py = spawn('python', [pyPath], {
    cwd: ROOT,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONPATH: path.join(ROOT, 'train') },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  let buf = '';
  py.stdout.on('data', (chunk) => {
    buf += chunk.toString();
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      if (obj.ready) {
        pyReady = true;
        continue;
      }
      const cb = pyQueue.shift();
      if (cb) cb(obj);
    }
  });
  py.stderr.on('data', () => { /* 静默 */ });
  py.on('exit', () => {
    py = null; pyReady = false;
    const pend = pyQueue; pyQueue = [];
    pend.forEach((cb) => cb({ error: 'infer process exited' }));
  });
  return py;
}

/** 向推理进程发请求，带超时（等待 ready 再写） */
function inferRequest(req, timeoutMs) {
  return new Promise((resolve) => {
    ensurePy();
    const cb = (obj) => { clearTimeout(timer); resolve(obj); };
    const timer = setTimeout(() => {
      const i = pyQueue.indexOf(cb);
      if (i >= 0) pyQueue.splice(i, 1);
      resolve({ timeout: true });
    }, timeoutMs);
    pyQueue.push(cb);
    const doWrite = () => {
      try {
        py.stdin.write(JSON.stringify(req) + '\n');
      } catch {
        clearTimeout(timer);
        const i = pyQueue.indexOf(cb);
        if (i >= 0) pyQueue.splice(i, 1);
        resolve({ error: 'write failed' });
      }
    };
    if (pyReady) {
      doWrite();
    } else {
      const t = setInterval(() => { if (pyReady) { clearInterval(t); doWrite(); } }, 100);
      setTimeout(() => clearInterval(t), 30000);
    }
  });
}

/** 从 DB 取用户最新入库 N 条消息 */
function latestMessages(db, userId, n) {
  return db.prepare(`
    SELECT text, nickname FROM messages
    WHERE user_id=? AND LENGTH(text) > 0
    ORDER BY collected_at DESC, id DESC LIMIT ?`).all(userId, n);
}

/** 是否已标注 */
function getLabel(db, userId) {
  return db.prepare('SELECT gender, label_confidence, orientation FROM speaker_labels WHERE user_id=?').get(userId) ?? null;
}

/** 置信度判定 */
function confidenceFor(p, n) {
  if (n < 20) return 'low-data（样本不足）';
  if (Math.abs(p - V10_WB_THRESHOLD) < 0.15) return 'borderline（临界）';
  return 'high';
}

/** 分歧指数（静态表） */
function loadDisagreement(userId) {
  const st = loadStaticScores().get(userId);
  return st?.disagreement ?? '未知';
}

/** 男娘指数（无 Kalman） */
function loadFoiValue(userId) {
  const foi = loadFoiMap().get(String(userId));
  const v = foi ? Number(foi.foi_index) : null;
  if (v == null || isNaN(v)) return null;
  return v;
}

/** 执行一次推理，返回 {p, nUsed, source} 或抛错/返回错误文本 */
async function runInference(targetId, db) {
  const msgs = latestMessages(db, targetId, SAMPLE_N);
  if (!msgs.length) return { noData: true };
  const req = {
    texts: msgs.map((m) => m.text),
    nicknames: msgs.map((m) => m.nickname ?? null),
  };
  const res = await inferRequest(req, INFER_TIMEOUT_MS);
  if (res && typeof res.p_female === 'number') {
    return { p: res.p_female, nUsed: res.n ?? msgs.length, source: `实时采样${res.n ?? msgs.length}条(${res.t_ms}ms)` };
  }
  if (res?.timeout) {
    const st = loadStaticScores().get(String(targetId));
    if (st && st.p_bert_v10_wb) {
      return { p: Number(st.p_bert_v10_wb), nUsed: Number(st.n_messages) || 0, source: `超时降级-静态(历史${st.n_messages}条)` };
    }
    return { errorText: '推理超时且无静态结果，请稍后重试' };
  }
  return { errorText: `推理进程异常：${res?.error ?? '未知错误'}` };
}

// ============================================================
// 私聊规则（原有，不变）
// ============================================================

/** 组装私聊推理回复文本（含男娘指数） */
export async function buildReply(targetId, db) {
  const label = getLabel(db, targetId);
  const r = await runInference(targetId, db);
  if (r.noData) return `【推理 ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  if (r.errorText) return `【推理 ${targetId}】\n${r.errorText}`;

  const p = r.p;
  const gender = p >= V10_WB_THRESHOLD ? '女' : '男';
  const conf = confidenceFor(p, r.nUsed);
  const labeled = label ? `是（${label.gender}${label.orientation ? `/${label.orientation}` : ''}）` : '否';
  const disagreement = loadDisagreement(String(targetId));

  const lines = [
    `【推理 ${targetId}】`,
    `性别结论：${gender}`,
    `P(女)：${(p * 100).toFixed(1)}%`,
    `置信度：${conf}`,
    `是否已标注：${labeled}`,
    `分歧指数：${disagreement}`,
    `数据来源：${r.source}`,
  ];

  const labeledMale = label && (label.gender === 'male');
  if (gender === '男' || labeledMale) {
    const foiVal = loadFoiValue(targetId);
    if (foiVal != null) {
      const tip = foiVal >= 80 ? '（男娘信号强）' : foiVal >= 60 ? '（男娘信号中）' : foiVal >= 45 ? '（男娘信号弱）' : '';
      lines.push(`男娘指数：${foiVal.toFixed(0)}/100${tip}`);
    } else {
      lines.push('男娘指数：无数据（样本不足或未计算）');
    }
  }
  return lines.join('\n');
}

/** 私聊触发处理（原逻辑） */
async function handlePrivate(record, db, bot, log) {
  if (record.user_id !== TRIGGER_QQ) return false;
  const text = (record.text || '').trim();
  const m = text.match(RE_PRIVATE);
  if (!m) return false;
  const targetId = Number(m[1]);
  log.info(`[infer][私聊] ${TRIGGER_QQ} 请求推理 ${targetId}`);
  const reply = await buildReply(targetId, db);
  try {
    if (record.peer_id) await bot.callApi('send_private_msg', { user_id: record.peer_id, message: reply });
    log.info(`[infer][私聊] → ${record.peer_id}: ${reply.split('\n')[0]}`);
  } catch (e) {
    log.warn(`[infer][私聊] 发送失败: ${e.message}`);
  }
  return true;
}

// ============================================================
// 群聊规则（826904606，机器人被@才触发）
// ============================================================

/** 从消息段解析目标 QQ（@ 段优先（跳过机器人自己），其次文本数字） */
function extractTargetFromEvent(ev, re, selfId, textFallback) {
  const segs = Array.isArray(ev.message) ? ev.message : [];
  // 1) @ 段（非机器人、非 all、非自己）
  for (const s of segs) {
    if (s.type === 'at' && s.data?.qq && s.data.qq !== 'all') {
      const qq = Number(s.data.qq);
      if (Number.isInteger(qq) && qq >= 10000 && String(qq) !== String(selfId)) return qq;
    }
  }
  // 2) 纯文本数字：优先用 cqToText 产物（record.text，@ 已转名字），其次 raw_message
  const candidates = [textFallback, ev.raw_message].filter(Boolean);
  for (const raw of candidates) {
    const text = String(raw).trim().replace(/^@[^\s]+\s*/, '').trim();
    const m = text.match(re);
    if (m && m[1]) return Number(m[1]);
  }
  return null;
}

/** 消息是否 @ 了机器人 */
function isMentioned(ev, selfId) {
  const segs = Array.isArray(ev.message) ? ev.message : [];
  for (const s of segs) {
    if (s.type === 'at' && (String(s.data?.qq) === String(selfId) || s.data?.qq === 'all')) return true;
  }
  return false;
}

/** 群聊推理回复（判女直说、标注仅是否、无男娘指数） */
async function buildGroupInferReply(targetId, db, bot, groupId) {
  // 1) 群成员校验
  const inGroup = await bot.isGroupMember(groupId, targetId);
  if (!inGroup) {
    return `【推理 ${targetId}】\n无数据（该用户不在本群）`;
  }
  const label = getLabel(db, targetId);
  const r = await runInference(targetId, db);
  if (r.noData) return `【推理 ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  if (r.errorText) return `【推理 ${targetId}】\n${r.errorText}`;

  const p = r.p;
  const gender = p >= V10_WB_THRESHOLD ? '女' : '男';
  const conf = confidenceFor(p, r.nUsed);
  const labeled = label ? '是' : '否';
  const disagreement = loadDisagreement(String(targetId));

  // 模型判女 → 直接回复模型判女 + 概率 + 置信度
  if (gender === '女') {
    return [
      `【推理 ${targetId}】`,
      `模型判女`,
      `P(女)：${(p * 100).toFixed(1)}%`,
      `置信度：${conf}`,
      `是否已标注：${labeled}`,
      `分歧指数：${disagreement}`,
    ].join('\n');
  }

  return [
    `【推理 ${targetId}】`,
    `性别结论：${gender}`,
    `P(女)：${(p * 100).toFixed(1)}%`,
    `置信度：${conf}`,
    `是否已标注：${labeled}`,
    `分歧指数：${disagreement}`,
    `数据来源：${r.source}`,
  ].join('\n');
}

/** 群聊 xnn 回复（男娘指数） */
async function buildGroupXnnReply(targetId, db, bot, groupId) {
  const inGroup = await bot.isGroupMember(groupId, targetId);
  if (!inGroup) {
    return `【xnn ${targetId}】\n无数据（该用户不在本群）`;
  }
  const label = getLabel(db, targetId);
  const foiVal = loadFoiValue(targetId);
  const hasMsgs = latestMessages(db, targetId, 1).length > 0;
  if (!hasMsgs) return `【xnn ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  if (foiVal == null) return `【xnn ${targetId}】\n男娘指数：无数据（样本不足或未计算）`;
  const tip = foiVal >= 80 ? '（男娘信号强）' : foiVal >= 60 ? '（男娘信号中）' : foiVal >= 45 ? '（男娘信号弱）' : '';
  return [
    `【xnn ${targetId}】`,
    `男娘指数：${foiVal.toFixed(0)}/100${tip}`,
    `是否已标注：${label ? '是' : '否'}`,
  ].join('\n');
}

/** 群聊触发处理 */
async function handleGroup(record, ev, selfId, db, bot, log) {
  if (!GROUP_IDS.includes(record.peer_id)) return false;
  if (!isMentioned(ev, selfId)) return false;
  // text 以 "@bot " 开头（cqToText 把 @ 放最前），命令匹配需容忍前缀
  const text = (record.text || '').trim();
  const stripped = text.replace(/^@[^\s]+\s*/, '').trim();   // 去掉 @bot 前缀
  const isInfer = /^推理/.test(stripped);
  const isXnn = /^xnn/.test(stripped);
  if (!isInfer && !isXnn) return false;

  const re = isInfer ? RE_GROUP_INFER : RE_XNN;
  const targetId = extractTargetFromEvent(ev, re, selfId, record.text);
  log.info(`[infer][群聊] ${record.peer_id} @bot ${isInfer ? '推理' : 'xnn'} → target=${targetId ?? '未解析出QQ'}`);
  if (!targetId) return false;

  log.info(`[infer][群聊] ${record.peer_id} @bot ${isInfer ? '推理' : 'xnn'} ${targetId}`);
  const reply = isInfer
    ? await buildGroupInferReply(targetId, db, bot, record.peer_id)
    : await buildGroupXnnReply(targetId, db, bot, record.peer_id);
  try {
    await bot.sendGroupMessage(record.peer_id, reply);
    log.info(`[infer][群聊] → ${record.peer_id}: ${reply.split('\n')[0]}`);
  } catch (e) {
    log.warn(`[infer][群聊] 发送失败: ${e.message}`);
  }
  return true;
}

// ============================================================
// 统一入口 + 时间戳顺序队列（防并发）
// ============================================================

let cmdQueue = [];       // {ts, record, ev, selfId}
let processing = false;

/**
 * 统一入口：检测并处理推理命令（私聊/群聊）。按消息时间戳入队，串行执行。
 * @param {object} record  规范化消息记录（scene/user_id/peer_id/text/time）
 * @param {object} ev      原始 OneBot 事件（含 message 段，用于 @ 解析）
 * @param {number} selfId  机器人自身 QQ（@ 检测用）
 */
export function handleInferRule(record, ev, selfId, db, bot, log) {
  if (!record || !ev) return false;
  // 调试日志：记录收到的候选消息（含 @ 检测结果）
  try {
    const ats = (ev.message || []).filter((s) => s.type === 'at').map((s) => s.data?.qq);
    const debug = `[infer][debug] scene=${record.scene} peer=${record.peer_id} user=${record.user_id} ` +
      `self=${selfId} ats=[${ats.join(',')}] text="${(record.text || '').slice(0, 30)}"`;
    log.info(debug);
  } catch { /* ignore */ }
  // 先判断是否可能命中（私聊触发人 + 群聊@），不命中直接返回
  let possible = false;
  if (record.scene === 'private' && record.user_id === TRIGGER_QQ && /^推理/.test(record.text || '')) possible = true;
  if (record.scene === 'group' && GROUP_IDS.includes(record.peer_id) && isMentioned(ev, selfId)) {
    const stripped = (record.text || '').replace(/^@[^\s]+\s*/, '').trim();
    if (/^推理/.test(stripped) || /^xnn/.test(stripped)) possible = true;
  }
  if (!possible) return false;

  cmdQueue.push({ ts: record.time ?? Date.now(), record, ev, selfId });
  cmdQueue.sort((a, b) => a.ts - b.ts);   // 按时间戳排序
  if (!processing) drainQueue(db, bot, log);
  return true;
}

async function drainQueue(db, bot, log) {
  processing = true;
  while (cmdQueue.length) {
    const { record, ev, selfId } = cmdQueue.shift();
    try {
      if (record.scene === 'private') {
        await handlePrivate(record, db, bot, log);
      } else if (record.scene === 'group') {
        await handleGroup(record, ev, selfId, db, bot, log);
      }
    } catch (e) {
      log.warn(`[infer] 处理失败: ${e.message}`);
    }
  }
  processing = false;
}

export function stopInfer() {
  if (py) { try { py.kill(); } catch { /* ignore */ } py = null; }
  cmdQueue = [];
}
