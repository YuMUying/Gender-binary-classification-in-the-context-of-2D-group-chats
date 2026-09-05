/**
 * infer.js — 性别推理响应（私聊 + 群聊）
 *
 * 【私聊规则】（原有，不改）
 *   触发：私聊来自 0，文本匹配 /^推理\s+(\d+)/
 *   输出：性别/概率/置信度/是否已标注(含标签)/分歧指数；男或标注男附艾草value
 *
 * 【群聊规则】（0，机器人被@才触发）
 *   命令1：推理 <QQ号> 或 推理 @某人
 *     - 目标必须在群内（get_group_member_info 校验），不在群 → 无数据
 *     - 输出：性别/概率/置信度/是否已标注(仅是否)/分歧指数；不含艾草value
 *     - 模型判女 → 直接回复"模型判女"+概率+置信度
 *   命令2：xnn <QQ号> 或 xnn @某人
 *     - 输出艾草value（无 Kalman 平滑版）
 *
 * 【并发控制】所有命令按消息到达时间戳入队，串行处理（时间戳顺序）。
 */
import { spawn, execFile } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// ---- 配置 ----
const TRIGGER_QQ = 0;          // 私聊触发器
const GROUP_IDS = [0, 0];  // 群聊命令启用群（0 主群 + 0 调试小群）
const DEBUG_SAMPLE_RATE = 0.05;         // debug 日志抽样率（所有消息 5% 记录）
const RE_PRIVATE = /^(推理|xnn)\s*[:：]?\s*(\d{5,12})/;
const RE_GROUP_INFER = /^推理\s*[:：]?\s*(?:@?\s*(\d{5,12})|.+)/;   // 推理 <qq> 或 推理 @某人
const RE_XNN = /^xnn\s*[:：]?\s*(?:@?\s*(\d{5,12})|.+)/;            // xnn <qq> 或 xnn @某人
const SAMPLE_N = 100;
const INFER_TIMEOUT_MS = 30000;
const V10_WB_THRESHOLD = 0.73;

// ---- GPU 占用检测（占用过高时降级为静态表，避免挤爆显存） ----
const GPU_MEM_USED_PCT = 0.85;     // 显存占用 ≥85% 视为 GPU 高负载
const GPU_UTIL_PCT = 85;           // GPU 利用率 ≥85% 视为 GPU 高负载
const GPU_CHECK_TTL_MS = 3000;     // 检测结果缓存 3 秒，避免频繁 spawn nvidia-smi
let gpuBusyCache = null;
let gpuBusyAt = 0;

/** 检测 GPU 是否高负载（显存占用比或利用率任一超阈值） */
function checkGpuBusy() {
  return new Promise((resolve) => {
    const now = Date.now();
    if (gpuBusyCache !== null && now - gpuBusyAt < GPU_CHECK_TTL_MS) return resolve(gpuBusyCache);
    execFile('nvidia-smi',
      ['--query-gpu=memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'],
      { timeout: 4000, windowsHide: true },
      (err, stdout) => {
        if (err || !stdout) { gpuBusyCache = false; gpuBusyAt = Date.now(); return resolve(false); }
        const line = (stdout.trim().split('\n')[0] || '').split(',');
        const used = parseFloat(line[0]);
        const total = parseFloat(line[1]);
        const util = parseFloat(line[2]);
        const busy = !Number.isNaN(used) && !Number.isNaN(total) && total > 0
          ? (used / total >= GPU_MEM_USED_PCT || (Number.isFinite(util) && util >= GPU_UTIL_PCT))
          : false;
        gpuBusyCache = busy;
        gpuBusyAt = Date.now();
        resolve(busy);
      });
  });
}

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

/** 加载 r3 abstain 静态表（r3-s0v56 三seed 全账本 P_female，2026-09-05 abstain 决策） */
let r3Scores = null;
function loadR3Scores() {
  if (r3Scores) return r3Scores;
  const p = path.join(ROOT, 'outputs', 'r3-abstain-scores.csv');
  r3Scores = new Map();
  if (!existsSync(p)) return r3Scores;
  try {
    const lines = readFileSync(p, 'utf8').split('\n');
    const cols = lines[0].trim().split(',');
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].trim().split(',');
      if (vals.length < cols.length) continue;
      const row = {};
      cols.forEach((c, j) => (row[c.trim()] = vals[j]?.trim() ?? ''));
      if (row.user_id) r3Scores.set(row.user_id, Number(row.p_female));
    }
  } catch (e) { /* ignore */ }
  return r3Scores;
}

const R3_ABSTAIN_LO = 0.35;   // r3 P_female < 0.35 → male（自动）
const R3_ABSTAIN_HI = 0.50;   // r3 P_female >= 0.50 → female（自动）；之间 → abstain

/** r3 abstain 裁决：命中静态表返回 {verdict, pf}，否则 null */
function r3Verdict(userId) {
  const pf = loadR3Scores().get(String(userId));
  if (pf == null || Number.isNaN(pf)) return null;
  if (pf >= R3_ABSTAIN_HI) return { verdict: 'female', pf };
  if (pf < R3_ABSTAIN_LO) return { verdict: 'male', pf };
  return { verdict: 'abstain', pf };
}

