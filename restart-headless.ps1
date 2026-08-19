# restart-headless.ps1 — 无窗口重启 QQ（不显示 QQ 主窗口，避免黑屏/窗口唤醒冲突）
# 登录二维码通过 NapCat WebUI (6099) 查看，扫码无需 QQ 主窗口
$ErrorActionPreference = 'Continue'

Write-Host '1) Killing QQ / BootMain ...'
Get-Process QQ, QQEX, NapCatWinBootMain -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$env:NAPCAT_PATCH_PACKAGE = 'D:\Program Files (x86)\Tencent\NapCat\napcat\qqnt.json'
$env:NAPCAT_LOAD_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\loadNapCat.js'
$env:NAPCAT_INJECT_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootHook.dll'
$env:NAPCAT_LAUNCHER_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootMain.exe'
$env:NAPCAT_MAIN_PATH = 'D:/Program Files (x86)/Tencent/NapCat/napcat/napcat.mjs'

Write-Host '2) Starting BootMain (headless, no window shown) ...'
Start-Process -FilePath 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootMain.exe' `
  -ArgumentList '"D:\Program Files (x86)\Tencent\QQ.exe" "D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootHook.dll"' `
  -WorkingDirectory 'D:\Program Files (x86)\Tencent\NapCat\napcat'

Write-Host '3) Done. 登录二维码请在 WebUI 查看: http://127.0.0.1:6099 (token: napcat2026)'
