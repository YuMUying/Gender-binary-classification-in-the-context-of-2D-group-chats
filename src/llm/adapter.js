/**
 * llm/adapter.js — OpenAI 兼容 Chat Completions 客户端（非流式）
 *
 * 借鉴 harness 的「适配器只管传输」原则：
 *  - fetch + Bearer，超时 AbortController
 *  - 5xx/429/网络抖动重试一次，超时不重试（reasoner 重试代价太大）
 *  - 透传 usage（token 计量给预算系统）
 */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function chatCompletion({ baseURL, apiKey, model, messages, tools, timeoutMs = 60000 }) {
  const url = baseURL.replace(/\/+$/, '') + '/chat/completions';
  const body = { model, messages, stream: false };
  if (tools?.length) body.tools = tools;

  for (let attempt = 0; attempt < 2; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method: 'POST',
        signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        if ((res.status >= 500 || res.status === 429) && attempt === 0) {
          await sleep(2000);
          continue;
        }
        throw new Error(`LLM HTTP ${res.status}: ${text.slice(0, 300)}`);
      }
      const data = await res.json();
      const msg = data.choices?.[0]?.message ?? {};
      return {
        content: typeof msg.content === 'string' ? msg.content : '',
        tool_calls: Array.isArray(msg.tool_calls) ? msg.tool_calls : null,
        usage: data.usage ?? null,
        finish_reason: data.choices?.[0]?.finish_reason ?? null,
      };
    } catch (e) {
      if (e.name === 'AbortError') throw new Error(`LLM 请求超时 (${timeoutMs}ms)`);
      const retryable = /fetch failed|ECONNRESET|EAI_AGAIN|socket hang up/i.test(
        `${e.message} ${e.cause?.code ?? ''}`);
      if (retryable && attempt === 0) {
        await sleep(2000);
        continue;
      }
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error('LLM 请求失败（重试后仍失败）');
}