/** 加载带内三通道参考表（v10/LLM/标定模型，2026-09-05 第三参考通道，仅供参考不作裁决） */
let bandRef = null;
function loadBandReference() {
  if (bandRef) return bandRef;
  const p = path.join(ROOT, 'outputs', 'band-reference-s0v56.csv');
  bandRef = new Map();
  if (!existsSync(p)) return bandRef;
  try {
    const lines = readFileSync(p, 'utf8').split('\n');
    const cols = lines[0].trim().split(',');
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].trim().split(',');
      if (vals.length < cols.length) continue;
      const row = {};
      cols.forEach((c, j) => (row[c.trim()] = vals[j]?.trim() ?? ''));
      if (row.user_id) bandRef.set(row.user_id, row);
    }
  } catch (e) { /* ignore */ }
  return bandRef;
}

/** 加载艾草value表（models/acao-bert 全库推理结果，0-1） */
let foiMap = null;
function loadFoiMap() {
  if (foiMap) return foiMap;
  const p = path.join(ROOT, 'outputs', 'acao_value.csv');
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
      const uid = row['QQ号'] ?? row.user_id;
      if (uid) foiMap.set(String(uid), row);
    }
  } catch (e) { /* ignore */ }
  return foiMap;
}

/** 加载 LGBT 小众性取向指数表（v4 独立指数） */
let lgbtMap = null;
function loadLgbtMap() {
  if (lgbtMap) return lgbtMap;
  const p = path.join(ROOT, 'outputs', 'lgbt_index.csv');
  lgbtMap = new Map();
  if (!existsSync(p)) return lgbtMap;
  try {
    const lines = readFileSync(p, 'utf8').split('\n');
    const cols = lines[0].trim().split(',');
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].trim().split(',');
      if (vals.length < cols.length) continue;
      const row = {};
      cols.forEach((c, j) => (row[c.trim()] = vals[j]?.trim() ?? ''));
      const uid = row['QQ号'] ?? row.user_id;
      if (uid) lgbtMap.set(String(uid), row);
    }
  } catch (e) { /* ignore */ }
  return lgbtMap;
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

/** 艾草value（0-1，衡量男性当受接受度） */
function loadFoiValue(userId) {
  const foi = loadFoiMap().get(String(userId));
  const v = foi ? Number(foi.acao_value ?? foi.艾草value) : null;
  if (v == null || isNaN(v)) return null;
  return v;
}

/** LGBT 小众性取向指数（v4 独立指数） */
function loadLgbtValue(userId) {
  const lgbt = loadLgbtMap().get(String(userId));
  const v = lgbt ? Number(lgbt.LGBT小众性取向指数) : null;
  if (v == null || isNaN(v)) return null;
  return v;
}

/** 执行一次推理，返回 {p, nUsed, source} 或抛错/返回错误文本 */
async function runInference(targetId, db) {
  // GPU 高负载 → 直接输出数据库静态值，不启动实时推理
  const gpuBusy = await checkGpuBusy();
  if (gpuBusy) {
    const st = loadStaticScores().get(String(targetId));
    if (st && st['p_bert-v10-wb']) {
      return { p: Number(st['p_bert-v10-wb']), nUsed: Number(st.n_messages) || 0, source: `GPU高负载-静态(历史${st.n_messages}条)` };
    }
    return { errorText: 'GPU 占用过高且无静态结果，请稍后重试' };
  }
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
    if (st && st['p_bert-v10-wb']) {
      return { p: Number(st['p_bert-v10-wb']), nUsed: Number(st.n_messages) || 0, source: `超时降级-静态(历史${st.n_messages}条)` };
    }
    return { errorText: '推理超时且无静态结果，请稍后重试' };
  }
  return { errorText: `推理进程异常：${res?.error ?? '未知错误'}` };
}

// ============================================================
// 私聊规则（原有，不变）
// ============================================================

