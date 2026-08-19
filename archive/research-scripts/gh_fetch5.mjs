const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null };
}
async function getText(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 research' } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}

async function main() {
  // 1. gitcode 镜像的 raw README
  const r1 = await getText('https://raw.gitcode.com/gh_mirrors/op/OpenShamrock/master/README.md');
  console.log(`== gitcode raw README status=${r1.status} ==`);
  if (r1.ok) console.log(r1.text.split('\n').slice(0, 110).join('\n'));

  // 2. 一键安装脚本仓库 README（看它从哪里下载 APK）
  const r2 = await getText('https://raw.githubusercontent.com/YuYue-Amatsuki/OpenShamrock_Oneclick_Install_Upgrade/main/README.md');
  console.log(`\n== Oneclick README status=${r2.status} ==`);
  if (r2.ok) console.log(r2.text.split('\n').slice(0, 60).join('\n'));
  else {
    // 试 master 分支
    const r2b = await getText('https://raw.githubusercontent.com/YuYue-Amatsuki/OpenShamrock_Oneclick_Install_Upgrade/master/README.md');
    if (r2b.ok) console.log(r2b.text.split('\n').slice(0, 60).join('\n'));
  }

  // 3. 搜索还在活跃的 QQ Xposed/OneBot 模块
  const s = await api('/search/repositories?q=QQ+Xposed+OneBot&sort=updated&order=desc&per_page=10');
  console.log('\n== search QQ Xposed OneBot (按更新排序) ==');
  if (s.json) for (const it of s.json.items.slice(0, 8)) {
    console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,70)}`);
  }

  // 4. XiaoMiku01/Shamrock 是否还有 releases
  const x = await api('/repos/XiaoMiku01/Shamrock/releases/latest');
  console.log('\n== XiaoMiku01/Shamrock latest release ==');
  if (x.json) console.log(`tag=${x.json.tag_name} published=${String(x.json.published_at).slice(0,10)} assets=${x.json.assets.map(a=>a.name).join(',')}`);
  else console.log('status', x.status);
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
