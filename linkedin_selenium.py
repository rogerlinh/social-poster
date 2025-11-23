#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn article publishing via Selenium
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


def _log(message: str) -> None:
    caller = inspect.currentframe().f_back  # type: ignore[assignment]
    line = caller.f_lineno if caller else -1
    pid = os.getpid()
    formatted = f"[pid {pid:>6}] [line {line:04d}] {message}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        sys.stdout.buffer.write((formatted + "\n").encode(encoding, errors="replace"))
        sys.stdout.flush()
    except Exception:
        print(formatted)


def linkedin_publish_article_selenium(
    driver: webdriver.Chrome,
    title: str,
    description: str,
    content: str,
    image_path: str = None,
) -> Optional[str]:
    """
    Publish an article to LinkedIn via Selenium.
    
    Args:
        driver: Selenium WebDriver instance
        title: Article title
        description: Article description
        content: Article content
        image_path: Optional path to article image
    
    Returns:
        Published article URL or None if failed
    """
    try:
        _log("Điều hướng đến trang xuất bản bài viết LinkedIn...")
        driver.set_page_load_timeout(15)  # Set 15 second timeout for page load
        driver.get("https://www.linkedin.com/article/new/")
        time.sleep(2)
        
        # Check current URL
        current_url = driver.current_url
        _log(f"URL hiện tại sau get: {current_url}")
        
        # Kiểm tra nếu là about:blank, có thể page chưa load xong
        if current_url == "about:blank":
            _log("CẢNH_BÁO:URL_LÀ_ABOUT_BLANK chờ page load...")
            time.sleep(2)
            current_url = driver.current_url
            _log(f"URL sau chờ thêm: {current_url}")
        
        if "/article" not in current_url and current_url != "about:blank":
           return None
        
        _log("BƯỚC:LINKEDIN_UPLOAD_HÌNH_ẢNH bắt đầu tải hình ảnh...")
        image_uploaded = upload_article_cover_image(driver, image_path)
        if image_uploaded:
            _log("BƯỚC:LINKEDIN_HÌNH_ẢNH_ĐÃ_TẢI hình ảnh được tải lên thành công")
            
            # Nhấp nút Next sau khi upload xong
            _log("BƯỚC:LINKEDIN_NHẤP_NÚT_NEXT nhấp nút Next...")
            if click_next_button(driver):
                _log("BƯỚC:LINKEDIN_NÚT_NEXT_ĐÃ_NHẤP nút Next được nhấp thành công")
            else:
                _log("CẢNH_BÁO:LINKEDIN_NHẤP_NÚT_NEXT_THẤT_BẠI nhấp nút Next thất bại, tiếp tục...")
        else:
            _log("CẢNH_BÁO:LINKEDIN_TẢI_HÌNH_ẢNH_THẤT_BẠI tải hình ảnh thất bại, tiếp tục...")
        
        input("Nhấn Enter để tiếp tục...")

        _log("BƯỚC:LINKEDIN_ĐIỀN_TIÊU_ĐỀ bắt đầu điền tiêu đề...")
        title_filled = fill_article_title(driver, title)
        if title_filled:
            _log("BƯỚC:LINKEDIN_TIÊU_ĐỀ_ĐÃ_ĐIỀN tiêu đề được điền thành công")
        else:
            _log("CẢNH_BÁO:LINKEDIN_ĐIỀN_TIÊU_ĐỀ_THẤT_BẠI điền tiêu đề thất bại, tiếp tục...")
        
        _log("Xuất bản bài viết LinkedIn hiện chưa được hỗ trợ - tính năng chưa được triển khai")
        return None
        
    except TimeoutException as e:
        _log(f"CẢNH_BÁO:LINKEDIN_XUẤT_BẢN_TIMEOUT err={e}")
        return None
    except WebDriverException as e:
        _log(f"CẢNH_BÁO:LINKEDIN_XUẤT_BẢN_LỖI_WEBDRIVER err={e}")
        return None
    except Exception as e:
        _log(f"LỖI:LINKEDIN_XUẤT_BẢN_THẤT_BẠI err={e}")
        return None


