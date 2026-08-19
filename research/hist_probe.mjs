// URI 打开群后，检查历史接口数据量是否增长
const HTTP = 'http://127.0.0.1:3000';
const r = await fetch(`${HTTP}/get_group_msg_history`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ group_id: 826904606, count: 200 }),
});
const j = await r.json();
const msgs = j.data?.messages ?? [];
const times = msgs.map((m) => m.time ?? 0);
console.log('消息数:', msgs.length);
console.log('时间范围:', times.length ? `${new Date(Math.min(...times) * 1000).toLocaleString('zh-CN')} → ${new Date(Math.max(...times) * 1000).toLocaleString('zh-CN')}` : '空');
