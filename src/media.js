/**
 * media.js — 聊天图片 / 表情包采集
 *
 *  - 从 CQ 消息段提取媒体：image（聊天图片）、market_face（市场表情包）、face（QQ 表情，仅记录元数据）
 *  - 入库 media_files 表，串行限速下载到 data/media/<peer_id>/<md5>.<ext>
 *  - 按 URL/file_id 去重；下载失败标 failed，可由调度器重试
 *
 * 用途：为"性别标定器"提供多模态特征（表情包使用风格与性别相关）。
 */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { insertMedia, setMediaStatus, listPendingMedia, resetFailedMedia } from './db.js';

const EXT_BY_MIME = {
  'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif',
  'image/webp': 'webp', 'image/bmp': 'bmp', 'image/x-icon': 'ico',
};

function extFromUrl(url, contentType = '') {
  if (EXT_BY_MIME[contentType]) return EXT_BY_MIME[contentType];
  const m = /\.(jpe?g|png|gif|webp|bmp)(?:[?#]|$)/i.exec(url ?? '');
  return m ? m[1].toLowerCase() : 'jpg';
}

/** 从消息段列表提取媒体描述（仅保留配置开启的类型） */
export function extractMediaSegments(segments = [], cfg) {
  const types = new Set(cfg?.types ?? ['image', 'market_face']);
  const out = [];
  for (const s of segments) {
    if (s.type === 'image' && types.has('image')) {
      out.push({ media_type: 'image', url: s.data?.url ?? null, file_id: s.data?.file ?? null, downloadable: !!s.data?.url });
    } else if (s.type === 'market_face' && types.has('market_face')) {
      out.push({ media_type: 'market_face', url: s.data?.url ?? null, file_id: s.data?.key ?? null, downloadable: !!s.data?.url });
    } else if (s.type === 'face') {
      // QQ 基础表情无直链，仅记录使用元数据（表情包使用风格特征）
      out.push({ media_type: 'face', url: null, file_id: `face:${s.data?.id ?? ''}`, downloadable: false });
    }
  }
  return out;
}

export class MediaDownloader {
  constructor(db, config, log) {
    this.db = db;
    this.cfg = config.collect?.media ?? { enabled: false };
    this.log = log;
    this.dir = path.resolve(this.cfg.dir ?? 'data/media');
    this.queue = [];
    this.busy = false;
    this.stopped = false;
    this.queueOverflowWarned = false;
  }

  /** 一条消息入库后调用：登记媒体并排队下载 */
  enqueue(record, segments) {
    if (!this.cfg.enabled || !segments?.length) return;
    const items = extractMediaSegments(segments, this.cfg);
    for (const it of items) {
      insertMedia(this.db, {
        message_id: record.message_id,
        scene: record.scene,
        peer_id: record.peer_id,
        user_id: record.user_id,
        media_type: it.media_type,
        url: it.url,
        file_id: it.file_id,
        status: it.downloadable ? 'pending' : 'recorded',   // 无直链的仅记录
        time: record.time,
      });
      if (it.downloadable) {
        if (this.queue.length > 5000) {
          if (!this.queueOverflowWarned) {
            this.log.warn('[media] 下载队列超过 5000，暂停入队（已下载完的会继续）');
            this.queueOverflowWarned = true;
          }
          continue;
        }
        this.queue.push({ message_id: record.message_id, peer_id: record.peer_id, media_type: it.media_type, url: it.url });
      }
    }
    this.#pump();
  }

  async #pump() {
    if (this.busy || this.stopped) return;
    this.busy = true;
    try {
      while (this.queue.length) {
        if (this.stopped) break;
        const item = this.queue.shift();
        await this.#download(item);
        const delay = this.cfg.delayMs ?? 1000;
        if (delay > 0 && this.queue.length) await new Promise((r) => setTimeout(r, delay));
      }
    } finally {
      this.busy = false;
    }
  }

  async #download(item) {
    try {
      const res = await fetch(item.url, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      if (!buf.length) throw new Error('empty body');
      const ext = extFromUrl(item.url, res.headers.get('content-type') ?? '');
      const name = `${createHash('md5').update(item.url).digest('hex')}.${ext}`;
      const dir = path.join(this.dir, String(item.peer_id));
      mkdirSync(dir, { recursive: true });
      const file = path.join(dir, name);
      writeFileSync(file, buf);
      // 找到对应 media_files 行并标记完成
      const row = this.db.prepare(
        `SELECT id FROM media_files WHERE message_id=? AND media_type=? AND url=?`
      ).get(item.message_id, item.media_type, item.url);
      if (row) setMediaStatus(this.db, row.id, 'downloaded', file);
    } catch (e) {
      const row = this.db.prepare(
        `SELECT id FROM media_files WHERE message_id=? AND media_type=? AND url=?`
      ).get(item.message_id, item.media_type, item.url);
      if (row) setMediaStatus(this.db, row.id, 'failed');
      this.log.debug(`[media] 下载失败: ${item.url?.slice(0, 60)} (${e.message})`);
    }
  }

  /** 重试历史失败项（调度器/启动时调用） */
  retryFailed() {
    const rows = resetFailedMedia(this.db);
    for (const r of rows) {
      if (r.url && this.queue.length <= 5000) {
        this.queue.push({ message_id: r.message_id, peer_id: r.peer_id, media_type: r.media_type, url: r.url });
      }
    }
    if (rows.length) this.log.info(`[media] ${rows.length} 个失败项重新入队下载`);
    this.#pump();
  }

  /** 把 pending（上次进程崩溃遗留）重新入队 */
  requeuePending() {
    const rows = listPendingMedia(this.db, 5000);
    for (const r of rows) {
      if (r.url) this.queue.push({ message_id: r.message_id, peer_id: r.peer_id, media_type: r.media_type, url: r.url });
    }
    if (rows.length) this.log.info(`[media] 恢复 ${rows.length} 个待下载项`);
    this.#pump();
  }

  stop() { this.stopped = true; }
}
