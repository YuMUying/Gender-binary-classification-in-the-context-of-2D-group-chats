/**
 * infer.js — 私聊性别推理响应
 *
 * 触发：私聊来自 2633083674，文本匹配 /^推理\s+(\d+)/（如 "推理 2673619125"）
 *
 * 流程：
 *   1. 从 DB 取目标用户最新入库的 N 条消息（ORDER BY collected_at DESC = 新入库优先）
 *   2. 交给常驻 Python 子进程（train/infer_one.py + bert-v10-wb）实时推理
 *   3. 超时（INFER_TIMEOUT_MS，默认 30s）→ 降级用 outputs/score-multi-v10.csv 静态结果
 *   4. DB 无该用户消息 → 回复"无用户数据"
 *   5. 输出：性别结论 / P(女) 概率 / 置信度 / 是否已标注 / 分歧指数；
 *      男性附加男娘指数（FOI，无 Kalman 平滑版 = foi_final.csv 的混合值）
 */
import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const TRIGGER_QQ = 2633083674;          // 只有这个号发的私聊触发
const RE = /^推理\s*[:：]?\s*(\d{5,12})/;
const SAMPLE_N = 100;                    // 采样最新 N 条消息
const INFER_TIMEOUT_MS = 30000;          // 推理超时（超时降级静态结果）
const V10_WB_THRESHOLD = 0.73;           // bert-v10-wb 阈值

let py = null;                           // 常驻 Python 子进程
let pyQueue = [];                        // 等待响应的回调队列
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
        continue;   // ready 消息不消费业务回调
      }
      const cb = pyQueue.shift();
      if (cb) cb(obj);
    }
  });
  py.stderr.on('data', (d) => { /* 保留静默，错误在超时兜底 */ });
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
    const cb = (obj) => {
      clearTimeout(timer);
      resolve(obj);
    };
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
      // 等待 ready（最多 30s），期间若进程退出会由 exit 回调兜底
      const t = setInterval(() => {
        if (pyReady) { clearInterval(t); doWrite(); }
      }, 100);
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

/** 置信度判定（实时推理版）：样本充足 + 概率远离阈值 → high */
function confidenceFor(p, n) {
  if (n < 20) return 'low-data（样本不足）';
  if (Math.abs(p - V10_WB_THRESHOLD) < 0.15) return 'borderline（临界）';
  return 'high';
}

/**
 * 处理一条私聊消息。返回是否命中规则。
 * @param {object} record 规范化消息记录
 * @param {object} db
 * @param {object} bot   OneBotClient（发送回复用）
 * @param {object} log
 */
export async function handleInferRule(record, db, bot, log) {
  if (record.scene !== 'private') return false;
  if (record.user_id !== TRIGGER_QQ) return false;
  const text = (record.text || '').trim();
  const m = text.match(RE);
  if (!m) return false;

  const targetId = Number(m[1]);
  log.info(`[infer] ${TRIGGER_QQ} 请求推理 ${targetId}`);
  const reply = await buildReply(targetId, db);
  try {
    if (record.peer_id) await bot.callApi('send_private_msg', { user_id: record.peer_id, message: reply });
    log.info(`[infer] → ${record.peer_id}: ${reply.slice(0, 60)}`);
  } catch (e) {
    log.warn(`[infer] 发送失败: ${e.message}`);
  }
  return true;
}

/** 组装推理回复文本 */
export async function buildReply(targetId, db) {
  const msgs = latestMessages(db, targetId, SAMPLE_N);
  const label = getLabel(db, targetId);

  if (!msgs.length) {
    return `【推理 ${targetId}】\n无用户数据（数据库中无该用户的消息记录）`;
  }

  // 1) 实时推理（新入库消息采样），带超时降级
  let p = null, nUsed = msgs.length, source = '实时采样';
  const req = {
    texts: msgs.map((m) => m.text),
    nicknames: msgs.map((m) => m.nickname ?? null),
  };
  const res = await inferRequest(req, INFER_TIMEOUT_MS);
  if (res && typeof res.p_female === 'number') {
    p = res.p_female;
    nUsed = res.n ?? nUsed;
    source = `实时采样${nUsed}条(${res.t_ms}ms)`;
  } else if (res?.timeout) {
    // 2) 超时降级：静态结果
    const st = loadStaticScores().get(String(targetId));
    if (st && st.p_bert_v10_wb) {
      p = Number(st.p_bert_v10_wb);
      source = `超时降级-静态(历史${st.n_messages}条)`;
    } else {
      return `【推理 ${targetId}】\n推理超时且无静态结果，请稍后重试`;
    }
  } else {
    return `【推理 ${targetId}】\n推理进程异常：${res?.error ?? '未知错误'}`;
  }

  // 3) 组装结果
  const gender = p >= V10_WB_THRESHOLD ? '女' : '男';
  const conf = confidenceFor(p, nUsed);
  const labeled = label ? `是（${label.gender}${label.orientation ? `/${label.orientation}` : ''}）` : '否';
  const disagreement = loadDisagreement(String(targetId));

  let lines = [
    `【推理 ${targetId}】`,
    `性别结论：${gender}`,
    `P(女)：${(p * 100).toFixed(1)}%`,
    `置信度：${conf}`,
    `是否已标注：${labeled}`,
    `分歧指数：${disagreement}`,
    `数据来源：${source}`,
  ];

  // 4) 男娘指数：模型判男 → 输出；模型判女但已标注为男 → 也输出（"男声女气"需男娘信号辅助）
  const labeledMale = label && (label.gender === 'male');
  if (gender === '男' || labeledMale) {
    const foi = loadFoiMap().get(String(targetId));
    const foiVal = foi ? Number(foi.foi_index) : null;
    if (foiVal != null && !isNaN(foiVal)) {
      const tip = foiVal >= 80 ? '（男娘信号强）' : foiVal >= 60 ? '（男娘信号中）' : foiVal >= 45 ? '（男娘信号弱）' : '';
      lines.push(`男娘指数：${foiVal.toFixed(0)}/100${tip}`);
    } else {
      lines.push('男娘指数：无数据（样本不足或未计算）');
    }
  }

  return lines.join('\n');
}

/** 分歧指数（静态表 disagreement 字段） */
function loadDisagreement(userId) {
  const st = loadStaticScores().get(userId);
  return st?.disagreement ?? '未知';
}

export function stopInfer() {
  if (py) { try { py.kill(); } catch { /* ignore */ } py = null; }
}
