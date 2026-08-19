/**
 * export-dataset.js — CLI：导出数据集（支持按 QQ 号分层划分、类别平衡、多模态）
 *
 * 用法：
 *   node scripts/export-dataset.js --mode train [--out data/train.jsonl]
 *       [--split-by-user --val-ratio 0.15 --seed 42]     # 按 QQ 号划分，同一人不出现在 train/val 两侧
 *       [--balance]                                       # 多数类用户级欠采样
 *       [--min-per-user 5] [--max-per-user 2000]
 *       [--include-media]                                 # 每行附带 images: [本地图片路径]
 *
 *   node scripts/export-dataset.js --mode infer [--out data/infer.jsonl] [--min-per-user 0] [--include-media]
 *       → 未标注发言人的消息 → 待预测集
 *
 *   node scripts/export-dataset.js --mode all [--format csv|jsonl] [--out data/all.csv]
 *       → 全量消息导出（人工检查 / 备份）
 *
 * 训练集/推断集按"发言人（QQ号）"划分，防止个人口头禅导致的数据泄漏。
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { loadConfig, ROOT } from '../src/config.js';
import { openDb, getContext, labelMeta } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const has = (name) => args.includes(name);

const mode = arg('--mode') ?? 'all';
const format = arg('--format') ?? (mode === 'all' ? 'csv' : 'jsonl');
const out = arg('--out') ?? `data/${mode === 'train' ? 'train' : mode === 'infer' ? 'infer' : 'all'}.${format === 'csv' ? 'csv' : 'jsonl'}`;
const outVal = arg('--out-val') ?? 'data/val.jsonl';
const minPerUser = arg('--min-per-user') ? Number(arg('--min-per-user')) : 0;
const maxPerUser = arg('--max-per-user') ? Number(arg('--max-per-user')) : Infinity;
const splitByUser = has('--split-by-user');
const valRatio = arg('--val-ratio') ? Number(arg('--val-ratio')) : 0.15;
const balance = has('--balance');
const includeMedia = has('--include-media');
const contextN = arg('--context') ? Number(arg('--context')) : 0;
const foldContext = has('--fold-context');
const noNickname = has('--no-nickname');   // 消融实验：去掉昵称/名片特征
const useAvatarDesc = has('--avatar-desc');   // 附加每用户头像描述（research/avatar_desc.jsonl）
const useProfileMeta = has('--profile-meta'); // 附加每用户主页信息（profile_details 表）
const seed = arg('--seed') ? Number(arg('--seed')) : 42;

// ---------- 夜间噪声处理（--night-mode） ----------
// 深夜(0-6点)消息风格偏向情绪化/感性，与性别特征混杂。策略：
//   - 多样本用户（全量消息 ≥ nightHigh）：深夜消息直接剔除（白天样本充足）
//   - 少样本用户：深夜消息保留但降权（weight < 1，训练时 loss 加权）
//   - 深夜型少样本保护：用户深夜占比越高，降权越轻，避免样本被过度稀释
const nightMode = has('--night-mode');
const NIGHT_HIGH = arg('--night-high') ? Number(arg('--night-high')) : 200;
const NIGHT_HOURS_IN = (arg('--night-hours') ?? '00,01,02,03,04,05').split(',').map((s) => s.trim());
if (nightMode && NIGHT_HOURS_IN.some((h) => !/^\d{2}$/.test(h))) {
  throw new Error('--night-hours 必须是 HH 格式的逗号分隔列表（如 00,01,02,03,04,05）');
}
const NIGHT_HOURS = new Set(NIGHT_HOURS_IN);

/** 是否为深夜消息（time 为 unix 秒，换算 UTC+8） */
function isNight(time) {
  const d = new Date((Number(time) + 8 * 3600) * 1000);
  return NIGHT_HOURS.has(String(d.getUTCHours()).padStart(2, '0'));
}

/** 用户全量消息的深夜占比（用于决定剔除/降权/保护） */
function userNightRatio(userId) {
  const hours = [...NIGHT_HOURS].map((h) => `'${h}'`).join(',');
  const r = db.prepare(`
    SELECT COUNT(*) c,
           SUM(CASE WHEN strftime('%H', time, 'unixepoch', '+8 hours') IN (${hours}) THEN 1 ELSE 0 END) night
    FROM messages WHERE user_id=? AND scene IN ('group','private')`).get(userId);
  const c = r?.c ?? 0;
  return { total: c, ratio: c ? (r.night ?? 0) / c : 0 };
}

