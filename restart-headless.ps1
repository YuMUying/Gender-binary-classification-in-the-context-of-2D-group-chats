# restart-headless.ps1 — 无窗口重启 QQ + NapCat（通用版，路径自动推导，可随目录整体迁移）
#
# QQBot 根查找顺序（首个命中者生效）：
#   1. 环境变量 $env:QQBOT_ROOT（显式指定，最灵活）
#   2. 与本工程同级的 QQ_bot/ 目录（迁移部署：把 qq-gender-dataset 与 QQ_bot 放同一根下）
#   3. 回退 H:\QQ_bot（当前机器部署位置）
#
# 登录二维码通过 NapCat WebUI (6099) 查看，扫码无需 QQ 主窗口
$ErrorActionPreference = 'Continue'

# ---- QQBot 根解析 ----
function Resolve-QQBotRoot {
  if ($env:QQBOT_ROOT -and (Test-Path $env:QQBOT_ROOT)) { return $env:QQBOT_ROOT }
  $sibling = Join-Path (Split-Path -Parent $PSScriptRoot) 'QQ_bot'
  if (Test-Path $sibling) { return $sibling }
  if (Test-Path 'H:\QQ_bot') { return 'H:\QQ_bot' }
  return $null
}

$QQBot = Resolve-QQBotRoot
if (-not $QQBot) {
  Write-Error '无法定位 QQ_bot 根目录：请设置环境变量 QQBOT_ROOT，或将 QQ_bot 放到本工程同级目录'
  exit 1
}
$QQExe = Join-Path $QQBot 'QQ\QQ.exe'
$NapCatNap = Join-Path $QQBot 'NapCat\napcat'

if (-not (Test-Path $QQExe) -or -not (Test-Path $NapCatNap)) {
  Write-Error "未找到 QQ/NapCat: 期望 <QQBot>/QQ/QQ.exe 与 <QQBot>/NapCat/napcat，当前 QQBot=$QQBot"
  exit 1
}

Write-Host "QQBot 根: $QQBot"
Write-Host '1) Killing QQ / BootMain ...'
Get-Process QQ, QQEX, NapCatWinBootMain -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$env:NAPCAT_PATCH_PACKAGE = Join-Path $NapCatNap 'qqnt.json'
$env:NAPCAT_LOAD_PATH = Join-Path $NapCatNap 'loadNapCat.js'
$env:NAPCAT_INJECT_PATH = Join-Path $NapCatNap 'NapCatWinBootHook.dll'
$env:NAPCAT_LAUNCHER_PATH = Join-Path $NapCatNap 'NapCatWinBootMain.exe'
$env:NAPCAT_MAIN_PATH = (Join-Path $NapCatNap 'napcat.mjs').Replace('\', '/')

Write-Host '2) Starting BootMain (headless, no window shown) ...'
Start-Process -FilePath (Join-Path $NapCatNap 'NapCatWinBootMain.exe') `
  -ArgumentList "`"$QQExe`" `"$(Join-Path $NapCatNap 'NapCatWinBootHook.dll')`"" `
  -WorkingDirectory $NapCatNap

Write-Host '3) Done. 登录二维码请在 WebUI 查看: http://127.0.0.1:6099 (token: napcat2026)'
