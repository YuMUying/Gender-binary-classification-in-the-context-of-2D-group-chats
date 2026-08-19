// 检查 NapCat 状态并拉取 2633083674 的私聊历史
const HTTP = 'http://127.0.0.1:3000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(name, body) {
  try {
    const r = await fetch(`${HTTP}/${name}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const j = await r.json();
    return { ok: r.status === 200 && j.status === 'ok', j };
  } catch (e) { return { ok: false, j: { err: e.message } }; }
}

// 1) 健康检查
const h = await api('get_login_info', {});
console.log('NapCat 状态:', h.ok ? `在线 uin=${h.j.data?.user_id}` : JSON.stringify(h.j).slice(0, 120));
if (!h.ok) { console.log('NapCat 未运行，需要先重启'); process.exit(0); }

// 2) 私聊历史（从最新开始）
const hist = await api('get_friend_msg_history', { user_id: 2633083674, count: 30 });
if (!hist.ok) { console.log('私聊历史失败:', JSON.stringify(hist.j).slice(0, 200)); process.exit(1); }
const msgs = hist.j.data?.messages ?? [];
console.log('\n私聊历史条数:', msgs.length);
let fwdIds = [];
for (const m of msgs) {
  const t = new Date((m.time ?? 0) * 1000).toLocaleString('zh-CN');
  const fwds = (m.message ?? []).filter((s) => s.type === 'forward');
  const text = (m.message ?? []).map((s) => s.type === 'text' ? s.data?.text : `[${s.type}]`).join('').slice(0, 40);
  console.log(`  [${t}] ${text}`);
  for (const f of fwds) {
    console.log(`    → forward 段: id=${f.data?.id}`);
    fwdIds.push(f.data?.id);
  }
}

// 3) 读取合并转发内容
for (const fid of fwdIds) {
  const r = await api('get_forward_msg', { message_id: fid });
  console.log(`\n===== get_forward_msg id=${fid} =====`);
  if (r.ok) {
    console.log(JSON.stringify(r.j.data, null, 2).slice(0, 2500));
  } else {
    console.log('失败:', JSON.stringify(r.j).slice(0, 300));
  }
  await sleep(500);
}
