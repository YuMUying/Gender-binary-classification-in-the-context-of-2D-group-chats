// 拉取官网 windowsConfig.js 拿最新 QQ 下载直链
const r = await fetch('https://cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow/windowsConfig.js', {
  headers: { 'User-Agent': 'Mozilla/5.0' },
});
const js = await r.text();
console.log('len:', js.length);
console.log(js.slice(0, 3000));
