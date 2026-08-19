const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}
async function raw(u, tries = 4) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(u, { headers: { 'User-Agent': 'research' } });
      if (r.ok) return await r.text();
      if (r.status === 404) return null;
    } catch { /* retry */ }
    await new Promise(res => setTimeout(res, 1200 * (i + 1)));
  }
  return null;
}

async function main() {
  const readme = await raw('https://raw.githubusercontent.com/NapNeko/NapCat-Docker/main/README.md');
  console.log('== README ==');
  console.log(readme ? readme.split('\n').slice(0, 90).join('\n') : '(failed)');

  // 看 compose 和 base 目录里有没有 arm64
  const base = await api('/repos/NapNeko/NapCat-Docker/contents/base');
  console.log('\n== base dir ==');
  if (base) console.log(base.map(x => x.name).join(', '));
  const compose = await api('/repos/NapNeko/NapCat-Docker/contents/compose');
  console.log('== compose dir ==');
  if (compose) console.log(compose.map(x => x.name).join(', '));
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
