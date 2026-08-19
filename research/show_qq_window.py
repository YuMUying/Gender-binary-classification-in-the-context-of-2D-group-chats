# -*- coding: utf-8 -*-
"""show_qq_window.py — 显示 QQ 主窗口（用于登录扫码）"""
import ctypes
import ctypes.wintypes as wt
import subprocess

user32 = ctypes.windll.user32
out = subprocess.run(['powershell', '-Command', '(Get-Process QQ -ErrorAction SilentlyContinue).Id'],
                     capture_output=True, text=True)
pids = {int(x.strip()) for x in out.stdout.split() if x.strip().isdigit()}
print('QQ PIDs:', pids)
found = []

@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, l):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value in pids:
        buf = ctypes.create_unicode_buffer(512)
        user32.GetClassNameW(h, buf, 512)
        if buf.value == 'Chrome_WidgetWin_0':
            found.append(h)
    return True

user32.EnumWindows(cb, 0)
print('QQ 主窗口:', found)
for h in found:
    user32.ShowWindow(h, 5)
    user32.SetForegroundWindow(h)
    print(f'已显示 hwnd={h}')