/** 少样本用户的深夜降权系数：深夜占比越高越少降权（保护深夜型少样本用户） */
function nightWeight(ratio) {
  if (ratio <= 0.3) return 0.5;
  if (ratio <= 0.6) return 0.7;
  return 0.9;
}

// 任务③：疑难用户强制进验证集（不进训练集），用于检验新通道对难例的效果
const holdoutUsers = new Set((arg('--holdout-users') ?? '').split(',').map((s) => Number(s.trim())).filter(Boolean));

// ---------- 头像描述 / 主页信息（按用户附加到样本） ----------
const avatarDesc = new Map();   // user_id -> 描述串
const profileMeta = new Map();  // user_id -> 主页信息串
if (useAvatarDesc || useProfileMeta) {
  const fs = await import('node:fs');
  if (useAvatarDesc) {
    const p = path.join(ROOT, 'research', 'avatar_desc.jsonl');
    try {
      for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
        if (!line.trim()) continue;
        const d = JSON.parse(line);
        const desc = d.desc ?? {};
        if (desc.overall || desc.content || desc.vibe) {
          avatarDesc.set(String(d.uin), [desc.content, desc.style, desc.vibe].filter(Boolean).join('；').slice(0, 120));
        }
      }
      log.info(`[avatar-desc] 载入头像描述 ${avatarDesc.size} 人`);
    } catch (e) { log.warn(`[avatar-desc] 读取失败: ${e.message}`); }
  }
  if (useProfileMeta) {
    for (const r of db.prepare('SELECT user_id, data_json FROM profile_details').all()) {
      try {
        const d = JSON.parse(r.data_json);
        const parts = [];
        if (d.age) parts.push(`${d.age}岁`);
        if (d.constellation) parts.push(`星座${d.constellation}`);
        if (d.shengXiao) parts.push(`属相${d.shengXiao}`);
        if (Array.isArray(d.labels) && d.labels.length) parts.push(`标签:${d.labels.join('/')}`);
        if (d.interest) parts.push(`兴趣:${String(d.interest).slice(0, 30)}`);
        if (d.country) parts.push(`地区:${d.country}`);
        const s = parts.join(' ');
        if (s) profileMeta.set(String(r.user_id), s.slice(0, 100));
      } catch { /* ignore */ }
    }
    log.info(`[profile-meta] 载入主页信息 ${profileMeta.size} 人`);
  }
}

// 标签置信度过滤：high(3) > medium(2) > low(1)，默认全部纳入
const CONF_RANK = { high: 3, medium: 2, low: 1 };
const minConfidence = arg('--min-confidence') ?? 'low';
const minConfRank = CONF_RANK[minConfidence] ?? 1;
const allowedConfs = Object.entries(CONF_RANK).filter(([, r]) => r >= minConfRank).map(([k]) => k);

// 群隔离验证：--val-groups 762673304,xxx → 这些群标注的用户整体进验证集（跨群泛化测试）
const valGroups = new Set((arg('--val-groups') ?? '').split(',').map((s) => Number(s.trim())).filter(Boolean));

// 训练排除名单：--exclude-users 123,456 或 config/excluded_users.json（机器人/噪音用户不进训练）
let excludeUsers = new Set((arg('--exclude-users') ?? '').split(',').map((s) => Number(s.trim())).filter(Boolean));
{
  const fs = await import('node:fs');
  const p = path.join(ROOT, 'config', 'excluded_users.json');
  try {
    const arr = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (Array.isArray(arr)) for (const u of arr) excludeUsers.add(Number(u));
  } catch { /* 文件不存在或格式错误则忽略 */ }
}
if (excludeUsers.size) log.info(`[exclude] 训练排除用户: ${[...excludeUsers].join(',')}`);

// 弱样本划入测试集：--weak-as-test 300 → 有效发言(<300)的标注用户强制进验证/测试集
const weakAsTest = arg('--weak-as-test') ? Number(arg('--weak-as-test')) : 0;

// ---------- 可复现随机 ----------
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

const MEDIA_SELECT = `
  (SELECT json_group_array(local_path) FROM media_files f
   WHERE f.message_id = m.message_id AND f.status = 'downloaded') AS images`;

function parseImages(row) {
  if (!includeMedia || row.images == null) return undefined;
  const arr = JSON.parse(row.images);
  const paths = (Array.isArray(arr) ? arr : []).filter(Boolean);
  return paths.length ? paths : undefined;
}