def click_next_button(driver: webdriver.Chrome) -> bool:
    """
    Nhấp nút Next sau khi upload hình ảnh.
    
    Args:
        driver: Selenium WebDriver instance
    
    Returns:
        True nếu nhấp nút thành công, False nếu thất bại
    """
    try:
        _log("Tìm nút Next...")
        wait = WebDriverWait(driver, 10)
        
        # Tìm button Next - có aria-label hoặc text "Next"
        next_button_selectors = [
            "button[aria-label='Next']",
            "button:contains('Next')",
            "button[id*='next' i]",
            ".share-box-footer button[aria-label*='Next' i]",
        ]
        
        next_button = None
        for selector in next_button_selectors:
            try:
                # CSS_SELECTOR không support :contains, nên skip
                if ":contains" in selector:
                    continue
                    
                next_button = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                _log(f"Tìm thấy nút Next với selector: {selector}")
                break
            except TimeoutException:
                _log(f"Không tìm thấy nút Next với selector: {selector}")
                continue
        
        # Nếu không tìm được, thử tìm button chứa text "Next"
        if next_button is None:
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "Next" in (btn.text or ""):
                        next_button = btn
                        _log("Tìm thấy nút Next bằng text search")
                        break
            except:
                pass
        
        if next_button is None:
            _log("CẢNH_BÁO:NÚT_NEXT_KHÔNG_TÌM_THẤY hết thời gian chờ nút Next")
            return False
        
        # Nhấp nút Next
        try:
            next_button.click()
            _log("Đã nhấp nút Next")
            time.sleep(1)  # Chờ page chuyển
            return True
        except Exception as e:
            _log(f"CẢNH_BÁO:NHẤP_NÚT_NEXT_THẤT_BẠI err={e}")
            return False
            
    except Exception as e:
        _log(f"LỖI:CLICK_NEXT_THẤT_BẠI err={e}")
        return False


def wait_for_upload_image(driver: webdriver.Chrome, timeout: float = 10, poll: float = 0.3) -> bool:
    """
    Đợi dấu hiệu hình ảnh đã tải lên thành công:
      1) Có img element được hiển thị
      2) Có div background-image chứa blob:/data:image (preview)
      3) Có aria-label chứa 'uploaded' hoặc tương tự
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Thời gian chờ tối đa (giây)
        poll: Tần suất kiểm tra (giây)
    
    Returns:
        True nếu upload thành công, False nếu timeout
    """
    try:
        _log(f"Đợi dấu hiệu upload xong (timeout={timeout}s)...")
        
        wait = WebDriverWait(
            driver, timeout,
            poll_frequency=poll,
            ignored_exceptions=(Exception,)
        )
        
        # Kiểm tra một trong các điều kiện
        def check_upload_complete(d):
            # 1) Kiểm tra img element
            try:
                img_elems = d.find_elements(By.CSS_SELECTOR, "img[alt*='image'], img[src*='blob'], img[src*='data:image']")
                if img_elems:
                    _log(f"Tìm thấy img element: {len(img_elems)} cái")
                    return True
            except:
                pass
            
            # 2) Kiểm tra div background-image
            try:
                divs = d.find_elements(By.CSS_SELECTOR, "div[style*='background-image']")
                for div in divs:
                    style = (div.get_attribute("style") or "").lower()
                    if "blob:" in style or "data:image" in style:
                        _log("Tìm thấy div background-image với blob/data URI")
                        return True
            except:
                pass
            
            # 3) Kiểm tra aria-label
            try:
                ui_elems = d.find_elements(By.CSS_SELECTOR, "[aria-label*='uploaded'], [aria-label*='Uploaded']")
                if ui_elems:
                    label = ui_elems[0].get_attribute("aria-label")
                    _log(f"Tìm thấy aria-label: {label}")
                    return True
            except:
                pass
            
            return False
        
        result = wait.until(check_upload_complete)
        _log("Hình ảnh được xác nhận upload thành công")
        return result
        
    except TimeoutException:
        _log(f"CẢNH_BÁO:UPLOAD_TIMEOUT hết thời gian {timeout}s chờ hình ảnh")
        return False
    except Exception as e:
        _log(f"CẢNH_BÁO:WAIT_UPLOAD_FAILED err={e}")
        return False


