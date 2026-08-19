// UTF-16LE 字符串扫描
import { readFileSync } from 'node:fs';
const buf = readFileSync('C:/Users/Lenovo/Downloads/qq-bot-deploy/onekey/NapCatInstaller.exe');
const text = buf.toString('utf16le');
const strings = text.match(/[\u0020-\u007e\u4e00-\u9fff]{6,}/g) ?? [];
const hits = strings.filter((s) => /\.exe|dldir|gtimg|QQNT|https?:|QQ9|一键|下载/i.test(s));
const uniq = [...new Set(hits)];
console.log('UTF16 命中:', uniq.length);
for (const s of uniq.slice(0, 80)) console.log(s);