/** 取某用户的消息行（可限额；peerFilter 用于群隔离验证的消息级过滤；含私聊/转发消息） */
function rowsForUser(userId, cap = Infinity, peerFilter = null) {
  let rows = db.prepare(`
    SELECT user_id, peer_id AS group_id, time, text, CAST(message_id AS TEXT) AS message_id, nickname, card,
           ${includeMedia ? MEDIA_SELECT : 'NULL AS images'}
    FROM messages m WHERE user_id=? AND scene IN ('group','private') ORDER BY time ASC`).all(userId);
  if (peerFilter) rows = rows.filter((r) => peerFilter(r.group_id));
  return rows.slice(0, cap);
}

/**
 * 构造一条导出样本。
 *  - 默认附带 nickname（QQ 全局昵称快照）与 card（群名片快照），昵称/名片是强性别信号；
 *    --no-nickname 可去掉（消融实验）
 *  - --context N：附加同群前后各 N 条消息（before/after 数组，含发言人昵称/名片）
 *  - --fold-context：把上下文拼进 text，每行带发言人昵称前缀（"昵称: 文本"）
 */
function buildRow(r, label) {
  const row = { text: r.text, user_id: r.user_id, group_id: r.group_id, time: r.time };
  if (label !== undefined) row.label = label;
  if (!noNickname) {
    if (r.nickname != null) row.nickname = r.nickname;
    if (r.card != null && r.card !== '') row.card = r.card;
  }
  const ad = avatarDesc.get(String(r.user_id));
  if (useAvatarDesc && ad) row.avatar_desc = ad;
  const pm = profileMeta.get(String(r.user_id));
  if (useProfileMeta && pm) row.profile_meta = pm;

  if (contextN > 0) {
    const ctx = getContext(db, r.group_id, r.message_id, contextN);
    if (ctx) {
      const fmt = (m) => (foldContext ? `${m.nickname ?? m.user_id}: ${m.text}` : m.text);
      const before = ctx.before.map((m) => (foldContext ? fmt(m) : m.text));
      const after = ctx.after.map((m) => (foldContext ? fmt(m) : m.text));
      row.before = before;
      row.after = after;
      if (!foldContext && !noNickname) {
        row.before_meta = ctx.before.map((m) => ({ user_id: m.user_id, nickname: m.nickname, card: m.card ?? null }));
        row.after_meta = ctx.after.map((m) => ({ user_id: m.user_id, nickname: m.nickname, card: m.card ?? null }));
      }
      if (foldContext) row.text = [...before, fmt({ nickname: r.nickname ?? r.user_id, text: r.text }), ...after].join('\n');
    }
  }

  const imgs = parseImages(r);
  if (imgs) row.images = imgs;
  return row;
}

/** 已标注用户及每人消息数/有效数（按置信度过滤；含私聊/转发消息） */
function labeledUsers(confs) {
  const ph = confs.map(() => '?').join(',');
  return db.prepare(`
    SELECT l.user_id, l.gender, l.label_group, COUNT(m.id) c,
           SUM(CASE WHEN LENGTH(m.text) >= 4 THEN 1 ELSE 0 END) eff
    FROM speaker_labels l LEFT JOIN messages m ON m.user_id = l.user_id AND m.scene IN ('group','private')
    WHERE l.gender IN ('male','female') AND l.label_confidence IN (${ph})
    GROUP BY l.user_id, l.gender, l.label_group
    HAVING c >= ?`).all(...confs, minPerUser);
}

