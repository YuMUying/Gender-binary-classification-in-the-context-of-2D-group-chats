/**
 * llm/tools.js — 只读工具注册表（借鉴 harness 的 defineTool + 白名单思想）
 *
 * 原则：
 *  - 模型永远拿不到任意 shell：只允许调用这里注册的固定函数；
 *  - 参数过 schema 校验，execFile 用固定 argv（无 shell 注入面）；
 *  - 单工具超时 + 输出截断；
 *  - 工具失败返回错误文本给模型（模型可向用户解释），不抛出中断会话。
 */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { spawn } from 'node:child_process';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { LLM_ROOT } from './config.js';
const pExec = promisify(execFile);

const readFile = (p) => import('node:fs').then((fs) => fs.readFileSync(p, 'utf8'));

/**
 * @param {object} cfg    llm 配置（tools.units / limits）
 * @param {object} collectorDb  采集主库句柄（node:sqlite, 只读查询）
 * @param {object} chatDb       会话库句柄
 * @param {object} log          logger
 * @param {object} ctx          运行环境 { httpUrl, httpToken, dbFile, selfId, groups, units }
 */
export function buildTools(cfg, collectorDb, chatDb, log, ctx = {}) {
  const lim = cfg.limits;
  const dataDir = path.dirname(ctx.dbFile ?? cfg.database);

  // 采集速率闭包记忆：上次快照（跨工具调用保留）
  let lastSnap = null;

  const truncate = (s) => {
    const max = lim.toolOutputMaxChars;
    return s.length > max ? s.slice(0, max) + `\n...(截断,共${s.length}字)` : s;
  };
  const run = async (cmd, args, timeoutMs = lim.toolTimeoutMs) => {
    const { stdout } = await pExec(cmd, args, { timeout: timeoutMs, windowsHide: true });
    return stdout.trim();
  };

  // ---------- pi_status: 系统与服务总览 ----------
  async function piStatus() {
    const lines = [];
    const [uptime, load, meminfo, disk, temp, throttled, ...units] = await Promise.allSettled([
      run('uptime', ['-p']),
      readFile('/proc/loadavg'),
      readFile('/proc/meminfo'),
      run('df', ['-h', '/']),
      run('vcgencmd', ['measure_temp']),
      run('vcgencmd', ['get_throttled']),
      ...cfg.tools.units.map((u) => run('systemctl', ['is-active', u], 5000).catch(() => 'unknown')),
    ]);
    if (uptime.status === 'fulfilled') lines.push(`运行时长: ${uptime.value}`);
    if (load.status === 'fulfilled') lines.push(`负载: ${load.value.split(' ').slice(0, 3).join(' ')}`);
    if (meminfo.status === 'fulfilled') {
      const get = (k) => Number((meminfo.value.match(new RegExp(`${k}:\\s+(\\d+)`)) ?? [])[1] ?? 0);
      const total = get('MemTotal'), avail = get('MemAvailable');
      if (total) lines.push(`内存: ${((total - avail) / 1048576).toFixed(1)}/${(total / 1048576).toFixed(1)} GB (可用 ${(avail / 1048576).toFixed(1)} GB)`);
    }
    if (disk.status === 'fulfilled') {
      const m = disk.value.split('\n').find((l) => l.includes('/') && !l.includes('Mount'));
      if (m) lines.push(`根盘: ${m.split(/\s+/).slice(-4).join('  ')}`);
    }
    if (temp.status === 'fulfilled') lines.push(`温度: ${temp.value.replace('temp=', '').trim()}`);
    if (throttled.status === 'fulfilled') {
      const hex = (throttled.value.match(/throttled=0x([0-9a-f]+)/i) ?? [])[1];
      lines.push(`电源状态: 0x${hex ?? '?'}${hex === '0' || hex === '0000' ? '（正常）' : '（异常:曾降压/过热/断电）'}`);
    }
    cfg.tools.units.forEach((u, i) => {
      const v = units[i];
      lines.push(`服务 ${u}: ${v.status === 'fulfilled' ? v.value : 'unknown'}`);
    });
    // 采集心跳
    try {
      const r = collectorDb.prepare('SELECT COUNT(*) n, MAX(time) t FROM messages').get();
      const ageMin = r.t ? Math.round((Date.now() / 1000 - r.t) / 60) : -1;
      lines.push(`采集库: ${r.n} 条消息, 最新 ${ageMin < 0 ? '?' : ageMin + ' 分钟前'}`);
    } catch { /* 忽略 */ }
    return lines.join('\n');
  }

  // ---------- pi_logs: 服务日志尾部 ----------
  async function piLogs(args) {
    const unit = String(args.unit ?? '');
    const lines = Math.min(80, Math.max(1, Number(args.lines ?? 20)));
    if (!cfg.tools.units.includes(unit)) return `不允许查询 ${unit}（白名单: ${cfg.tools.units.join(', ')}）`;
    try {
      return truncate(await run('journalctl', ['-u', unit, '-n', String(lines), '--no-pager', '-o', 'cat']));
    } catch (e) {
      return `日志查询失败: ${e.message}`;
    }
  }

  // ---------- collector_db: 采集/会话库统计 ----------
  function collectorDbStats() {
    const out = [];
    try {
      const r = collectorDb.prepare(
        "SELECT COUNT(*) n, SUM(CASE WHEN time >= strftime('%s','now','-1 day') THEN 1 ELSE 0 END) d1 FROM messages").get();
      const latest = collectorDb.prepare('SELECT MAX(time) t FROM messages').get().t;
      out.push(`采集库: 总 ${r.n} 条 / 近24h ${r.d1 ?? 0} 条 / 最新 ${latest ? new Date(latest * 1000).toLocaleString('zh-CN') : '?'}`);
      const media = collectorDb.prepare("SELECT status, COUNT(*) n FROM media_files GROUP BY status").all();
      if (media.length) out.push(`媒体: ${media.map((m) => `${m.status}=${m.n}`).join(' ')}`);
      const labels = collectorDb.prepare('SELECT COUNT(*) n FROM speaker_labels').get().n;
      out.push(`人工标注: ${labels} 条`);
    } catch (e) {
      out.push(`采集库查询失败: ${e.message}`);
    }
    try {
      const u = chatDb.prepare('SELECT calls, prompt_tokens, completion_tokens FROM usage WHERE day=?')
        .get(new Date().toLocaleDateString('sv-SE'));
      out.push(`今日 LLM 用量: ${u ? `${u.calls} 次 / ${(u.prompt_tokens + u.completion_tokens).toLocaleString()} tokens` : '0 次'}`);
    } catch { /* 忽略 */ }
    return out.join('\n');
  }

  // ---------- pi_tasks: 采集任务/回填进度监控 ----------
  async function piTasks() {
    const out = [];
    // 1) 服务存活（本机全部 bot/collector 单元）
    const allUnits = ['llbot-139', 'collector-139', 'llbot-274', 'collector-274'];
    const st = await Promise.allSettled(allUnits.map((u) => run('systemctl', ['is-active', u], 5000).catch(() => 'unknown')));
    out.push(`服务: ${allUnits.map((u, i) => `${u}=${st[i].status === 'fulfilled' ? st[i].value : '?'}`).join('  ')}`);

    // 2) 采集覆盖面 + 速率（与上次查询对比）
    try {
      const rows = collectorDb.prepare(`
        SELECT peer_id, COUNT(*) n, MIN(time) mn, MAX(time) mx
        FROM messages WHERE scene='group' GROUP BY peer_id ORDER BY peer_id`).all();
      const snapTs = Math.floor(Date.now() / 1000);
      for (const r of rows) {
        const age = Math.round((snapTs - r.mx) / 60);
        let rateTxt = '';
        if (lastSnap && lastSnap.groups[r.peer_id] != null) {
          const dtMin = (Date.now() - lastSnap.ts) / 60000;
          if (dtMin > 0.2) {
            const per = Math.round((r.n - lastSnap.groups[r.peer_id]) / dtMin);
            rateTxt = per > 0 ? ` (+${per}/分钟, 回滚中)` : per === 0 ? ' (无新增)' : '';
          }
        }
        out.push(`群 ${r.peer_id}: ${r.n} 条, 覆盖 ${fmtT(r.mn)} ~ ${fmtT(r.mx)} (最新${age < 1 ? '刚刚' : age + '分钟前'})${rateTxt}`);
      }
      const priv = collectorDb.prepare("SELECT COUNT(*) n FROM messages WHERE scene='private'").get().n;
      if (priv) out.push(`私聊: ${priv} 条`);
      lastSnap = { ts: Date.now(), groups: Object.fromEntries(rows.map((r) => [r.peer_id, r.n])) };
    } catch (e) {
      out.push(`采集统计失败: ${e.message}`);
    }

    // 3) 时间段补收任务（range-job 文件）
    try {
      const jobs = existsSync(dataDir)
        ? readdirSync(dataDir).filter((f) => f.startsWith('range-job-') && f.endsWith('.json')) : [];
      for (const f of jobs) {
        try {
          const j = JSON.parse(readFileSync(path.join(dataDir, f), 'utf8'));
          const st2 = j.running ? '运行中' : (j.error ?? '已完成');
          out.push(`补收任务 群${j.peer} ${fmtT(j.from)}~${fmtT(j.to)}: ${st2}, 已翻${j.pages}页 新增${j.inserted} 覆盖到 ${fmtT(j.oldestTime)}`);
        } catch { /* 损坏文件跳过 */ }
      }
    } catch { /* 忽略 */ }

    // 4) LLM 今日用量
    try {
      const u = chatDb.prepare('SELECT calls, prompt_tokens, completion_tokens FROM usage WHERE day=?')
        .get(new Date().toLocaleDateString('sv-SE'));
      out.push(`今日 LLM 用量: ${u ? `${u.calls} 次 / ${(u.prompt_tokens + u.completion_tokens).toLocaleString()} tokens` : '0 次'}`);
    } catch { /* 忽略 */ }
    return out.join('\n');
  }
  const fmtT = (t) => (t ? new Date(t * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-');

  // ---------- backfill_range: 补收指定时间段消息（后台任务） ----------
  async function backfillRange(args) {
    const peer = Number(args.group);
    const groups = ctx.groups ?? [];
    if (!peer || !groups.includes(peer)) {
      return `只能补收本账号在的群（${groups.join(', ')}）。`;
    }
    const fromD = String(args.from ?? '').trim();
    const toD = String(args.to ?? '').trim();
    const dateOk = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s);
    if (!dateOk(fromD) || !dateOk(toD)) return '日期格式要 YYYY-MM-DD，例如 2026-08-20。';
    const dayStart = (s) => Math.floor(new Date(`${s}T00:00:00`).getTime() / 1000);
    const dayEnd = (s) => Math.floor(new Date(`${s}T23:59:59`).getTime() / 1000);
    if (dayStart(fromD) > dayEnd(toD)) return '起始日期不能晚于结束日期。';
    // 同 peer 已有任务在跑则拒绝
    const pf = path.join(dataDir, `range-job-group-${peer}.json`);
    if (existsSync(pf)) {
      try {
        const j = JSON.parse(readFileSync(pf, 'utf8'));
        if (j.running && Date.now() - j.startedAt < 6 * 3600 * 1000) {
          return `群 ${peer} 已有补收任务在跑（已翻${j.pages}页），等它完成再来。`;
        }
      } catch { /* 文件坏就覆盖 */ }
    }
    const script = path.join(LLM_ROOT, 'scripts', 'backfill-range.js');
    if (!existsSync(script)) return '补收脚本缺失（scripts/backfill-range.js）。';
    const child = spawn(process.execPath, [
      script,
      '--scene', 'group',
      '--peer', String(peer),
      '--from', fromD, '--to', toD,
      '--db', ctx.dbFile,
      '--http', ctx.httpUrl,
      '--token', ctx.httpToken ?? '',
      '--self', String(ctx.selfId ?? 0),
    ], { detached: true, stdio: 'ignore', cwd: LLM_ROOT });
    child.unref();
    log?.info?.(`[llm][tool] 已启动补收任务: 群${peer} ${fromD}~${toD} pid=${child.pid}`);
    return [
      `已启动补收任务：群 ${peer}，${fromD} 到 ${toD}。`,
      `任务在后台独立运行（pid ${child.pid}），每小时约能补 6千~7千条，不干扰正常采集。`,
      '之后问我「补收任务进度怎么样了」就能查。',
    ].join('\n');
  }

  // ---------- backup_now: 生成采集库快照（入库第一步, PC 端 gis ingest-pi 消费） ----------
  async function backupNow() {
    try {
      await pExec('/bin/bash', ['/opt/qqbot/scripts/backup-to-usb.sh'], { timeout: 900000 });
      const { stdout } = await pExec('cat', ['/opt/qqbot/backups/latest.txt'], { timeout: 10000 });
      const snap = stdout.trim();
      return [
        `快照已生成：${snap}`,
        '入库第二步在 PC 端执行（主库在 PC）：python -m gis ingest-pi',
        '或者直接让主人在 PC 上叫 AI 助手跑这条命令即可完成合并。',
      ].join('\n');
    } catch (e) {
      return `备份脚本失败: ${e.message}`;
    }
  }

// 追加到 src/llm/tools.js 的 buildTools 内: 联网检索工具(webSearch + fetchPage)
// ===== web_search / fetch_page (2026-09-06) =====
async function webSearch(args) {
  const q = String(args.query ?? '').trim();
  if (!q) return 'query 不能为空';
  const n = Math.min(Math.max(Number(args.count) || 5, 1), 10);
  const url = 'https://cn.bing.com/search?format=rss&count=' + n + '&q=' + encodeURIComponent(q);
  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'zh-CN,zh;q=0.9' },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) return `搜索请求失败: HTTP ${res.status}`;
  const xml = await res.text();
  const items = [];
  const re = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = re.exec(xml)) && items.length < n) {
    const seg = m[1];
    const pick = (tag) => {
      const mm = seg.match(new RegExp('<' + tag + '>([\\s\\S]*?)</' + tag + '>'));
      if (!mm) return '';
      return mm[1]
        .replace(/<!\[CDATA\[|\]\]>/g, '')
        .replace(/<[^>]+>/g, '')
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();
    };
    items.push({ title: pick('title'), url: pick('link'), snippet: pick('description') });
  }
  if (!items.length) return `「${q}」没有搜索结果（或被风控）。可以换个关键词，或用 fetch_page 直接读 URL。`;
  return items.map((it, i) => `${i + 1}. ${it.title}\n   ${it.url}\n   ${it.snippet}`).join('\n');
}

