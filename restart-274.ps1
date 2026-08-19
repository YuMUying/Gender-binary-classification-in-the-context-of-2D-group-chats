# restart-274.ps1 — 无窗口重启 QQ + NapCat（账号 2740088195）
# 路径自动推导（QQBOT_ROOT 环境变量 > 同级 QQ_bot > H:\QQ_bot），与 restart-headless.ps1 相同
$ErrorActionPreference = 'Continue'
& (Join-Path $PSScriptRoot 'restart-headless.ps1')
