/**
 * llm/handler.js — AI 助手事件入口
 *
 * 职责（借鉴 harness pre-step + guard 思想）：
 *  - 过滤：只响应白名单用户的私聊；推理/xnn 前缀让位给 infer.js
 *  - 指令快路径（不花 token）：/help /reset /model /status
 *  - LLM 慢路径：串行队列 + 冷却 + 日预算（token/次数）+ 失败友好降级
 *  - 回复分段（超长按行切分）
 */
import { loadLlmConfig, LLM_ROOT } from './config.js';
import { openChatDb, activeSession, resetSession, setSessionModel, usageToday } from './session.js';
import { runTurn } from './loop.js';
import { buildTools } from './tools.js';
import path from 'node:path';
import { readFileSync, existsSync, readdirSync } from 'node:fs';

/** 角色卡目录: ROOT/personas/*.json; 卡片 = {name?, ...结构化字段} 或 {name, persona} */
const PERSONA_DIR = path.join(LLM_ROOT, 'personas');

function composeCardPersona(card, fallbackName) {
  if (typeof card.persona === 'string' && card.persona.trim()) return card.persona;
  const parts = [];
  const name = card.name || card.名字 || fallbackName;
  parts.push(`你现在扮演「${name}」，在私聊中与主人（对方）交谈，全程保持人设。`);
  if (card.身份感) parts.push(`身份感：${card.身份感}`);
  if (card.性格) parts.push(`性格：${card.性格}`);
  const yt = card.语体 ?? card.说话方式;
  if (yt) parts.push(`说话方式：${Array.isArray(yt) ? yt.join('；') : yt}`);
  const kc = card.口头禅;
  if (kc) parts.push(`口头禅：${Array.isArray(kc) ? kc.join('、') : kc}`);
  if (card.幽默类型) parts.push(`幽默类型：${card.幽默类型}`);
  if (card.阴影) parts.push(`内心阴影（偶尔流露）：${Array.isArray(card.阴影) ? card.阴影.join('；') : card.阴影}`);
  if (card.补充) parts.push(`补充设定：${Array.isArray(card.补充) ? card.补充.join('；') : card.补充}`);
  return parts.join('\n');
}

function listPersonaCards() {
  if (!existsSync(PERSONA_DIR)) return [];
  return readdirSync(PERSONA_DIR).filter((f) => f.endsWith('.json')).map((f) => {
    const stem = f.replace(/\.json$/, '');
    try {
      const card = JSON.parse(readFileSync(path.join(PERSONA_DIR, f), 'utf8'));
      return { file: stem, name: card.name || card.名字 || stem };
    } catch { return { file: stem, name: stem + '（解析失败）' }; }
  });
}

