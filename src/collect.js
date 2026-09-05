/**
 * collect.js — 实时事件规范化与入库
 */
import { saveMessage, trackNewestSeq } from './db.js';
import { cqToText } from './utils.js';
import { shouldExclude } from './filter.js';

/** OneBot 11 事件 → 标准化消息记录（或 null 表示忽略） */
export function normalizeEvent(ev) {
  if (ev.post_type !== 'message') return null;
  if (ev.message_type !== 'group' && ev.message_type !== 'private') return null;

  const scene = ev.message_type === 'group' ? 'group' : 'private';
  const peerId = ev.group_id ?? ev.user_id;
  if (peerId == null) return null;

  return {
    scene,
    peer_id: peerId,
    message_id: ev.message_id ?? null,
    message_seq: null,               // 实时事件不含 seq（回填时才有）
    group_name: null,                // 由调用方补充缓存群名
    user_id: ev.user_id,
    nickname: ev.sender?.nickname ?? null,
    card: ev.sender?.card ?? null,
    role: ev.sender?.role ?? null,
    time: ev.time ?? Math.floor(Date.now() / 1000),
    text: cqToText(ev.message),
    raw_json: JSON.stringify(ev),
    source: 'live',
    segments: ev.message ?? [],      // 内存用：供媒体采集提取图片/表情包
  };
}

/**
 * 处理一条实时事件。
 * @param {function(number): string|null} getGroupNameSync 同步群名查找（缓存命中返回名字，未命中返回 null）
 * @returns {{result:'inserted'|'dup'|'skipped', record?:object}}
 */
export function handleLiveEvent(db, config, ev, getGroupNameSync) {
  const rec = normalizeEvent(ev);
  if (!rec) return { result: 'skipped' };

  const { groups, friends, ignoreSelf } = config.collect;
  if (rec.scene === 'group' && groups.length > 0 && !groups.includes(rec.peer_id)) return { result: 'skipped' };
  if (rec.scene === 'private' && friends.length > 0 && !friends.includes(rec.peer_id)) return { result: 'skipped' };

  // 统一过滤：机器人自己 + 指令消息 + 空文本（ignoreSelf 已并入）
  const selfId = ev.self_id ?? null;
  if (shouldExclude(rec, { selfId })) return { result: 'skipped' };

  if (rec.scene === 'group' && getGroupNameSync) {
    rec.group_name = getGroupNameSync(rec.peer_id) ?? null;
  }
  const result = saveMessage(db, rec);
  if (result === 'inserted' && ev.message_seq != null) {
    trackNewestSeq(db, rec.scene, rec.peer_id, ev.message_seq);
  }
  return { result, record: rec };
}
