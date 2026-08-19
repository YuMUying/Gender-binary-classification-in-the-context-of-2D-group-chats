@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist node_modules (
  echo [首次运行] 安装依赖...
  call npm install
)
node src\index.js
pause
