// 诊断：登录状态 + 进程（短超时）
import { createHash } from 'node:crypto';
const BASE = 'http://127.0.0.1:6099';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  const hash = createHash('sha256').update('a971c0e9ff47.napcat').digest('hex');
  const login = await (await fetch(BASE + '/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hash, totpCode: '' }),
    signal: AbortSignal.timeout(10000),
  })).json();
  const H = { 'Content-Type': 'application/json', Authorization: `Bearer ${login.data.Credential}` };
  const st = await (await fetch(BASE + '/api/QQLogin/CheckLoginStatus', {
    method: 'POST', headers: H, body: '{}', signal: AbortSignal.timeout(10000),
  })).json();
  console.log('登录状态:', JSON.stringify(st.data));
  const ql = await (await fetch(BASE + '/api/QQLogin/GetQuickLoginList', { headers: H, signal: AbortSignal.timeout(10000) })).json();
  console.log('快速登录列表:', JSON.stringify(ql.data));
  if (!st.data?.isLogin && ql.data?.length) {
    console.log('尝试快速登录...');
    const r = await (await fetch(BASE + '/api/QQLogin/SetQuickLogin', {
      method: 'POST', headers: H, body: JSON.stringify({ uin: String(ql.data[0]) }),
      signal: AbortSignal.timeout(15000),
    })).json();
    console.log('结果:', JSON.stringify(r));
    await sleep(12000);
    const st2 = await (await fetch(BASE + '/api/QQLogin/CheckLoginStatus', {
      method: 'POST', headers: H, body: '{}', signal: AbortSignal.timeout(10000),
    })).json();
    console.log('二次检查:', JSON.stringify(st2.data));
  }
} catch (e) {
  console.log('ERR:', e.message);
}
