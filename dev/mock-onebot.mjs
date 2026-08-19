/**
 * mock-onebot.mjs — 本地模拟 OneBot 11 协议端（开发/验证用，不需要真实 QQ）
 *
 * 模拟内容：
 *  - WS :3001：连接后推 1 条 lifecycle + 2 条实时群消息（含图片段）
 *  - HTTP :3000：get_group_msg_history（60 条假历史）/ get_group_info / send_group_msg / 图片下载
 *
 * 用法：node dev/mock-onebot.mjs
 * 然后另开终端运行采集服务（QQBOT_CONFIG 指向测试配置），可完整验证
 * 实时采集 → 历史回填 → 媒体下载 → 上下文快照 → 导出 全链路。
 */
import http from 'node:http';
import { WebSocketServer } from 'ws';

const GROUP_ID = 826904606;
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);

// 60 条假历史（3 个发言人轮换，seq 1..60，2026-01-01 起每 10 分钟一条）
const users = [
  { user_id: 2633083674, nickname: '猛男一号', card: '' },
  { user_id: 185327596, nickname: '萌妹一号', card: '小仙女' },
  { user_id: 2392304699, nickname: '路人甲', card: null },
];
const HISTORY = [];
for (let seq = 1; seq <= 60; seq++) {
  const u = users[seq % 3];
  const m = {
    message_id: 900000 + seq,
    message_seq: seq,
    sender: { user_id: u.user_id, nickname: u.nickname, card: u.card ?? '', role: 'member' },
    time: 1767225600 + seq * 600,
    message: [{ type: 'text', data: { text: `历史消息${seq} ${seq % 2 ? '哈哈哈' : '今天吃了吗'}` } }],
  };
  if (seq === 30) m.message.push({ type: 'image', data: { url: 'http://127.0.0.1:3000/img/1.png', file: '1.png' } });
  HISTORY.push(m);
}
HISTORY.sort((a, b) => b.message_seq - a.message_seq);

http.createServer((req, res) => {
  if (req.url.startsWith('/img/')) {
    res.writeHead(200, { 'Content-Type': 'image/png' });
    res.end(PNG);
    return;
  }
  let body = '';
  req.on('data', (c) => (body += c));
  req.on('end', () => {
    let b = {};
    try { b = body ? JSON.parse(body) : {}; } catch { /* ignore */ }
    if (req.url.includes('get_group_msg_history')) {
      const count = b.count ?? 20;
      const anchor = b.message_seq ?? Infinity;
      const page = HISTORY.filter((m) => m.message_seq < anchor).slice(0, count);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', retcode: 0, data: { messages: page } }));
    } else if (req.url.includes('get_group_info')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', retcode: 0, data: { group_id: b.group_id, group_name: '⑩犹格索托斯的庭院群', member_count: 17 } }));
    } else if (req.url.includes('send_group_msg')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', retcode: 0, data: { message_id: 1 } }));
    } else {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'failed', retcode: -1, message: 'unknown api' }));
    }
  });
}).listen(3000, '127.0.0.1', () => console.log('[mock] HTTP :3000 就绪'));

const wss = new WebSocketServer({ port: 3001, host: '127.0.0.1' }, () => console.log('[mock] WS :3001 就绪'));
wss.on('connection', (ws) => {
  console.log('[mock] 采集服务已连接，推送事件...');
  ws.send(JSON.stringify({ post_type: 'meta_event', meta_event_type: 'lifecycle', self_id: 10001, sub_type: 'connect' }));
  setTimeout(() => ws.send(JSON.stringify({
    post_type: 'message', message_type: 'group', sub_type: 'normal', time: Math.floor(Date.now() / 1000),
    self_id: 10001, message_id: 888001, group_id: GROUP_ID, user_id: 185327596,
    message: [{ type: 'text', data: { text: '实时消息：蹲蹲，有瓜吗' } }],
    sender: { user_id: 185327596, nickname: '萌妹一号', card: '小仙女', role: 'member' },
  })), 300);
  setTimeout(() => ws.send(JSON.stringify({
    post_type: 'message', message_type: 'group', sub_type: 'normal', time: Math.floor(Date.now() / 1000),
    self_id: 10001, message_id: 888002, group_id: GROUP_ID, user_id: 2633083674,
    message: [
      { type: 'text', data: { text: '实时消息：兄弟萌早' } },
      { type: 'image', data: { url: 'http://127.0.0.1:3000/img/1.png', file: '2.png' } },
    ],
    sender: { user_id: 2633083674, nickname: '猛男一号', card: '', role: 'member' },
  })), 500);
});

console.log('[mock] MOCK READY（Ctrl+C 退出）');