/** 组装私聊推理回复文本（含艾草value） */
export async function buildReply(targetId, db) {
  const label = getLabel(db, targetId);
  const r = await runInference(targetId, db);
  if (r.noData) return `【推理 ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  if (r.errorText) return `【推理 ${targetId}】\n${r.errorText}`;

  const p = r.p;
  // ---- r3 abstain 层（2026-09-05）：静态表命中的用户用 r3 三分类裁决，0.35-0.5 输出不确定 ----
  const r3 = r3Verdict(targetId);
  if (r3) {
    const conf3 = r3.verdict === 'abstain' ? 'abstain（转人工/带外验证）' : (r3.verdict === 'female' ? 'high（r3≥0.50）' : 'auto（r3<0.35）');
    const lines3 = [
      `【推理 ${targetId}】`,
      `性别结论：${r3.verdict === 'female' ? '女' : r3.verdict === 'male' ? '男' : '不确定（疑似男域原生女）'}`,
      `P(女/r3)：${(r3.pf * 100).toFixed(1)}%`,
      `裁决：${conf3}`,
      `裁决口径：r3-s0v56 三seed（abstain 带 0.35-0.50，docs/decisions.md）`,
      ...(r3.verdict === 'abstain' && loadBandReference().get(String(targetId)) ? (() => {
        const ref = loadBandReference().get(String(targetId));
        const v10s = ref.p_v10 !== '' ? `v10=${ref.v10_lean}(${Number(ref.p_v10).toFixed(2)})` : 'v10=无';
        return [`参考信号：${v10s} | LLM=${ref.llm_lean} | 标定P=${Number(ref.p_calibrated).toFixed(2)} | F票${ref.f_votes}/M票${ref.m_votes}（仅供参考）`];
      })() : []),
      `数据来源：${r.source} + r3 静态表`,
    ];
    return lines3.join('\n');
  }
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
      const tip = foiVal >= 0.85 ? '（当受信号强）' : foiVal >= 0.6 ? '（当受信号中）' : foiVal >= 0.45 ? '（当受信号弱）' : '';
      lines.push(`艾草value：${foiVal.toFixed(2)}${tip}`);
    } else {
      lines.push('艾草value：无数据（样本不足或未计算）');
    }
  }
  return lines.join('\n');
}

/** 私聊触发处理（推理 + xnn） */
async function handlePrivate(record, db, bot, log) {
  if (record.user_id !== TRIGGER_QQ) return false;
  const text = (record.text || '').trim();
  const m = text.match(RE_PRIVATE);
  if (!m) return false;
  const cmd = m[1];                     // 推理 | xnn
  const targetId = Number(m[2]);
  log.info(`[infer][私聊] ${TRIGGER_QQ} 请求 ${cmd} ${targetId}`);
  let reply;
  if (cmd === 'xnn') {
    // 私聊 xnn：只返回艾草value
    const label = getLabel(db, targetId);
    const hasMsgs = latestMessages(db, targetId, 1).length > 0;
    if (!hasMsgs) {
      reply = `【xnn ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
    } else {
      const foiVal = loadFoiValue(targetId);
      if (foiVal == null) {
        reply = `【xnn ${targetId}】\n艾草value：无数据（样本不足或未计算）`;
      } else {
        const tip = foiVal >= 0.85 ? '（当受信号强）' : foiVal >= 0.6 ? '（当受信号中）' : foiVal >= 0.45 ? '（当受信号弱）' : '';
        reply = [
          `【xnn ${targetId}】`,
          `艾草value：${foiVal.toFixed(2)}${tip}`,
          `是否已标注：${label ? '是' : '否'}`,
        ].join('\n');
      }
    }
  } else {
    reply = await buildReply(targetId, db);
  }
  try {
    if (record.peer_id) await bot.callApi('send_private_msg', { user_id: record.peer_id, message: reply });
    log.info(`[infer][私聊] → ${record.peer_id}: ${reply.split('\n')[0]}`);
  } catch (e) {
    log.warn(`[infer][私聊] 发送失败: ${e.message}`);
  }
  return true;
}

// ============================================================
// 群聊规则（0，机器人被@才触发）
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

/** 群聊推理回复（判女直说、标注仅是否、无艾草value） */
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

/** 群聊 xnn 回复（艾草value） */
async function buildGroupXnnReply(targetId, db, bot, groupId) {
  const inGroup = await bot.isGroupMember(groupId, targetId);
  if (!inGroup) {
    return `【xnn ${targetId}】\n无数据（该用户不在本群）`;
  }
  const label = getLabel(db, targetId);
  const foiVal = loadFoiValue(targetId);
  const hasMsgs = latestMessages(db, targetId, 1).length > 0;
  if (!hasMsgs) return `【xnn ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  if (foiVal == null) return `【xnn ${targetId}】\n艾草value：无数据（样本不足或未计算）`;
  const tip = foiVal >= 0.85 ? '（当受信号强）' : foiVal >= 0.6 ? '（当受信号中）' : foiVal >= 0.45 ? '（当受信号弱）' : '';
  return [
    `【xnn ${targetId}】`,
    `艾草value：${foiVal.toFixed(2)}${tip}`,
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
  // 调试日志：异常/命令相关消息必记录，其余按抽样率记录
  try {
    const ats = (ev.message || []).filter((s) => s.type === 'at').map((s) => s.data?.qq);
    const text = record.text || '';
    const isCmdLike = /^推理/.test(text.replace(/^@[^\s]+\s*/, '').trim()) ||
                      /^xnn/.test(text.replace(/^@[^\s]+\s*/, '').trim());
    const isMentionedEvt = isMentioned(ev, selfId);
    if (isCmdLike || isMentionedEvt || Math.random() < DEBUG_SAMPLE_RATE) {
      const debug = `[infer][debug] scene=${record.scene} peer=${record.peer_id} user=${record.user_id} ` +
        `self=${selfId} ats=[${ats.join(',')}] text="${(text || '').slice(0, 30)}"`;
      log.info(debug);
    }
  } catch { /* ignore */ }
  // 先判断是否可能命中（私聊触发人 + 群聊@），不命中直接返回
  let possible = false;
  if (record.scene === 'private' && record.user_id === TRIGGER_QQ &&
      /^(推理|xnn)/.test(record.text || '')) possible = true;
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
