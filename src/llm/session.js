/**
 * llm/session.js — 会话存储（借鉴 harness「会话=追加日志」思想，等比例缩小）
 *
 * data/chat.db 三张表：
 *   sessions  会话注册表（peer → 多代会话，/reset 即开新代，旧日志保留可审计）
 *   messages  追加式消息日志（模型可见的每一条都落库——model-visible means logged）
 *   usage     token 计量表（按天，供日预算控制）
 */
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

export function openChatDb(file) {
  mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA journal_mode = WAL;');
  db.exec('PRAGMA busy_timeout = 10000;');
  db.exec(`
    CREATE TABLE IF NOT EXISTS sessions (
      id         TEXT PRIMARY KEY,   -- qq:private:<uid>#<gen>
      peer       TEXT NOT NULL,
      generation INTEGER NOT NULL,
      model      TEXT,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id      TEXT NOT NULL,
      role            TEXT NOT NULL,           -- user / assistant / tool / system
      content         TEXT NOT NULL DEFAULT '',
      tool_calls_json TEXT,
      tool_call_id    TEXT,
      ts              INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_chat_msg ON messages(session_id, id);
    CREATE TABLE IF NOT EXISTS usage (
      day               TEXT PRIMARY KEY,      -- YYYY-MM-DD（本地时区）
      calls             INTEGER DEFAULT 0,
      prompt_tokens     INTEGER DEFAULT 0,
      completion_tokens INTEGER DEFAULT 0
    );
  `);
  return db;
}

/** 取 peer 的当前会话，没有则创建（generation 递增） */
export function activeSession(db, peer, defaultModel) {
  let row = db.prepare(
    'SELECT id, model FROM sessions WHERE peer=? ORDER BY generation DESC LIMIT 1').get(peer);
  if (!row) {
    const gen = 1;
    const id = `${peer}#${gen}`;
    db.prepare('INSERT INTO sessions (id, peer, generation, model, created_at) VALUES (?,?,?,?,?)')
      .run(id, peer, gen, defaultModel, Date.now());
    return { id, model: defaultModel, fresh: true };
  }
  return { id: row.id, model: row.model || defaultModel, fresh: false };
}

/** /reset：开新代（旧代日志保留） */
export function resetSession(db, peer, defaultModel) {
  const max = db.prepare('SELECT COALESCE(MAX(generation),0) g FROM sessions WHERE peer=?').get(peer).g;
  const id = `${peer}#${max + 1}`;
  db.prepare('INSERT INTO sessions (id, peer, generation, model, created_at) VALUES (?,?,?,?,?)')
    .run(id, peer, max + 1, defaultModel, Date.now());
  return { id, model: defaultModel };
}

export function setSessionModel(db, peer, model) {
  const row = db.prepare('SELECT id FROM sessions WHERE peer=? ORDER BY generation DESC LIMIT 1').get(peer);
  if (!row) throw new Error('会话不存在');
  db.prepare('UPDATE sessions SET model=? WHERE id=?').run(model, row.id);
}

/** 追加一条模型可见消息（永不 UPDATE/DELETE —— 只追加日志） */
export function appendMessage(db, sessionId, { role, content = '', tool_calls = null, tool_call_id = null }) {
  db.prepare(
    'INSERT INTO messages (session_id, role, content, tool_calls_json, tool_call_id, ts) VALUES (?,?,?,?,?,?)')
    .run(sessionId, role, content ?? '',
      tool_calls ? JSON.stringify(tool_calls) : null, tool_call_id, Date.now());
}

/**
 * 模型历史窗口：最近 limit 条，锚定到第一条 user（保证 assistant/tool 配对完整、
 * 首条必是 user）。返回 OpenAI messages 形态。
 */
export function windowMessages(db, sessionId, limit) {
  const rows = db.prepare(
    'SELECT role, content, tool_calls_json, tool_call_id FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?')
    .all(sessionId, limit);
  rows.reverse();
  const start = rows.findIndex((r) => r.role === 'user');
  if (start < 0) return [];
  return rows.slice(start).map((r) => {
    if (r.role === 'assistant' && r.tool_calls_json) {
      return { role: 'assistant', content: r.content || '', tool_calls: JSON.parse(r.tool_calls_json) };
    }
    if (r.role === 'tool') return { role: 'tool', tool_call_id: r.tool_call_id, content: r.content };
    return { role: r.role, content: r.content };
  });
}

export function todayKey() {
  // 本地时区 YYYY-MM-DD
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function addUsage(db, usage) {
  if (!usage) return;
  db.prepare(`
    INSERT INTO usage (day, calls, prompt_tokens, completion_tokens) VALUES (?,?,?,?)
    ON CONFLICT(day) DO UPDATE SET calls=calls+1,
      prompt_tokens=prompt_tokens+excluded.prompt_tokens,
      completion_tokens=completion_tokens+excluded.completion_tokens`)
    .run(todayKey(), 1, usage.prompt_tokens ?? 0, usage.completion_tokens ?? 0);
}

export function usageToday(db) {
  const r = db.prepare('SELECT calls, prompt_tokens, completion_tokens FROM usage WHERE day=?')
    .get(todayKey());
  return {
    calls: r?.calls ?? 0,
    prompt_tokens: r?.prompt_tokens ?? 0,
    completion_tokens: r?.completion_tokens ?? 0,
    total_tokens: (r?.prompt_tokens ?? 0) + (r?.completion_tokens ?? 0),
  };
}
