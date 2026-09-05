/**
 * llm/loop.js — 迷你 Agent 循环（借鉴 harness 的 turn/step 模型，等比例缩小）
 *
 * 一轮 = system(人设+环境) + 历史窗口 + 用户消息
 *      → 模型 → 有 tool_calls 则执行并回填 → 再请求（最多 maxToolSteps 步）
 *      → 无 tool_calls 即最终回复。
 * 每一步的每一条消息（含工具结果）都先落库再进上下文——模型可见即已记录。
 */
import { chatCompletion } from './adapter.js';
import { buildTools } from './tools.js';
import { appendMessage, windowMessages, addUsage, resolveApiKey } from './config-helpers.js';

export async function runTurn({ cfg, chatDb, collectorDb, sessionId, modelKey, userText, log, personaText }) {
  const { prov, modelDef } = resolveApiKey(cfg, modelKey);
  const { defs, exec } = buildTools(cfg, collectorDb, chatDb, log, cfg._ctx);
  const lim = cfg.limits;

  const now = new Date().toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
  const system = `${personaText || cfg.persona}\n\n[环境] 当前时间: ${now}（Asia/Shanghai）；宿主: 树莓派 4GB（采集+协议端所在机器）。`;

  const history = windowMessages(chatDb, sessionId, lim.contextMessages);
  const trimmed = userText.length > lim.inputMaxChars ? userText.slice(0, lim.inputMaxChars) + '…(截断)' : userText;
  const messages = [{ role: 'system', content: system }, ...history, { role: 'user', content: trimmed }];
  appendMessage(chatDb, sessionId, { role: 'user', content: trimmed });

  const useTools = modelDef.tools !== false;
  let last = null;
  for (let step = 0; step < lim.maxToolSteps; step++) {
    last = await chatCompletion({
      baseURL: prov.baseURL,
      apiKey: prov.apiKey,
      model: modelDef.name,
      messages,
      tools: useTools ? defs : undefined,
      timeoutMs: modelDef.timeoutMs ?? 60000,
    });
    addUsage(chatDb, last.usage);
    messages.push({
      role: 'assistant',
      content: last.content || '',
      ...(last.tool_calls ? { tool_calls: last.tool_calls } : {}),
    });
    appendMessage(chatDb, sessionId, {
      role: 'assistant', content: last.content || '', tool_calls: last.tool_calls,
    });
    if (!last.tool_calls?.length) return last.content || '(空回复，可重发)';

    for (const call of last.tool_calls) {
      const out = await exec(call.function?.name, call.function?.arguments);
      messages.push({ role: 'tool', tool_call_id: call.id, content: out });
      appendMessage(chatDb, sessionId, { role: 'tool', content: out, tool_call_id: call.id });
    }
  }
  // 步数用尽：摘掉工具强制收尾
  const final = await chatCompletion({
    baseURL: prov.baseURL, apiKey: prov.apiKey, model: modelDef.name,
    messages, timeoutMs: modelDef.timeoutMs ?? 60000,
  });
  addUsage(chatDb, final.usage);
  appendMessage(chatDb, sessionId, { role: 'assistant', content: final.content || '' });
  return final.content || '(空回复，可重发)';
}