async function fetchPage(args) {
  const url = String(args.url ?? '').trim();
  if (!/^https?:\/\//i.test(url)) return 'url 必须以 http(s):// 开头';
  const UA = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  };
  let res;
  try {
    res = await fetch(url, { headers: UA, signal: AbortSignal.timeout(20000), redirect: 'follow' });
  } catch (e) {
    return `页面请求失败: ${e.message}（站点可能无响应或被墙）`;
  }
  if (!res.ok) return `页面请求失败: HTTP ${res.status}（可能需要登录/反爬）`;
  const ct = res.headers.get('content-type') ?? '';
  if (!/text\/html|text\/plain|application\/(json|xml|rss|xhtml)/i.test(ct)) {
    return `不支持的内容类型: ${ct}（仅支持网页/文本类）`;
  }
  // 字节级取body, 按声明字符集解码(老站GBK乱码问题)
  const buf = await res.arrayBuffer();
  let html = new TextDecoder('utf-8', { fatal: false }).decode(buf);
  if (/[\uFFFD]{3,}/.test(html)) {
    const m = ct.match(/charset=([\w-]+)/i) ?? html.match(/<meta[^>]+charset=["']?([\w-]+)/i);
    if (m && !/utf-?8/i.test(m[1])) {
      try { html = new TextDecoder(m[1].toLowerCase()).decode(buf); } catch { /* 解码器不存在就保持utf-8 */ }
    }
  }
  const title = (html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '').replace(/<[^>]+>/g, '').trim().slice(0, 120);
  const desc = (html.match(/<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i)?.[1] ?? '').trim().slice(0, 200);
  // 块级抽取: 剪掉不可见区, 块级闭合标签转换行, 剥标签, 按行清理
  let body = html
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<(script|style|noscript|svg|iframe|template)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<(nav|footer|header|aside|form)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6]|tr|section|article|blockquote|pre|dd|dt|option)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ');
  const lines = body
    .split('\n')
    .map((l) => l.replace(/&nbsp;/gi, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#x?[0-9a-f]+;/gi, ' ').replace(/\s+/g, ' ').trim())
    .filter((l) => l.length >= 4)
    // 去连续重复行(菜单循环渲染)
    .filter((l, i, arr) => i === 0 || l !== arr[i - 1]);
  const text = lines.join('\n');
  const head = [`【网页】${title || url}`, desc ? `【摘要】${desc}` : '', `【URL】${res.url || url}`].filter(Boolean).join('\n');
  if (lines.length < 3 || text.length < 150) {
    return `${head}\n\n⚠️ 正文提取不到内容——该页面几乎肯定是 JS 动态渲染或需要登录（常见于百度/知乎/B站/微博的页面）。\n建议: ①用 web_search 搜关键词拿摘要 ②换该站点的文章直链或移动版(m.) ③告诉我标题我帮你搜。`;
  }
  return `${head}\n\n${text}`;
}

// ===== deep_search (GLM云端检索, 2026-09-06) =====
// 通道: 智谱 chat completions + web_search 工具 (key 在 cfg.search.apiKey, 不入git)
// 返回: 带引用的综述 + 来源列表; 比Bing RSS质量高一个量级(时效性/中文/合成)
async function deepSearch(args) {
  const q = String(args.query ?? '').trim();
  if (!q) return 'query 不能为空';
  const s = cfg.search;
  if (!s?.apiKey) return '未配置检索通道(llm.json 缺 search.apiKey)';
  const body = {
    model: s.model || 'glm-5.3-flash',
    messages: [{ role: 'user', content: `${q}\n\n(回答需基于联网检索结果, 末尾用[来源N]标注, 并列出关键来源标题)` }],
    tools: [{ type: 'web_search', web_search: { enable: true } }],
    stream: false,
  };
  const res = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + s.apiKey },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(90000),
  });
  if (!res.ok) return `云端检索失败: HTTP ${res.status}`;
  const data = await res.json();
  const content = data.choices?.[0]?.message?.content ?? '';
  if (!content) return '云端检索返回空(可能触发风控或欠费)';
  const refs = (data.web_search ?? []).map((it, i) => `${i + 1}. ${it.title ?? ''} ${it.link ?? it.url ?? ''}`.trim());
  return `【云端检索·综述】\n${content}${refs.length ? '\n\n【来源】\n' + refs.slice(0, 8).join('\n') : ''}`;
}


