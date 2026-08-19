// api_health.mjs — 探测 NapCat 各 API 健康状况
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger('info');
const bot = new OneBotClient(config.onebot, log);

async function tryApi(name, fn, timeout) {
  const t0 = Date.now();
  try {
    const r = await fn(timeout);
    console.log(`[OK]   ${name} (${Date.now() - t0}ms) ->`, JSON.stringify(r).slice(0, 200));
  } catch (e) {
    console.log(`[FAIL] ${name} (${Date.now() - t0}ms) -> ${e.message}`);
  }
}

await tryApi('get_login_info', (t) => bot.callApi('get_login_info', {}, t), 30000);
await tryApi('get_friend_list', () => bot.getFriendList(), 30000);
await tryApi('群历史 826904606 (5条)', (t) => bot.fetchHistoryPage(826904606, { count: 5 }), 45000);
await tryApi('私聊历史 2633083674 (20条)', (t) => bot.fetchPrivateHistoryPage(2633083674, { count: 20 }), 45000);
await tryApi('私聊历史 1094950020 (5条)', (t) => bot.fetchPrivateHistoryPage(1094950020, { count: 5 }), 45000);
console.log('done');
process.exit(0);
