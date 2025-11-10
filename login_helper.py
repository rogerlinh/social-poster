import os
import asyncio
from playwright.async_api import async_playwright

CHROME_EXECUTABLE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    print("=== Social Poster - Login Helper ===")
    platform = input("Chọn nền tảng (LinkedIn/Medium): ").strip() or "LinkedIn"
    profile = input("Nhập đường dẫn Chrome Profile Folder: ").strip()
    if not profile:
        print("Thiếu profile folder.")
        return

    os.makedirs(profile, exist_ok=True)
    async with async_playwright() as p:
        launch_options = {
            "user_data_dir": profile,
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
            "locale": "vi-VN",
        }
        if os.path.exists(CHROME_EXECUTABLE_PATH):
            launch_options["executable_path"] = CHROME_EXECUTABLE_PATH

        context = await p.chromium.launch_persistent_context(**launch_options)
        page = await context.new_page()

        try:
            if platform.lower().startswith("link"):
                await page.goto("https://www.linkedin.com/login", timeout=180_000)
                print("Đã mở LinkedIn. Hãy đăng nhập trong cửa sổ trình duyệt...")
            else:
                await page.goto("https://medium.com/m/signin", timeout=180_000)
                print("Đã mở Medium. Hãy đăng nhập trong cửa sổ trình duyệt...")

            print("Giữ cửa sổ này mở. Nhấn Ctrl+C trong terminal để thoát khi đã đăng nhập xong.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nĐang đóng trình duyệt...")
        finally:
            await context.close()


if __name__ == "__main__":
    asyncio.run(main())

