const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}
async function search(q) {
  const r = await fetch(`https://api.github.com/search/repositories?q=${encodeURIComponent(q)}&sort=stars&order=desc&per_page=6`, UA);
  return r.ok ? r.json() : null;
}

async function main() {
  const repos = [
    'OFA-Sys/Chinese-CLIP',
    'IDEA-CCNL/Fengshenbang-LM',
    'QwenLM/Qwen2.5-VL',
    'huggingface/transformers',
    'shibing624/text2vec',
    'scikit-learn/scikit-learn',
  ];
  console.log('== 关键组件仓库 ==');
  for (const r of repos) {
    const j = await api(`/repos/${r}`);
    console.log(j ? `${r} | stars=${j.stargazers_count} | pushed=${String(j.pushed_at).slice(0,10)} | ${(j.description || '').slice(0,70)}` : `${r} | NOT FOUND`);
  }
  for (const q of ['focal loss pytorch', 'meme classification chinese', 'gender author profiling social media', 'emotion classification chinese pretrained']) {
    const j = await search(q);
    console.log(`\n== search: ${q} ==`);
    if (!j) { console.log('(failed)'); continue; }
    for (const it of j.items.slice(0, 6)) {
      console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,80)}`);
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