def upload_article_cover_image(driver: webdriver.Chrome, image_path: str) -> bool:
    """
    Upload cover image for LinkedIn article.
    
    Args:
        driver: Selenium WebDriver instance
        image_path: Path to the image file to upload
    
    Returns:
        True if upload successful, False otherwise
    """
    if not image_path or not os.path.exists(image_path):
        _log(f"CẢNH_BÁO:HÌNH_ẢNH_KHÔNG_TÌM_THẤY image_path={image_path}")
        return False
    
    try:
        _log(f"Tải lên hình ảnh bìa: {image_path}")
        
        wait = WebDriverWait(driver, 10)
        
        # Tìm file input trực tiếp (không cần nhấp button)
        def find_file_input():
            # Ưu tiên input nhận image
            js = """
                const candidates = Array.from(document.querySelectorAll("input[type='file']"));
                return candidates.map(el => ({
                    accept: el.getAttribute('accept') || '',
                    hidden: el.getAttribute('hidden') !== null,
                    ariaHidden: el.getAttribute('aria-hidden') !== null,
                    selector: el.outerHTML.slice(0, 120)
                }));
            """
            try:
                found = driver.execute_script(js)
                _log(f"Tìm thấy {len(found)} input[type=file] qua JS")
            except Exception:
                found = []
            # # Nếu có input và nó là sibling của button upload, log thêm
            # try:
            #     btn = driver.find_element(By.CSS_SELECTOR, ".article-editor-cover-media__placeholder-upload-buttons button")
            #     sib_input = btn.find_element(By.XPATH, "following-sibling::input[@type='file']")
            #     if sib_input:
            #         return sib_input
            # except Exception:
            #     pass
            # Dùng DOM tìm cụ thể
            file_input_selectors = [
                ".article-editor-cover-media__placeholder-upload-buttons input[type='file']",
                "button[aria-label*='Upload from computer' i] + input[type='file']",
                "button[aria-label*='Upload' i] + input[type='file']",
                "input[type='file'][aria-label*='Upload' i]",
                "input[type='file'][accept*='image']",
                "input[type='file'][data-test-id*='upload']",
                "input[type='file']",
            ]
            for selector in file_input_selectors:
                try:
                    el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    return el
                except TimeoutException:
                    continue
            return None

        file_input = find_file_input()

        if file_input is None:
            _log("CẢNH_BÁO:FILE_INPUT_KHÔNG_TÌM_THẤY hết thời gian chờ file input")
            return False
        
        # Làm visible file input để có thể send_keys
        try:
            driver.execute_script("""
                const el = arguments[0];
                el.style.display = 'block';
                el.style.opacity = '1';
                el.style.position = 'fixed';
                el.style.left = '10px';
                el.style.top = '10px';
                el.style.width = '200px';
                el.style.height = '40px';
                el.style.zIndex = '999999';
                el.removeAttribute('hidden');
                el.removeAttribute('aria-hidden');
            """, file_input)
            _log("Làm visible file input")
        except Exception as e:
            _log(f"CẢNH_BÁO:LÀM_VISIBLE_THẤT_BẠI err={e}")
        
        # Gửi file path đến input
        try:
            abs_path = os.path.abspath(image_path)
            file_input.send_keys(abs_path)
            _log(f"Gửi file: {abs_path}")
        except Exception as e:
            _log(f"LỖI:GỬI_PHÍM_THẤT_BẠI err={e}")
            return False
        
        # Đợi upload xong
        if not wait_for_upload_image(driver, timeout=10):
            _log("CẢNH_BÁO:KH\u00d4NG_XÁC_NHẬN_UPLOAD_XONG")
            return False
        
        _log("Hình ảnh được tải lên thành công")
        return True
        
    except Exception as e:
        _log(f"LỖI:TẢI_LÊN_THẤT_BẠI err={e}")
        return False