export function makeLlmHandler(config, collectorDb, bot, log) {
  const cfg = loadLlmConfig();
  if (!cfg) return null;
  if (!cfg.allow_users.length) throw new Error('llm.json 未配置 allow_users');

  // 默认人设可以指向一张角色卡(llm.json 的 persona_card: "卡名"), 未加载任何卡时用它
  let defaultPersonaName = '阿雪';
  if (cfg.persona_card) {
    try {
      const cardFile = path.join(PERSONA_DIR, cfg.persona_card + '.json');
      const card = JSON.parse(readFileSync(cardFile, 'utf8'));
      defaultPersonaName = card.name || card.名字 || cfg.persona_card;
      cfg.persona = composeCardPersona(card, cfg.persona_card);
      log.info(`[llm] 默认人设=角色卡「${defaultPersonaName}」(${cfg.persona_card}.json)`);
    } catch (e) {
      log.warn(`[llm] persona_card「${cfg.persona_card}」加载失败, 回落内置人设: ${e.message}`);
    }
  }

  // 运行环境：供工具层使用（各自 bot 的 HTTP API、各自的采集库、各自在的群）
  cfg._ctx = {
    httpUrl: config.onebot.httpUrl,
    httpToken: config.onebot.httpToken ?? config.onebot.accessToken ?? '',
    dbFile: path.isAbsolute(config.database ?? '')
      ? config.database
      : path.join(LLM_ROOT, config.database ?? 'data/chat.db'),
    groups: config.collect?.groups ?? [],
    units: cfg.tools.units,
  };

  const chatDb = openChatDb(cfg.database);
  const personaMap = new Map();   // sessionPeer → {name, persona}（运行时角色卡，重启后回归默认）
  const { exec: execTool } = buildTools(cfg, collectorDb, chatDb, log, cfg._ctx);
  const lim = cfg.limits;

  // 会话命名空间：<bot账号>:<用户QQ> —— 多 bot 共库时上下文互不串
  const sessionPeer = (record) => `${bot.selfId ?? 'unknown'}:${record.user_id}`;

  let chain = Promise.resolve();     // 串行队列（防止并发请求打爆 API/顺序错乱）
  let pending = 0;
  let lastStart = 0;
  let budgetNoticeDay = '';

  function sendPrivate(peer, text) {
    return bot.callApi('send_private_msg', { user_id: peer, message: text });
  }

  /** 超长分段（按行聚合到 replyMaxChars） */
  function splitReply(text) {
    if (text.length <= lim.replyMaxChars) return [text];
    const chunks = [];
    let cur = '';
    for (const line of text.split('\n')) {
      if (cur.length + line.length + 1 > lim.replyMaxChars && cur) {
        chunks.push(cur);
        cur = '';
      }
      cur += (cur ? '\n' : '') + line;
    }
    if (cur) chunks.push(cur);
    return chunks;
  }

  async function sendSplit(peer, text) {
    for (const seg of splitReply(text)) {
      await sendPrivate(peer, seg);
    }
  }

  function budgetExceeded() {
    const u = usageToday(chatDb);
    return u.total_tokens >= lim.dailyTokenBudget || u.calls >= lim.dailyCallBudget;
  }

  /** 主入口（永不让异常逃逸——采集主线不受影响） */
  async function inner(record) {
    if (!record || record.scene !== 'private') return false;
    if (!cfg.allow_users.includes(record.user_id)) return false;
    const peer = record.peer_id ?? record.user_id;
    const text = (record.text || '').trim();
    if (!text) return false;
    if (record.user_id === Number(bot.selfId)) return false;

    // ---- 指令快路径（不耗 token）----
    if (/^\/?(help|帮助)$/i.test(text)) {
      await sendPrivate(peer, [
        '【AI 助手指令】',
        '/help 帮助',
        '/reset 重置对话（清空上下文记忆）',
        '/model 查看可用模型；/model <key> 切换（如 /model reasoner）',
        '/status 树莓派状态速览（不走大模型）',
        '/cards 查看角色卡；/card <名字> 加载角色卡；/uncard 卸载回归默认人设',
        '其余任意消息直接和我聊；也支持临时角色扮演（例：「扮演傲娇猫娘」）。',
      ].join('\n'));
      return true;
    }
    if (/^\/?(reset|重置)$/i.test(text)) {
      const s = resetSession(chatDb, sessionPeer(record), cfg.default_model);
      log.info(`[llm] 会话重置 → ${s.id}`);
      await sendPrivate(peer, '已重置对话，记忆清空。');
      return true;
    }
    const mModel = text.match(/^\/?(?:model|模型)(?:\s+(\S+))?$/i);
    if (mModel) {
      if (!mModel[1]) {
        const cur = activeSession(chatDb, sessionPeer(record), cfg.default_model);
        const list = Object.entries(cfg.models)
          .map(([k, m]) => `${k === cur.model ? '▶' : ' '} ${k} — ${m.label ?? m.name}`)
          .join('\n');
        await sendPrivate(peer, `当前模型: ${cur.model}\n可用:\n${list}\n切换: /model <key>`);
        return true;
      }
      const key = mModel[1].toLowerCase();
      if (!cfg.models[key]) {
        await sendPrivate(peer, `没有模型 ${key}。可用: ${Object.keys(cfg.models).join(', ')}`);
        return true;
      }
      setSessionModel(chatDb, sessionPeer(record), key);
      await sendPrivate(peer, `已切换到 ${key} — ${cfg.models[key].label ?? cfg.models[key].name}`);
      return true;
    }
    if (/^\/?(status|状态)$/i.test(text)) {
      const s = await execTool('pi_status', '');
      await sendSplit(peer, `【树莓派状态】\n${s}`);
      return true;
    }
    if (/^\/?(?:cards|角色卡列表|角色卡)\s*$/i.test(text)) {
      const cards = listPersonaCards();
      const cur = personaMap.get(sessionPeer(record));
      await sendPrivate(peer, `【角色卡】当前: ${cur ? cur.name : '默认（' + defaultPersonaName + '）'}\n可用:\n${cards.map((c) => `${cur && cur.name === c.name ? '▶' : ' '} ${c.file} — ${c.name}${c.file === cfg.persona_card ? '（默认）' : ''}`).join('\n')}\n加载: /card <名字>  卸载: /uncard`);
      return true;
    }
    const mCard = text.match(/^\/?(?:card|加载角色卡)\s+(\S+)$/);
    if (mCard) {
      const key = mCard[1];
      const file = path.join(PERSONA_DIR, key + '.json');
      if (!existsSync(file)) {
        const cards = listPersonaCards().map((c) => c.file).join(', ');
        await sendPrivate(peer, `没有角色卡「${key}」。可用: ${cards || '（personas/ 目录为空）'}`);
        return true;
      }
      try {
        const card = JSON.parse(readFileSync(file, 'utf8'));
        const name = card.name || card.名字 || key;
        personaMap.set(sessionPeer(record), { name, persona: composeCardPersona(card, key) });
        await sendPrivate(peer, `已加载角色卡「${name}」。从下一句话开始入戏～（/uncard 卸载）`);
      } catch (e) {
        await sendPrivate(peer, `角色卡解析失败: ${e.message}`);
      }
      return true;
    }
    if (/^\/?(?:uncard|卸载角色卡)$/i.test(text)) {
      personaMap.delete(sessionPeer(record));
      await sendPrivate(peer, `已卸载角色卡，回到默认人设（${defaultPersonaName}）。`);
      return true;
    }

    // ---- LLM 慢路径 ----
    if (pending >= lim.queueMax) {
      await sendPrivate(peer, '消息排队中有点多，稍几秒再发～');
      return true;
    }
    const since = Date.now() - lastStart;
    if (since < lim.cooldownMs) await new Promise((r) => setTimeout(r, lim.cooldownMs - since));
    if (budgetExceeded()) {
      if (budgetNoticeDay !== new Date().toLocaleDateString('sv-SE')) {
        budgetNoticeDay = new Date().toLocaleDateString('sv-SE');
        await sendPrivate(peer, `今日 LLM 用量已达预算上限（${lim.dailyTokenBudget.toLocaleString()} tokens / ${lim.dailyCallBudget} 次），明天恢复。`);
      }
      return true;
    }

    const session = activeSession(chatDb, sessionPeer(record), cfg.default_model);
    pending++;
    chain = chain.then(async () => {
      lastStart = Date.now();
      try {
        const card = personaMap.get(sessionPeer(record));
        const reply = await runTurn({
          cfg, chatDb, collectorDb, sessionId: session.id,
          modelKey: session.model, userText: text, log,
          personaText: card?.persona,
        });
        await sendSplit(peer, reply);
        log.info(`[llm] → ${peer}: ${String(reply).slice(0, 40).replace(/\n/g, ' ')}`);
      } catch (e) {
        log.error(`[llm] 回合失败: ${e.message}`);
        try { await sendPrivate(peer, '（开小差了，稍后再试一次？）'); } catch { /* 忽略 */ }
      } finally {
        pending--;
      }
    });
    return true;
  }

  return {
    handle(record) {
      inner(record).catch((e) => log.warn(`[llm] 处理异常: ${e.message}`));
    },
  };
}
