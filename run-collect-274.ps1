# run-collect-274.ps1 — 启动收集器（账号 2740088195 → 群 826904606 + 762673304）
# 路径自动推导：以本脚本所在目录为工程根，无需硬编码盘符
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
Set-Location $Root
$env:QQBOT_CONFIG = Join-Path $Root 'config\config-274-main.json'
Write-Host "收集器启动: 2740088195 → 群 826904606, 762673304 (工程根: $Root)"
node src/index.js
