/**
 * onebot.js — OneBot 11 客户端封装
 *  - WebSocket 正向连接（接收事件）
 *  - HTTP API 调用（get_group_msg_history 等）
 */
import WebSocket from 'ws';

export class OneBotClient {
  constructor({ wsUrl, httpUrl, accessToken = '' }, logger) {
    this.wsUrl = wsUrl;
    this.httpUrl = httpUrl;
    this.accessToken = accessToken;
    this.log = logger;
    this.ws = null;
    this.onEvent = () => {};
    this.onConnect = () => {};
    this.onClose = () => {};
    this._retry = 0;
    this._closed = false;
  }

  /** 建立 WS 连接（自动重连，指数退避） */
  connect() {
    this._closed = false;
    const headers = this.accessToken ? { Authorization: `Bearer ${this.accessToken}` } : {};
    this.log.info(`[onebot] 连接 ${this.wsUrl} ...`);
    const ws = new WebSocket(this.wsUrl, { headers });
    this.ws = ws;

    ws.on('open', () => {
      this._retry = 0;
      this.log.info('[onebot] WebSocket 已连接，实时监听中');
      this.onConnect();
    });

    ws.on('message', (buf) => {
      let ev;
      try { ev = JSON.parse(buf.toString()); } catch { return; }
      if (ev?.post_type) {
        try { this.onEvent(ev); }
        catch (e) { this.log.error(`[onebot] 事件处理异常（已跳过，服务继续）: ${e.message}`); }
      }
    });

    ws.on('close', (code) => {
      if (this._closed) return;
      const wait = Math.min(30000, 1000 * 2 ** this._retry++);
      this.log.warn(`[onebot] 连接关闭 (code=${code})，${Math.round(wait / 1000)}s 后重连`);
      this.onClose();
      setTimeout(() => this.connect(), wait);
    });

    ws.on('error', (e) => { this.log.error(`[onebot] WS error: ${e.message}`); });
  }

  close() {
    this._closed = true;
    try { this.ws?.close(); } catch { /* ignore */ }
  }

  /** HTTP API 调用（默认 90s 超时，避免 NapCat 繁忙时无限挂起） */
  async callApi(apiName, body = {}, timeoutMs = 90000) {
    const res = await fetch(`${this.httpUrl}/${apiName}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(this.accessToken ? { Authorization: `Bearer ${this.accessToken}` } : {}),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    const json = await res.json();
    if (json.status !== 'ok') {
      throw new Error(`API ${apiName} 失败: retcode=${json.retcode} ${json.wording ?? json.msg ?? ''}`);
    }
    return json.data ?? {};
  }

  /** 拉一页历史消息（reverse_order=true：从 message_seq 向更旧翻，不含该 seq 本身） */
  async fetchHistoryPage(groupId, { messageSeq, count }) {
    const body = { group_id: groupId, count, reverse_order: true };
    if (messageSeq !== undefined && messageSeq !== null) body.message_seq = messageSeq;
    const data = await this.callApi('get_group_msg_history', body);
    return data.messages ?? [];
  }

  /** 拉一页好友/个人聊天历史（OneBot 11 get_friend_msg_history；NapCat 同样支持） */
  async fetchPrivateHistoryPage(userId, { messageSeq, count }) {
    const body = { user_id: userId, count, reverse_order: true };
    if (messageSeq !== undefined && messageSeq !== null) body.message_seq = messageSeq;
    const data = await this.callApi('get_friend_msg_history', body);
    return data.messages ?? [];
  }

  /** 好友列表（个人聊天采集配置用） */
  async getFriendList() {
    const data = await this.callApi('get_friend_list', {}, 30000);
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.friend_list)) return data.friend_list;
    if (Array.isArray(data?.friends)) return data.friends;
    return [];
  }

  async getGroupInfo(groupId) {
    try {
      const d = await this.callApi('get_group_info', { group_id: groupId, no_cache: false });
      return { name: d.group_name ?? null, memberCount: d.member_count ?? null };
    } catch { return { name: null, memberCount: null }; }
  }

  /** 群成员是否存在（用户是否在群内） */
  async isGroupMember(groupId, userId) {
    try {
      const d = await this.callApi('get_group_member_info', { group_id: groupId, user_id: userId, no_cache: false }, 20000);
      return !!(d && (d.user_id || d.group_id));
    } catch { return false; }
  }

  sendGroupMessage(groupId, text) {
    return this.callApi('send_group_msg', { group_id: groupId, message: [{ type: 'text', data: { text } }] });
  }
}