def fill_article_title(driver: webdriver.Chrome, title: str) -> bool:
    """
    Fill in the article title on LinkedIn article editor.
    
    Args:
        driver: Selenium WebDriver instance
        title: Article title text (max 150 characters)
    
    Returns:
        True if title filled successfully, False otherwise
    """
    if not title or not isinstance(title, str):
        _log("CẢNH_BÁO:TIÊU_ĐỀ_TRỐNG hoặc tiêu đề không hợp lệ")
        return False
    
    if len(title) > 150:
        _log(f"CẢNH_BÁO:TIÊU_ĐỀ_QUÁ_DÀI cắt ngắn từ {len(title)} xuống 150 ký tự")
        title = title[:150]
    
    try:
        _log(f"Điền tiêu đề bài viết: {title}")
        
        # Find title textarea using the selector from the HTML
        title_textarea_selector = "#article-editor-headline__textarea"
        
        try:
            title_textarea = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, title_textarea_selector))
            )
            _log("Tìm thấy textarea tiêu đề")
        except TimeoutException:
            _log("CẢNH_BÁO:TEXTAREA_TIÊU_ĐỀ_KHÔNG_TÌM_THẤY hết thời gian chờ textarea tiêu đề")
            return False
        
        # Click textarea to focus
        try:
            title_textarea.click()
            _log("Đã nhấp textarea tiêu đề")
        except Exception as e:
            _log(f"CẢNH_BÁO:NHẤP_TEXTAREA_TIÊU_ĐỀ_THẤT_BẠI err={e}")
        
        time.sleep(0.5)
        
        # Clear any existing text
        # try:
        #     title_textarea.clear()
        #     _log("Cleared existing title text")
        # except Exception as e:
        #     _log(f"WARN:TITLE_CLEAR_FAILED err={e}")
        
        # Type title character by character for better compatibility
        try:
            for char in title:
                title_textarea.send_keys(char)
                time.sleep(0.02)  # Small delay between characters
            _log(f"Tiêu đề được nhập thành công: {title}")
        except Exception as e:
            _log(f"LỖI:GỬI_PHÍM_TIÊU_ĐỀ_THẤT_BẠI err={e}")
            return False
        
        time.sleep(0.5)
        
        # Check actual value in textarea after sending
        try:
            actual_value = title_textarea.get_attribute("value")
            text_content = title_textarea.text
            _log(f"Giá trị thuộc tính textarea: {actual_value}")
            _log(f"Nội dung văn bản textarea: {text_content}")
            
            if actual_value:
                _log(f"Tiêu đề được xác nhận trong textarea: {actual_value}")
            elif text_content:
                _log(f"Tiêu đề được xác nhận trong textarea: {text_content}")
            else:
                _log(f"CẢNH_BÁO:TIÊU_ĐỀ_KHÔNG_CÓ_TRONG_TEXTAREA mong đợi '{title}' nhưng textarea trống")
        except Exception as e:
            _log(f"CẢNH_BÁO:KIỂM_TRA_TIÊU_ĐỀ_THẤT_BẠI err={e}")
        
        _log("Tiêu đề được điền thành công")
        return True
        
    except Exception as e:
        _log(f"LỖI:ĐIỀN_TIÊU_ĐỀ_THẤT_BẠI err={e}")
        return False


def main() -> None:
    """Test script for LinkedIn article publishing"""
    from gpm_profile import find_or_create_profile, start_profile, start_profile_api
    
    _log("Starting LinkedIn Selenium test script...")
    
    # Configuration
    profile_name = "Linkedin-hanguyen"
    title = "Test Article for LinkedIn"
    description = "This is a test article description"
    content = "This is test content for LinkedIn article publishing via Selenium."
    image_path = r"C:\Users\Admin\Downloads\Experience special tours from VietnamStory.png"
    driver = None
    try:
        # Find or use existing profile
        _log(f"Looking for GPM Login profile: {profile_name}")
        profile = find_or_create_profile(profile_name, create_if_missing=False)
        
        if profile is None:
            _log(f"ERROR: Profile '{profile_name}' not found. Please create it in GPM Login app.")
            return
        
        profile_id = profile.get('id')
        _log(f"Found profile: {profile_name} (ID: {profile_id})")
        
        # Start profile and get WebDriver
        _log("Launching Chrome via GPM Login API...")
        driver = start_profile_api(
            profile_id=profile_id,
            win_width=1280,
            win_height=720,
            pos_x=300,
            pos_y=300,
            retry_attempts=3
        )
        
        if driver is None:
            _log("ERROR: Failed to launch Chrome via GPM Login API")
            return
        time.sleep(2)
        _log("WebDriver ready. Testing LinkedIn publishing...")
        
        # Test LinkedIn publishing directly (skip chrome://version check)

        # Test LinkedIn publishing
        result = linkedin_publish_article_selenium(
            driver=driver,
            title=title,
            description=description,
            content=content,
            image_path=image_path,
        )
        
        if result:
            _log(f"SUCCESS: Article published at {result}")
        else:
            _log("INFO: LinkedIn publishing is currently unsupported (feature not yet implemented)")
        
    except Exception as e:
        _log(f"ERROR:TEST_FAILED err={e.__class__.__name__}: {e}")
    
    finally:
        if driver is not None:
            _log("Closing browser window...")
            try:
                input("stop")
                driver.quit()
            except Exception as e:
                _log(f"WARN:DRIVER_QUIT_FAILED err={e}")


if __name__ == "__main__":
    main()
