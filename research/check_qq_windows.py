# -*- coding: utf-8 -*-
"""check_qq_windows.py — 枚举 QQ 进程的所有窗口标题"""
import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowTextW = user32.GetWindowTextW
GetClassNameW = user32.GetClassNameW
IsWindowVisible = user32.IsWindowVisible

qq_pids = set()
import subprocess
out = subprocess.run(['powershell', '-Command', "(Get-Process QQ -ErrorAction SilentlyContinue).Id"], capture_output=True, text=True)
for line in out.stdout.split():
    try:
        qq_pids.add(int(line.strip()))
    except ValueError:
        pass
print('QQ PIDs:', qq_pids)

windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, lparam):
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in qq_pids:
        buf = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, buf, 512)
        cls = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, cls, 256)
        visible = IsWindowVisible(hwnd)
        windows.append((hwnd, pid.value, buf.value[:80], cls.value, visible))
    return True

EnumWindows(cb, 0)
print(f'\nQQ 窗口数: {len(windows)}')
for h, pid, title, cls, vis in windows:
    print(f'  hwnd={h} pid={pid} visible={vis} class={cls} title=[{title}]')
