// 检查 SJTU pytorch-wheels 镜像是否有 win_amd64 cu121
const urls = ['https://mirror.sjtu.edu.cn/pytorch-wheels/cu121/', 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu121/torch/'];
for (const u of urls) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const html = await r.text();
    const wins = [...html.matchAll(/torch-([\d.%2B+\w-]+)-cp310-cp310-win_amd64\.whl/g)].map((m) => decodeURIComponent(m[1]));
    console.log(u, '→', r.status, 'win310版本:', [...new Set(wins)].slice(-8).join(', ') || '(无)');
  } catch (e) { console.log(u, '→ ERR', e.message.slice(0, 60)); }
}
