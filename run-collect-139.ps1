# run-collect-139.ps1 — 启动收集器（账号 1394876195 → 群 723216773）
# 路径自动推导：以本脚本所在目录为工程根，无需硬编码盘符
# 注意: 139 号需先登录（restart-139.ps1），且需确认该号在 723216773 群中
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
Set-Location $Root
$env:QQBOT_CONFIG = Join-Path $Root 'config\config-group3.json'
Write-Host "收集器启动: 1394876195 → 群 723216773 (工程根: $Root)"
node src/index.js
