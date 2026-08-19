const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  if (!r.ok) throw new Error(`${p} -> ${r.status}`);
  return r.json();
}

async function main() {
  // 1. 搜索 OpenShamrock 相关仓库
  const s1 = await api('/search/repositories?q=OpenShamrock&sort=stars&order=desc&per_page=10');
  console.log('== search OpenShamrock ==');
  for (const it of s1.items.slice(0, 8)) {
    console.log(`${it.full_name} | stars=${it.stargazers_count} | fork=${it.fork} | pushed=${String(it.pushed_at).slice(0,10)} | archived=${it.archived} | ${it.description ? it.description.slice(0,60) : ''}`);
  }

  // 2. chen-dimitry/OpenShamrock 详情 + parent
  try {
    const j = await api('/repos/chen-dimitry/OpenShamrock');
    console.log('\n== chen-dimitry/OpenShamrock ==');
    console.log(`parent=${j.parent ? j.parent.full_name : 'NONE'} stars=${j.stargazers_count} pushed=${String(j.pushed_at).slice(0,10)} default_branch=${j.default_branch}`);
  } catch (e) { console.log('chen-dimitry FAILED', e.message); }

  // 3. 搜索 icqq
  const s2 = await api('/search/repositories?q=icqq&sort=stars&order=desc&per_page=10');
  console.log('\n== search icqq ==');
  for (const it of s2.items.slice(0, 8)) {
    console.log(`${it.full_name} | stars=${it.stargazers_count} | fork=${it.fork} | pushed=${String(it.pushed_at).slice(0,10)} | archived=${it.archived} | ${it.description ? it.description.slice(0,60) : ''}`);
  }

  // 4. NapCatQQ 主仓库
  try {
    const j = await api('/repos/NapNeko/NapCatQQ');
    console.log(`\n== NapNeko/NapCatQQ ==\nstars=${j.stargazers_count} pushed=${String(j.pushed_at).slice(0,10)} archived=${j.archived}`);
  } catch (e) { console.log('NapCatQQ FAILED', e.message); }

  // 5. 搜索 Shamrock xposed 更高星
  const s3 = await api('/search/repositories?q=Shamrock+Xposed&sort=stars&order=desc&per_page=10');
  console.log('\n== search Shamrock Xposed ==');
  for (const it of s3.items.slice(0, 8)) {
    console.log(`${it.full_name} | stars=${it.stargazers_count} | fork=${it.fork} | pushed=${String(it.pushed_at).slice(0,10)} | ${it.description ? it.description.slice(0,70) : ''}`);
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
