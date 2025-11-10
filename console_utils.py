# console_utils.py
import os, sys

import os, sys

def ensure_own_console(title: str | None = None, *, verbose: bool = True) -> bool:
    """Tách khỏi console cha và mở 1 console mới cho process hiện tại. Trả về True nếu OK."""
    if os.name != "nt":
        if verbose:
            print("[console] Bỏ qua: hệ điều hành không phải Windows.")
        return False

    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32",   use_last_error=True)

    # Lưu handle console (nếu có) trước khi tách
    try:
        get_console_win = k32.GetConsoleWindow
    except AttributeError:
        get_console_win = None
    prev_hwnd = get_console_win() if get_console_win else 0

    # Tách + xin console mới
    k32.FreeConsole()
    ok = k32.AllocConsole()
    if not ok:
        err = ctypes.get_last_error()
        if verbose:
            print(f"[console] ❌ AllocConsole FAILED, last_error={err}")
        return False

    # Đặt tiêu đề & đảm bảo hiển thị
    if title:
        k32.SetConsoleTitleW(str(title))
    hwnd = get_console_win() if get_console_win else 0
    if hwnd:
        # Hiện/đưa ra trước (nếu đang minimize/ẩn)
        SW_RESTORE = 9
        u32.ShowWindow(hwnd, SW_RESTORE)
        u32.SetForegroundWindow(hwnd)

    # Rebind I/O sang console mới
    sys.stdin  = open("CONIN$",  "r", encoding="utf-8", buffering=1)
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)

    # LOG xác nhận – lúc này log xuất ra console MỚI
    if verbose:
        print(f"[console] ✅ New console created")
        print(f"[console]     pid   = {os.getpid()}")
        print(f"[console]     hwnd  = 0x{hwnd:08X}" if hwnd else "[console]     hwnd  = 0x00000000")
        if title:
            print(f"[console]     title = {title!r}")
        print(f"[console]     prev  = 0x{prev_hwnd:08X}" if prev_hwnd else "[console]     prev  = 0x00000000")

    return bool(hwnd) and hwnd != prev_hwnd
