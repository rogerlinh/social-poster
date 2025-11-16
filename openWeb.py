import time, subprocess, shlex, os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
import psutil

def launch_profile_browser(profile_path: str, chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe") -> subprocess.Popen:
    """Open a Chrome window pointing at the given profile directory (creating it if missing)."""
    profile_dir = Path(profile_path).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise RuntimeError(f"Unable to open Chrome with profile {profile_dir}: {exc}") from exc
    return proc
def start_debug_with_powershell(
    chrome_path: str,
    user_data_dir: str,
    profile_name: str,
    port: int = 9333,
    lang: str = "en-US,en",
    skip_if_profile_exists: bool = True,
):
    """
    Mở Chrome (PowerShell) ở chế độ remote-debug và trả về PID.
    - Nếu skip_if_profile_exists=True và profile đã tồn tại, KHÔNG mở, log và trả về None.
    """
    # Chuẩn hoá đường dẫn
    user_data_dir = str(Path(user_data_dir).resolve())
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    # Thư mục profile con: user_data_dir/<profile_name>
    profile_dir = Path(user_data_dir) / profile_name
    profile_exists = profile_dir.is_dir() and any(
        (profile_dir / marker).exists()
        for marker in ("Preferences", "History", "Cookies", "Bookmarks")
    )

    if skip_if_profile_exists and profile_exists:
        print(f"[PS] Profile đã tồn tại: {profile_dir}")
        print(f"[PS] Bỏ qua mở Chrome debug mới. (skip_if_profile_exists=True)")
        return None  # không mở → không có PID

    # PowerShell: Start-Process ... -PassThru để lấy PID
    # Lưu ý quote path trong tham số Chrome (đề phòng dấu cách)
    arg_list = (
        f'"--remote-debugging-port={port}",'
        f'"--user-data-dir={user_data_dir}",'
        f'"--profile-directory={profile_name}",'
        f'"--no-first-run","--no-default-browser-check","--new-window","--lang={lang}"'
    )
    ps_cmd = (
        f'Start-Process -FilePath "{chrome_path}" '
        f'-ArgumentList @({arg_list}) '
        f'-PassThru | Select-Object -ExpandProperty Id'
    )

    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[PS] ❌ Lỗi chạy PowerShell: {e.stderr or e.stdout}")
        raise

    pid_str = (r.stdout or "").strip()
    if not pid_str.isdigit():
        raise RuntimeError(f"Không lấy được PID từ PowerShell. Output: {r.stdout!r} {r.stderr!r}")

    pid = int(pid_str)
    print(f"[PS] ✅ Đã mở Chrome debug (port {port}) | PID = {pid}")
    return pid

def kill_process_tree(pid: int):
    """Dừng tiến trình Chrome vừa mở (và con của nó) trên Windows."""
    # taskkill để đảm bảo diệt cả cây tiến trình
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[PS] Đã kill PID {pid}")

def open_chrome_with_selenium(user_data_dir, profile_name="Default", lang="en-US,en"):
    """Mở Chrome bằng Selenium với cùng hồ sơ (KHÔNG attach)."""
    opts = ChromeOptions()
    opts.add_argument(f"--user-data-dir={str(Path(user_data_dir).resolve())}")
    opts.add_argument(f"--profile-directory={profile_name}")
    opts.add_argument(f"--lang={lang}")
    # (tuỳ chọn) giảm dấu hiệu automation:
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    return driver

def open_headless_selenium(user_data_dir: str, profile_name: str="Default", lang: str="en-US,en"):
    opts = ChromeOptions()
    opts.add_argument(f"--user-data-dir={str(Path(user_data_dir).resolve())}")
    opts.add_argument(f"--profile-directory={profile_name}")
    opts.add_argument(f"--lang={lang}")
    # Headless + tiết kiệm tài nguyên
    # opts.add_argument("--headless=new")     # hoặc "--headless"
    # opts.add_argument("--disable-gpu")
    # opts.add_argument("--disable-extensions")
    # opts.add_argument("--disable-background-networking")
    # opts.add_argument("--disable-sync")
    # opts.add_argument("--mute-audio")
    # Giảm tải nội dung (tắt ảnh & thông báo)
    # prefs = {
    #     "profile.managed_default_content_settings.images": 2,
    #     "profile.default_content_setting_values.notifications": 2,
    #     "credentials_enable_service": False,
    #     "profile.password_manager_enabled": False,
    # }
    # opts.add_experimental_option("prefs", prefs)
    # (tuỳ chọn) giảm dấu hiệu automation
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = webdriver.Chrome(options=opts)

    # ===== LOG xác nhận đã mở =====
    try:
        cd_pid = driver.service.process.pid
        print(f"[OK] chromedriver PID = {cd_pid}")
    except Exception as e:
        print(f"[WARN] Không lấy được chromedriver PID: {e}")

    # Tìm PID Chrome theo user-data-dir (cần psutil, nếu có)
    try:
        import psutil, os
        ud = str(Path(user_data_dir).resolve())
        procs = psutil.Process(cd_pid).children(recursive=True) if 'cd_pid' in locals() else psutil.process_iter()
        chrome_pids = []
        for p in procs:
            try:
                name = p.name().lower()
                if "chrome" in name:
                    cmd = " ".join(p.cmdline()).lower()
                    if f"--user-data-dir={ud.lower()}" in cmd:
                        chrome_pids.append(p.pid)
            except Exception:
                pass
        if chrome_pids:
            print(f"[OK] chrome PID = {chrome_pids[0]}")
        else:
            print("[INFO] Không xác định được chrome PID (không cài psutil hoặc lệnh cmdline bị hạn chế).")
    except Exception as e:
        print(f"[INFO] Bỏ qua dò chrome PID: {e}")

    # CDP ping để chắc chắn browser sẵn sàng
    try:
        info = driver.execute_cdp_cmd("Browser.getVersion", {})
        print(f"[OK] Chrome {info.get('product','?')} | UA={info.get('userAgent','?')[:60]}...")
    except Exception as e:
        print(f"[OK] Chrome đã mở (CDP ping lỗi nhẹ: {e})")

    return driver

def open_debug_then_restart_with_selenium(
    user_data_dir: str,
    profile_name: str = "Profile 1",
    port: int = 9333,
    lang: str = "en-US,en",
    sleep_seconds: float = 2.0,
    chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe",
):
    """
    1) Mở Chrome debug bằng PowerShell
    2) Ngủ `sleep_seconds`
    3) Tắt phiên debug
    4) Mở lại Chrome bằng Selenium (KHÔNG attach) với cùng dữ liệu hồ sơ
    """
    print("[step] Mở Chrome debug bằng PowerShell…")
    pid = start_debug_with_powershell(chrome_path, user_data_dir, profile_name, port=port, lang=lang)

    # print(f"[step] Ngủ {sleep_seconds}s…")
    # time.sleep(sleep_seconds)
    if pid:
        print("[step] Tắt phiên debug vừa mở…")
        kill_process_tree(pid)
    time.sleep(sleep_seconds)
    print("[step] Mở lại bằng Selenium (không attach)…")
    drv = open_chrome_with_selenium(user_data_dir, profile_name, lang)
    # drv = open_headless_selenium(user_data_dir, profile_name, lang)
    return drv

# ---------- Ví dụ dùng ----------
if __name__ == "__main__":
    USER_DATA_DIR = r"C:\Selenium\ChromeProfiles\tester3"  # THƯ MỤC RIÊNG
    PROFILE_NAME  = "Default"                              # 'Default' hoặc 'Profile 1', 'Profile 2', ...

    driver = open_debug_then_restart_with_selenium(
        user_data_dir=USER_DATA_DIR,
        profile_name=PROFILE_NAME,
        port=9406,                 # cổng debug tạm
        sleep_seconds=2.0,
    )
    driver.get("chrome://version/")
    time.sleep(5)
    print(">> Selenium đã mở lại Chrome với cùng hồ sơ. Kiểm tra 'Profile Path' trong trang để xác nhận.")
    input("press any keys to exit")