// ---------- 注册表 ----------
  const defs = [
    {
      type: 'function',
      function: {
        name: 'pi_status',
        description: '查询树莓派运行状态：运行时长/负载/内存/磁盘/温度/电源状况，以及 QQ 协议端和采集服务是否存活、采集库心跳。主人问状态、任务、服务、负载、温度时调用。',
        parameters: { type: 'object', properties: {}, additionalProperties: false },
      },
    },
    {
      type: 'function',
      function: {
        name: 'pi_logs',
        description: '查看树莓派指定服务的最近日志尾部（只读）。unit 可选值: ' + cfg.tools.units.join(' / '),
        parameters: {
          type: 'object',
          properties: {
            unit: { type: 'string', enum: [...cfg.tools.units], description: '服务名' },
            lines: { type: 'integer', description: '行数, 默认20, 最多80', default: 20 },
          },
          required: ['unit'],
          additionalProperties: false,
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'collector_db',
        description: '查询采集数据库统计：消息总量/近24小时/最新消息时间、媒体下载状态、人工标注量、今日 LLM 用量。',
        parameters: { type: 'object', properties: {}, additionalProperties: false },
      },
    },
    {
      type: 'function',
      function: {
        name: 'pi_tasks',
        description: '监控 Pi 上的采集任务：各服务存活状态、每个群的采集覆盖区间与回滚速率（多少条/分钟）、时间段补收任务进度、今日 LLM 用量。主人问「任务跑到哪了」「回滚进度」「采集情况」时调用。',
        parameters: { type: 'object', properties: {}, additionalProperties: false },
      },
    },
    {
      type: 'function',
      function: {
        name: 'backfill_range',
        description: '补收某个群在指定日期时间段内的历史消息（后台任务，不阻塞）。适合主人说「补收群X 8月20日到8月25日的聊天记录」这类需求。',
        parameters: {
          type: 'object',
          properties: {
            group: { type: 'integer', description: '群号', enum: [...(ctx.groups ?? [])] },
            from: { type: 'string', description: '起始日期 YYYY-MM-DD（含当天）' },
            to: { type: 'string', description: '结束日期 YYYY-MM-DD（含当天）' },
          },
          required: ['group', 'from', 'to'],
          additionalProperties: false,
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'backup_now',
        description: '立即在树莓派上生成采集数据库快照（入库流程第一步，快照生成后由 PC 端 gis ingest-pi 合并入主库）。主人说「备份一下」「生成快照」或要求入库时调用。',
        parameters: { type: 'object', properties: {}, additionalProperties: false },
      },
    },
    {
      type: 'function',
      function: {
        name: 'web_search',
        description: '联网搜索：用 Bing 检索实时信息（新闻/资料/价格/天气等），返回标题+链接+摘要。主人问「搜一下」「最新的」「现在」「网上」或需要时效性信息时调用。',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: '搜索关键词（可用中文）' },
            count: { type: 'integer', description: '结果条数 1-10, 默认5' },
          },
          required: ['query'],
          additionalProperties: false,
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'fetch_page',
        description: '抓取指定网页的正文文本（去标签）。搜索结果里某条链接需要细读时，或主人直接给 URL 时调用。',
        parameters: {
          type: 'object',
          properties: {
            url: { type: 'string', description: '完整的 http(s):// 网页地址' },
          },
          required: ['url'],
          additionalProperties: false,
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'deep_search',
        description: '云端深度检索（推荐）：LLM+联网搜索的合成通道，返回带引用的最新信息综述。时效性问题（新闻/版本/价格/赛事/天气）、需要准确出处的问题优先用这个，比 web_search 强得多。',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: '检索问题（完整的自然语言问题，可用中文）' },
          },
          required: ['query'],
          additionalProperties: false,
        },
      },
    },
  ];

  const impls = {
    pi_status: piStatus,
    pi_logs: piLogs,
    collector_db: collectorDbStats,
    pi_tasks: piTasks,
    backfill_range: backfillRange,
    backup_now: backupNow,
    web_search: webSearch,
    fetch_page: fetchPage,
    deep_search: deepSearch,
  };

  async function exec(name, argsJson) {
    const fn = impls[name];
    if (!fn) return `未知工具: ${name}`;
    let args = {};
    if (argsJson) {
      try { args = JSON.parse(argsJson); } catch { return '参数不是合法 JSON'; }
    }
    try {
      const out = String(await fn(args) ?? '(空)');
      const cap = (name === 'fetch_page' || name === 'deep_search') ? lim.toolOutputMaxChars * 3 : lim.toolOutputMaxChars;
      return out.length > cap ? out.slice(0, cap) + `\n...(截断,共${out.length}字)` : out;
    } catch (e) {
      log?.warn?.(`[llm][tool] ${name} 失败: ${e.message}`);
      return `工具执行失败: ${e.message}`;
    }
  }

  return { defs, exec };
}
