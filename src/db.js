/**
 * db.js — SQLite 存储层（基于 Node 内置 node:sqlite，零原生依赖）
 */
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scene TEXT NOT NULL,
  peer_id INTEGER NOT NULL,
  message_id INTEGER,
  message_seq INTEGER,
  group_name TEXT,
  user_id INTEGER NOT NULL,
  nickname TEXT,
  card TEXT,
  role TEXT,
  time INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  raw_json TEXT,
  source TEXT NOT NULL DEFAULT 'live',
  collected_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_msg ON messages(scene, peer_id, message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_peer_time ON messages(peer_id, time);
CREATE INDEX IF NOT EXISTS idx_user_time ON messages(user_id, time);

CREATE TABLE IF NOT EXISTS speaker_labels (
  user_id INTEGER PRIMARY KEY,
  nickname TEXT,
  gender TEXT,
  label_source TEXT DEFAULT 'manual',
  label_confidence TEXT DEFAULT 'high',
  label_group INTEGER,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS sync_state (
  scene TEXT NOT NULL,
  peer_id INTEGER NOT NULL,
  oldest_seq INTEGER,
  newest_seq INTEGER,
  total_fetched INTEGER DEFAULT 0,
  last_sync_at INTEGER,
  PRIMARY KEY (scene, peer_id)
);

CREATE TABLE IF NOT EXISTS media_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL,
  scene TEXT NOT NULL,
  peer_id INTEGER NOT NULL,
  user_id INTEGER,
  media_type TEXT NOT NULL,
  url TEXT,
  file_id TEXT,
  local_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  time INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_media ON media_files(message_id, media_type, COALESCE(url,''), COALESCE(file_id,''));
CREATE INDEX IF NOT EXISTS idx_media_status ON media_files(status);
CREATE INDEX IF NOT EXISTS idx_media_user ON media_files(user_id, media_type);

CREATE TABLE IF NOT EXISTS context_exports (
  message_id INTEGER PRIMARY KEY,
  user_id INTEGER,
  written_at INTEGER
);

CREATE TABLE IF NOT EXISTS user_profiles (
  user_id INTEGER PRIMARY KEY,
  nickname TEXT,
  first_seen INTEGER,
  last_seen INTEGER,
  message_count INTEGER DEFAULT 0,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS forwards (
  forward_id TEXT PRIMARY KEY,
  envelope_user INTEGER,
  envelope_time INTEGER,
  content_raw TEXT,
  fetched_at INTEGER
);
`;

export function openDb(file) {
  if (file !== ':memory:') mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA journal_mode = WAL;');
  db.exec('PRAGMA synchronous = NORMAL;');
  db.exec('PRAGMA busy_timeout = 15000;');   // 多进程并发写时等待锁（默认 0 会立即报 database is locked）
  db.exec(SCHEMA);
  // 旧库迁移：补充 label_confidence / label_group 列
  const cols = db.prepare('PRAGMA table_info(speaker_labels)').all();
  if (!cols.some((c) => c.name === 'label_confidence')) {
    db.exec(`ALTER TABLE speaker_labels ADD COLUMN label_confidence TEXT DEFAULT 'high'`);
  }
  if (!cols.some((c) => c.name === 'label_group')) {
    db.exec(`ALTER TABLE speaker_labels ADD COLUMN label_group INTEGER`);
  }
  // 旧库一次性重建用户档案（新库无消息则跳过）
  const hasProfiles = db.prepare('SELECT COUNT(*) c FROM user_profiles').get().c;
  if (hasProfiles === 0) {
    const hasMsgs = db.prepare('SELECT COUNT(*) c FROM messages').get().c;
    if (hasMsgs > 0) {
      db.exec(`
        INSERT INTO user_profiles (user_id, nickname, first_seen, last_seen, message_count, updated_at)
        SELECT user_id,
          (SELECT nickname FROM messages m2 WHERE m2.user_id = m.user_id ORDER BY time DESC LIMIT 1),
          MIN(time), MAX(time), COUNT(*), 0
        FROM messages m GROUP BY user_id
        ON CONFLICT(user_id) DO NOTHING`);
    }
  }
  return db;
}

const INSERT_MSG = `
INSERT OR IGNORE INTO messages
  (scene, peer_id, message_id, message_seq, group_name, user_id, nickname, card, role, time, text, raw_json, source, collected_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
`;

const SELECT_MSG_ID = `SELECT id FROM messages WHERE scene=? AND peer_id=? AND message_id=?`;

/**
 * 保存一条消息。返回 'inserted' | 'dup'。
 * 新消息同时更新用户档案（最新昵称按消息时间比较，避免回填旧消息覆盖新昵称）。
 */
export function saveMessage(db, m) {
  const r = db.prepare(INSERT_MSG).run(
    m.scene, m.peer_id, m.message_id ?? null, m.message_seq ?? null, m.group_name ?? null,
    m.user_id, m.nickname ?? null, m.card ?? null, m.role ?? null,
    m.time, m.text, m.raw_json ?? null, m.source, Math.floor(Date.now() / 1000),
  );
  if (r.changes > 0) {
    db.prepare(`
      INSERT INTO user_profiles (user_id, nickname, first_seen, last_seen, message_count, updated_at)
      VALUES (?,?,?,?,1,?)
      ON CONFLICT(user_id) DO UPDATE SET
        message_count = message_count + 1,
        nickname = CASE WHEN excluded.first_seen > user_profiles.last_seen THEN excluded.nickname ELSE user_profiles.nickname END,
        first_seen = MIN(user_profiles.first_seen, excluded.first_seen),
        last_seen = MAX(user_profiles.last_seen, excluded.first_seen),
        updated_at = excluded.updated_at
    `).run(m.user_id, m.nickname ?? null, m.time, m.time, Math.floor(Date.now() / 1000));
    return 'inserted';
  }
  return 'dup';
}

/** 用户档案：最新全局昵称、活跃区间、发言数 */
export function getUserProfile(db, userId) {
  return db.prepare('SELECT * FROM user_profiles WHERE user_id=?').get(userId) ?? null;
}

export function hasMessage(db, scene, peerId, messageId) {
  return db.prepare(SELECT_MSG_ID).get(scene, peerId, messageId) !== undefined;
}

// ---------- sync_state ----------
export function getState(db, scene, peerId) {
  return db.prepare('SELECT * FROM sync_state WHERE scene=? AND peer_id=?').get(scene, peerId) ?? null;
}

export function setState(db, scene, peerId, { oldestSeq, newestSeq, fetchedDelta = 0 }) {
  const cur = getState(db, scene, peerId) ?? { oldest_seq: null, newest_seq: null, total_fetched: 0 };
  const next = {
    oldest_seq: oldestSeq ?? cur.oldest_seq,
    newest_seq: newestSeq ?? cur.newest_seq,
    total_fetched: (cur.total_fetched ?? 0) + fetchedDelta,
    last_sync_at: Math.floor(Date.now() / 1000),
  };
  db.prepare(`
    INSERT INTO sync_state (scene, peer_id, oldest_seq, newest_seq, total_fetched, last_sync_at)
    VALUES (?,?,?,?,?,?)
    ON CONFLICT(scene, peer_id) DO UPDATE SET
      oldest_seq=excluded.oldest_seq, newest_seq=excluded.newest_seq,
      total_fetched=excluded.total_fetched, last_sync_at=excluded.last_sync_at
  `).run(scene, peerId, next.oldest_seq, next.newest_seq, next.total_fetched, next.last_sync_at);
  return next;
}

/** 更新实时消息的最新 seq（用于 gapfill 判断） */
export function trackNewestSeq(db, scene, peerId, seq) {
  const cur = getState(db, scene, peerId);
  if (seq == null) return;
  if (cur?.newest_seq == null || seq > cur.newest_seq) setState(db, scene, peerId, { newestSeq: seq });
}

// ---------- media_files ----------
const INSERT_MEDIA = `
INSERT OR IGNORE INTO media_files (message_id, scene, peer_id, user_id, media_type, url, file_id, status, time)
VALUES (?,?,?,?,?,?,?,?,?)
`;

export function insertMedia(db, m) {
  const r = db.prepare(INSERT_MEDIA).run(
    m.message_id, m.scene, m.peer_id, m.user_id ?? null,
    m.media_type, m.url ?? null, m.file_id ?? null,
    m.status ?? 'pending', m.time ?? Math.floor(Date.now() / 1000),
  );
  return r.changes > 0 ? 'inserted' : 'dup';
}

export function listPendingMedia(db, limit = 100) {
  return db.prepare('SELECT * FROM media_files WHERE status=? LIMIT ?').all('pending', limit);
}

export function listFailedMedia(db, limit = 100) {
  return db.prepare('SELECT * FROM media_files WHERE status=? LIMIT ?').all('failed', limit);
}

export function setMediaStatus(db, id, status, localPath = null) {
  if (localPath != null) {
    db.prepare('UPDATE media_files SET status=?, local_path=? WHERE id=?').run(status, localPath, id);
  } else {
    db.prepare('UPDATE media_files SET status=? WHERE id=?').run(status, id);
  }
}

export function resetFailedMedia(db) {
  return db.prepare('UPDATE media_files SET status=? WHERE status=? RETURNING *').all('pending', 'failed');
}

// ---------- context（指定用户发言上下文） ----------
const CTX_ROW = 'SELECT id, message_id, user_id, nickname, card, text, time FROM messages';

/** 幂等标记：该中心消息的上下文是否已写过快照 */
export function markContextWritten(db, messageId, userId) {
  return db.prepare('INSERT OR IGNORE INTO context_exports (message_id, user_id, written_at) VALUES (?,?,?)')
    .run(messageId, userId, Math.floor(Date.now() / 1000)).changes > 0;
}

/**
 * 取某条中心消息在群内的上下文（前 window 条 + 自己 + 后 window 条，按到达序）
 * 用自增 id 作为"到达顺序"代理（实时与回填入库顺序均按时间递增，足够可靠）
 */
export function getContext(db, peerId, centerMessageId, window = 5) {
  const center = db.prepare(`${CTX_ROW} WHERE message_id=? AND peer_id=?`).get(centerMessageId, peerId);
  if (!center) return null;
  const before = db.prepare(`${CTX_ROW} WHERE peer_id=? AND id<? ORDER BY id DESC LIMIT ?`)
    .all(peerId, center.id, window).reverse();
  const after = db.prepare(`${CTX_ROW} WHERE peer_id=? AND id>? ORDER BY id ASC LIMIT ?`)
    .all(peerId, center.id, window);
  return { center, before, after };
}

// ---------- forwards（合并转发） ----------
export function saveForward(db, forwardId, envelopeUser, envelopeTime, contentRaw) {
  return db.prepare(`
    INSERT OR IGNORE INTO forwards (forward_id, envelope_user, envelope_time, content_raw, fetched_at)
    VALUES (?,?,?,?,?)`).run(
    String(forwardId), envelopeUser ?? null, envelopeTime ?? null,
    contentRaw, Math.floor(Date.now() / 1000),
  ).changes > 0;
}

export function hasForward(db, forwardId) {
  return db.prepare('SELECT 1 FROM forwards WHERE forward_id=?').get(String(forwardId)) !== undefined;
}

// ---------- speaker_labels ----------
export function setLabel(db, userId, gender, nickname = null, source = 'manual', confidence = 'high', group = null) {
  db.prepare(`
    INSERT INTO speaker_labels (user_id, nickname, gender, label_source, label_confidence, label_group, updated_at)
    VALUES (?,?,?,?,?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
      nickname=COALESCE(excluded.nickname, nickname),
      gender=excluded.gender, label_source=excluded.label_source,
      label_confidence=excluded.label_confidence,
      label_group=COALESCE(excluded.label_group, label_group),
      updated_at=excluded.updated_at
  `).run(userId, nickname, gender, source, confidence, group, Math.floor(Date.now() / 1000));
}

export function listLabels(db) {
  return db.prepare('SELECT * FROM speaker_labels ORDER BY user_id').all();
}

// ---------- 统计 ----------
export function stats(db) {
  const total = db.prepare('SELECT COUNT(*) c FROM messages').get().c;
  const byGroup = db.prepare(`
    SELECT scene, peer_id, group_name, COUNT(*) c, MIN(time) min_t, MAX(time) max_t
    FROM messages WHERE scene='group' GROUP BY peer_id ORDER BY c DESC`).all();
  const byUser = db.prepare(`
    SELECT m.user_id, COALESCE(p.nickname, MAX(m.nickname)) nickname, COUNT(*) c
    FROM messages m LEFT JOIN user_profiles p ON p.user_id = m.user_id
    GROUP BY m.user_id ORDER BY c DESC LIMIT 50`).all();
  const labelCoverage = db.prepare(`
    SELECT l.gender, COUNT(DISTINCT m.user_id) users, COUNT(m.id) msgs
    FROM speaker_labels l LEFT JOIN messages m ON m.user_id = l.user_id
    GROUP BY l.gender`).all();
  const unlabeledUsers = db.prepare(`
    SELECT COUNT(DISTINCT user_id) c FROM messages
    WHERE user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))`).get().c;
  return { total, byGroup, byUser, labelCoverage, unlabeledUsers };
}

/** 标签覆盖情况（用于标注后的自动化反馈） */
export function labelCoverageStats(db) {
  const totalUsers = db.prepare(`SELECT COUNT(DISTINCT user_id) c FROM messages WHERE scene='group'`).get().c;
  const labeledUsers = db.prepare(`SELECT COUNT(*) c FROM speaker_labels WHERE gender IN ('male','female')`).get().c;
  const labeledMsgs = db.prepare(`
    SELECT COUNT(*) c FROM messages m
    JOIN speaker_labels l ON l.user_id = m.user_id
    WHERE m.scene='group' AND l.gender IN ('male','female')`).get().c;
  const totalMsgs = db.prepare(`SELECT COUNT(*) c FROM messages WHERE scene='group'`).get().c;
  return { totalUsers, labeledUsers, labeledMsgs, totalMsgs };
}

/** 未标注的活跃用户（值得优先标注的人） */
export function topUnlabeledUsers(db, n = 20) {
  return db.prepare(`
    SELECT m.user_id, COALESCE(p.nickname, MAX(m.nickname)) nickname, COUNT(*) c
    FROM messages m LEFT JOIN user_profiles p ON p.user_id = m.user_id
    WHERE m.scene='group' AND m.user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
    GROUP BY m.user_id ORDER BY c DESC LIMIT ?`).all(n);
}

/** 标签版本信息（供训练流水线判断是否需要重训） */
export function labelMeta(db) {
  const byGender = db.prepare(`
    SELECT gender, COUNT(*) users FROM speaker_labels
    WHERE gender IN ('male','female') GROUP BY gender`).all();
  const byConfidence = db.prepare(`
    SELECT label_confidence, COUNT(*) users FROM speaker_labels
    WHERE gender IN ('male','female') GROUP BY label_confidence`).all();
  const maxUpdated = db.prepare(`SELECT MAX(updated_at) t FROM speaker_labels WHERE gender IN ('male','female')`).get().t;
  return { byGender, byConfidence, max_label_updated_at: maxUpdated ?? null };
}
