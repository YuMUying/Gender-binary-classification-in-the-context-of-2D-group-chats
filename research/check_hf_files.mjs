// 查 hfl/chinese-roberta-wwm-ext 仓库是否有 safetensors
const r = await fetch('https://huggingface.co/api/models/hfl/chinese-roberta-wwm-ext/tree/main', {
  headers: { 'User-Agent': 'Mozilla/5.0' },
  // 走系统代理由 Node 决定；若失败再手工代理
});
const j = await r.json();
for (const f of j ?? []) console.log(f.path, Math.round((f.size ?? 0) / 1048576), 'MB');
