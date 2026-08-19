// 从 napneko.github.io 仓库拿安装文档
const tree = await (await fetch('https://api.github.com/repos/NapNeko/napneko.github.io/git/trees/main?recursive=1', { headers: { 'User-Agent': 'research' } })).json();
const md = (tree.tree ?? []).filter((t) => t.path.endsWith('.md')).map((t) => t.path);
console.log('全部 md:', md.join('\n'));
