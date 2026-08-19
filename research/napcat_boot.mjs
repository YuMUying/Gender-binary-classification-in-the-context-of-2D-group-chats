// 扫描 NapCatWinBootMain.exe 字符串，找窗口/无头相关标志
import { readFileSync } from 'node:fs';
const buf = readFileSync('D:/Program Files (x86)/Tencent/NapCat/napcat/NapCatWinBootMain.exe');
for (const enc of ['latin1', 'utf16le']) {
  const text = buf.toString(enc);
  const strings = text.match(/[\x20-\x7e]{4,}/g) ?? [];
  const hits = strings.filter((s) => /headless|window|Window|enable-logging|SW_|hide|show|无头|--/i.test(s));
  console.log(`\n== ${enc} 命中 ==`);
  console.log([...new Set(hits)].slice(0, 40).join('\n'));
}
