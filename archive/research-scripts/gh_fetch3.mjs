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
  // 1. whitechi73 账户是否存在
  const u = await api('/users/whitechi73');
  console.log(`users/whitechi73 -> status=${u.status}`);

  // 2. Pages 文档站是否还在
  const p1 = await getHtml('https://whitechi73.github.io/OpenShamrock/');
  console.log(`\nwhitechi73.github.io/OpenShamrock -> status=${p1.status}${p1.text ? ' len=' + p1.text.length : ''}`);
  if (p1.text) {
    const t = p1.text.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    console.log(t.slice(0, 800));
  }

  // 3. 搜索 Shamrock QQ 相关高星仓库
  const s = await api('/search/repositories?q=Shamrock+QQ&sort=stars&order=desc&per_page=10');
  if (s.json) {
    console.log('\n== search Shamrock QQ ==');
    for (const it of s.json.items.slice(0, 8)) {
      console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,70)}`);
    }
  }

  // 4. callng/QQHook
  const q = await api('/repos/callng/QQHook');
  console.log(`\ncallng/QQHook -> status=${q.status}`);
  if (q.json) {
    console.log(`stars=${q.json.stargazers_count} pushed=${String(q.json.pushed_at).slice(0,10)} desc=${(q.json.description || '').slice(0,80)}`);
    const readme = await getHtml(`https://raw.githubusercontent.com/callng/QQHook/${q.json.default_branch}/README.md`);
    if (readme.ok) console.log(readme.text.split('\n').slice(0, 60).join('\n'));
  }

  // 5. gitcode 镜像 README
  const g = await getHtml('https://gitcode.com/gh_mirrors/op/OpenShamrock');
  console.log(`\ngitcode mirror -> status=${g.status}${g.text ? ' len=' + g.text.length : ''}`);
  if (g.text) {
    const m = g.text.match(/8\.9\.[0-9.]+|9\.0\.[0-9.]+|支持.*QQ|QQ [0-9.]+/g);
    if (m) console.log('version hints:', [...new Set(m)].slice(0, 20).join(' | '));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
