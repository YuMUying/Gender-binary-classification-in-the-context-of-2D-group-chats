const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null };
}
async function getHtml(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 research' } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}

async function main() {
  // 1. yogurt releases (Android artifacts?)
  const y = await api('/repos/SaltifyDev/yogurt-releases/releases/latest');
  console.log('== yogurt-releases latest ==');
  if (y.json) {
    console.log(`tag=${y.json.tag_name} published=${String(y.json.published_at).slice(0,10)}`);
    for (const a of y.json.assets.slice(0, 30)) console.log('  asset:', a.name, `(${Math.round(a.size / 1048576)}MB)`);
  } else console.log('status', y.status);

  // 2. icqqjs org repos
  const o = await api('/orgs/icqqjs/repos?per_page=20&sort=pushed');
  console.log('\n== icqqjs org repos ==');
  if (o.json) for (const r of o.json) console.log(`${r.name} | stars=${r.stargazers_count} | pushed=${String(r.pushed_at).slice(0,10)} | ${(r.description || '').slice(0,60)}`);

  // 3. am009/Shamrock releases
  const a = await api('/repos/am009/Shamrock/releases/latest');
  console.log('\n== am009/Shamrock latest release ==');
  if (a.json) console.log(`tag=${a.json.tag_name} name=${a.json.name} published=${String(a.json.published_at).slice(0,10)}`);
  else console.log('status', a.status);

  // 4. chen-dimitry/OpenShamrock releases
  const c = await api('/repos/chen-dimitry/OpenShamrock/releases?per_page=5');
  console.log('\n== chen-dimitry/OpenShamrock releases ==');
  if (c.json) { if (!c.json.length) console.log('(none)'); for (const r of c.json) console.log(`tag=${r.tag_name} published=${String(r.published_at).slice(0,10)}`); }

  // 5. acidify 项目主页文本
  const h = await getHtml('https://acidify.ntqqrev.org/');
  console.log(`\n== acidify.ntqqrev.org status=${h.status} ==`);
  if (h.text) {
    const t = h.text.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    console.log(t.slice(0, 1200));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
