async function api(p) {
  const r = await fetch('https://api.github.com' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? r.json() : null;
}
async function raw(p) {
  const r = await fetch('https://raw.githubusercontent.com/LagrangeDev/acidify/main/' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? r.text() : null;
}

async function main() {
  const d = await api('/repos/LagrangeDev/acidify/contents/acidify-docs/content/docs');
  console.log('== docs ==');
  if (d) console.log(d.map(x => `${x.type} ${x.path}`).join('\n'));
  // 尝试 yogurt start 页面 markdown
  for (const p of ['acidify-docs/content/docs/yogurt/start.mdx', 'acidify-docs/content/docs/yogurt/start.md', 'acidify-docs/content/docs/yogurt.mdx']) {
    const t = await raw(p);
    if (t) { console.log(`\n== ${p} ==\n` + t.split('\n').slice(0, 120).join('\n')); break; }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
