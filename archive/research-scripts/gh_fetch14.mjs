async function api(p) {
  const r = await fetch('https://api.github.com' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? r.json() : null;
}
async function raw(p) {
  const r = await fetch('https://raw.githubusercontent.com/LagrangeDev/acidify/main/' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? await r.text() : null;
}

async function main() {
  const d = await api('/repos/LagrangeDev/acidify/contents/acidify-docs/content/docs/yogurt');
  console.log('== docs/yogurt ==');
  if (d) console.log(d.map(x => `${x.type} ${x.path}`).join('\n'));
  else { console.log('list failed'); return; }
  const target = d.find(x => /start|index|quick/i.test(x.name)) || d.find(x => x.type === 'file');
  if (target) {
    const t = await raw(target.path);
    if (t) console.log(`\n== ${target.path} ==\n` + t.split('\n').slice(0, 150).join('\n'));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