async function main() {
  mkdirSync(path.dirname(out), { recursive: true });

  if (mode === 'train') {
    let users = labeledUsers(allowedConfs);
    users = users.filter((u) => !excludeUsers.has(u.user_id));   // 排除机器人/噪音用户
    if (!users.length) {
      log.warn(`暂无符合条件（置信度 ≥ ${minConfidence}）的已标注用户，请先用 scripts/label.js 或 scripts/import-labels.js 标注`);
      process.exit(0);
    }

    const byGender = (g) => users.filter((u) => u.gender === g);
    const totalMsgs = (arr) => arr.reduce((s, u) => s + u.c, 0);
    const genders = [...new Set(users.map((u) => u.gender))];

    // --balance：多数类用户级欠采样到少数类总量
    // 用户粒度贪心：跳过会让总量超额超过 50% 的用户（避免单个话痨主导）
    if (balance && genders.length > 1) {
      const target = Math.min(...genders.map((g) => totalMsgs(byGender(g))));
      const rng = mulberry32(seed);
      const picked = [];
      for (const g of genders) {
        const pool = shuffle([...byGender(g)], rng);
        let acc = 0;
        for (const u of pool) {
          if (acc >= target) break;
          if (acc > 0 && acc + u.c > target * 1.5) continue;   // 超额太多则换下一位
          acc += u.c;
          picked.push(u);
        }
      }
      users = picked;
      log.info(`[balance] 欠采样后各性别消息量 ≈ ${target}（建议配合 --max-per-user 控制单人上限）`);
    }

    // --weak-as-test：有效发言 < N 的标注用户强制进验证/测试集（低资源用户泛化检验）
    // --split-by-user / --val-groups：按 QQ 号划分（同一人只在一侧；每性别至少留 1 人在 train）
    let trainUsers = users, valUsers = [];
    let trainPeerFilter = null, valPeerFilter = null;
    if (weakAsTest > 0) {
      const weak = users.filter((u) => (u.eff ?? 0) > 0 && (u.eff ?? 0) < weakAsTest);
      if (weak.length) {
        valUsers = weak.slice();
        trainUsers = users.filter((u) => !weak.includes(u));
        users = trainUsers;   // 随机划分只在剩余用户中进行
        log.info(`[弱样本入测试集] 有效发言 < ${weakAsTest} 的 ${weak.length} 人强制进测试集（含群2女性等低资源用户）`);
      }
    }
    if (valGroups.size > 0) {
      // 群隔离验证：指定群的用户整体进验证集，且消息级过滤——
      // train 只含非验证群的消息，val 只含验证群的消息（成员跨群重合时结论才干净）
      valUsers.push(...users.filter((u) => u.label_group != null && valGroups.has(u.label_group)));
      trainUsers = users.filter((u) => !(u.label_group != null && valGroups.has(u.label_group)));
      trainPeerFilter = (peer) => !valGroups.has(peer);
      valPeerFilter = (peer) => valGroups.has(peer);
      log.info(`[群隔离] 群 ${[...valGroups].join(',')} 的用户整体进验证集；消息级过滤：train 只含非验证群消息，val 只含验证群消息`);
    } else if (splitByUser) {
      const rng = mulberry32(seed);
      for (const g of genders) {
        const pool = shuffle(byGender(g), rng);
        const n = Math.min(pool.length - 1, Math.max(0, Math.round(pool.length * Math.min(Math.max(valRatio, 0), 0.5))));
        valUsers.push(...pool.slice(0, n));
        trainUsers = trainUsers.filter((u) => !pool.slice(0, n).includes(u));
      }
    }
    // 任务③：疑难用户强制进验证集（不参与训练）
    if (holdoutUsers.size > 0) {
      const ho = users.filter((u) => holdoutUsers.has(u.user_id));
      if (ho.length) {
        valUsers.push(...ho);
        trainUsers = users.filter((u) => !holdoutUsers.has(u.user_id) && !valUsers.includes(u));
        log.info(`[holdout] 疑难用户 ${ho.map((u) => u.user_id).join(',')} 强制进验证集（不参与训练）`);
      }
    }

    const trainIds = new Set(trainUsers.map((u) => u.user_id));
    const valIds = new Set(valUsers.map((u) => u.user_id));

    const trainLines = [], valLines = [];
    let trainCount = 0, valCount = 0;
    let nightDropped = 0, nightWeighted = 0;
    const cap = maxPerUser;

    /** 生成某用户的行；nightMode 下多样本剔除深夜、少样本降权。返回生成行数。 */
    const emitRows = (u, rows, lines) => {
      const ns = nightMode ? userNightRatio(u.user_id) : null;
      const dropNight = ns != null && ns.total >= NIGHT_HIGH;   // 多样本：剔除
      let n = 0;
      for (const r of rows) {
        const row = buildRow(r, u.gender);
        if (nightMode && isNight(r.time)) {
          if (dropNight) { nightDropped++; continue; }           // 剔除深夜噪声
          row.weight = nightWeight(ns.ratio);                    // 少样本：降权
          row.night = true;
          nightWeighted++;
        }
        lines.push(JSON.stringify(row));
        n++;
      }
      return n;
    };

    for (const u of trainUsers) {
      const rows = rowsForUser(u.user_id, cap, trainPeerFilter);
      if (!rows.length) continue;
      trainCount += emitRows(u, rows, trainLines);
    }
    for (const u of valUsers) {
      const rows = rowsForUser(u.user_id, cap, valPeerFilter);
      if (!rows.length) continue;
      valCount += emitRows(u, rows, valLines);
    }

    writeFileSync(out, trainLines.join('\n') + (trainLines.length ? '\n' : ''), 'utf8');
    log.info(`导出 train: ${out}（${trainCount} 行, 用户 ${trainUsers.length} 人${contextN > 0 ? `, 上下文窗口 ±${contextN}${foldContext ? '（已折叠进 text）' : ''}` : ''}）`);
    if (nightMode) {
      log.info(`[night] 多样本用户深夜消息剔除 ${nightDropped} 条 | 少样本用户深夜降权 ${nightWeighted} 条`);
    }
    if ((splitByUser || valGroups.size > 0) && valUsers.length) {
      mkdirSync(path.dirname(outVal), { recursive: true });
      writeFileSync(outVal, valLines.join('\n') + (valLines.length ? '\n' : ''), 'utf8');
      log.info(`导出 val:   ${outVal}（${valCount} 行, 用户 ${valUsers.length} 人）`);
    }
    log.info('划分详情:');
    for (const g of genders) {
      log.info(`  ${g}: train ${trainUsers.filter((u) => u.gender === g).length} 人 / val ${valUsers.filter((u) => u.gender === g).length} 人`);
    }
    log.info(`同一 QQ 号跨集: ${[...trainIds].filter((id) => valIds.has(id)).length ? '存在(异常!)' : '无 ✔'}`);

    // 标签版本元数据：训练流水线据此判断是否需要重训
    const meta = {
      generated_at: Math.floor(Date.now() / 1000),
      context_window: contextN,
      fold_context: foldContext,
      include_media: includeMedia,
      min_confidence: minConfidence,
      val_groups: valGroups.size ? [...valGroups] : null,
      users: Object.fromEntries(genders.map((g) => [g, trainUsers.filter((u) => u.gender === g).length])),
      messages: { train: trainCount, val: valCount },
      night: nightMode
        ? { mode: 'auto', high: NIGHT_HIGH, hours: NIGHT_HOURS_IN, dropped: nightDropped, weighted: nightWeighted }
        : null,
      ...labelMeta(db),
    };
    const metaFile = `${out}.meta.json`;
    writeFileSync(metaFile, JSON.stringify(meta, null, 2), 'utf8');
    log.info(`标签元数据: ${metaFile}（label_updated_at=${meta.max_label_updated_at ?? '?'}，标签变化后可据此触发重训）`);

  } else if (mode === 'infer') {
    const rows = db.prepare(`
      SELECT user_id, peer_id AS group_id, time, text, CAST(message_id AS TEXT) AS message_id, nickname, card,
             ${includeMedia ? MEDIA_SELECT : 'NULL AS images'}
      FROM messages m
      WHERE scene IN ('group','private')
        AND user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
      ORDER BY time ASC`).all();
    const counts = new Map();
    const lines = [];
    let total = 0;
    for (const r of rows) {
      const n = (counts.get(r.user_id) ?? 0) + 1;
      counts.set(r.user_id, n);
      if (n < minPerUser) continue;
      if (n > maxPerUser) continue;
      lines.push(JSON.stringify(buildRow(r)));
      total++;
    }
    writeFileSync(out, lines.join('\n') + (lines.length ? '\n' : ''), 'utf8');
    log.info(`导出 infer: ${out}（${total} 行）`);

  } else {
    const rows = db.prepare(`
      SELECT m.time, m.peer_id AS group_id, m.group_name, m.user_id, m.nickname, m.card, m.text, l.gender
      FROM messages m
      LEFT JOIN speaker_labels l ON l.user_id = m.user_id
      ORDER BY m.time ASC`).all();
    const lines = [];
    let total = 0;
    if (format === 'csv') {
      lines.push('time,group_id,group_name,user_id,nickname,card,gender,text');
      for (const r of rows) {
        const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
        lines.push([r.time, r.group_id, esc(r.group_name), r.user_id, esc(r.nickname), esc(r.card), esc(r.gender), esc(r.text)].join(','));
        total++;
      }
    } else {
      for (const r of rows) {
        lines.push(JSON.stringify({
          time: r.time, group_id: r.group_id, user_id: r.user_id,
          nickname: r.nickname, card: r.card, text: r.text, label: r.gender ?? null,
        }));
        total++;
      }
    }
    writeFileSync(out, lines.join('\n') + (lines.length ? '\n' : ''), 'utf8');
    log.info(`导出 all: ${out}（${total} 行）`);
  }

  db.close();
  process.exit(0);
}

main().catch((e) => { log.error(`导出失败: ${e.message}`); db.close(); process.exit(1); });
