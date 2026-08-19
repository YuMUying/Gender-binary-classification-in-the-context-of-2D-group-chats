async function api(p) {
  const r = await fetch('https://api.github.com' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? r.json() : null;
}

async function main() {
  const docs = await api('/repos/LagrangeDev/acidify/contents/acidify-docs');
  console.log('== acidify-docs ==');
  if (docs) console.log(docs.map(x => `${x.type} ${x.path}`).join('\n'));

  for (const repo of ['SaltifyDev/milky', 'LagrangeDev/acidify']) {
    const i = await api(`/repos/${repo}/issues/46`);
    if (i && i.body) {
      console.log(`\n== ${repo} issue #46 ==\n${i.title}\n${i.body.slice(0, 3000)}`);
      break;
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
