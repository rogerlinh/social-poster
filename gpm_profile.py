#!/usr/bin/env python3
"""
GPM Login App Profile Management Module
Handles finding, creating, and starting profiles via GPM Login API
"""
import time
import requests
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from openWeb import open_chrome_with_selenium

try:
    from config import CHROME_USER_DATA_DIR, CHROME_PROFILE_DIR
except Exception:
    CHROME_USER_DATA_DIR = None
    CHROME_PROFILE_DIR = "Default"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "http://127.0.0.1:19995"


def get_profiles_list(base_url: str = BASE_URL):
    """Get list of all profiles from GPM Login API"""
    try:
        endpoint = "/api/v3/profiles"
        full_url = f"{base_url}{endpoint}"
        response = requests.get(full_url, timeout=5)
        
        if response.status_code != 200:
            logging.error(f"Failed to get profiles list. Status: {response.status_code}")
            return None
        
        data = response.json()
        if 'data' in data:
            logging.info(f"Found {len(data['data'])} profiles")
            return data['data']
        return None
    except Exception as e:
        logging.error(f"Error getting profiles list: {e}")
        return None


def find_profile_by_name(profile_name: str, base_url: str = BASE_URL):
    """Find a profile by name from the list of profiles"""
    profiles = get_profiles_list(base_url)
    
    if profiles is None:
        logging.error("Failed to get profiles list")
        return None
    
    for profile in profiles:
        if isinstance(profile, dict) and profile.get('name') == profile_name:
            logging.info(f"Found profile: {profile_name}")
            return profile
    
    logging.warning(f"Profile '{profile_name}' not found")
    return None


def create_profile(profile_name: str, custom_params=None, base_url: str = BASE_URL):
    """Create a new profile with given name"""
    try:
        endpoint = "/api/v3/profiles/create"
        full_url = f"{base_url}{endpoint}"
        
        # Default profile data
        profile_data = {
            "profile_name": profile_name,
            "group_name": "All",
            "browser_core": "chromium",
            "browser_name": "Chrome",
            "is_random_browser_version": False,
            "raw_proxy": "",
            "startup_urls": "",
            "is_masked_font": True,
            "is_noise_canvas": False,
            "is_noise_webgl": False,
            "is_noise_client_rect": False,
            "is_noise_audio_context": True,
            "is_random_screen": False,
            "is_masked_webgl_data": True,
            "is_masked_media_device": True,
            "is_random_os": False,
            "os": "Windows 11",
            "webrtc_mode": 2,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        
        # Update with custom parameters if provided
        if custom_params and isinstance(custom_params, dict):
            profile_data.update(custom_params)
        
        logging.info(f"Creating profile: {profile_name}")
        response = requests.post(full_url, json=profile_data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logging.info(f"Profile created successfully: {profile_name}")
                return data.get('data')
        
        logging.error(f"Failed to create profile: {response.status_code}")
        return None
    except Exception as e:
        logging.error(f"Error creating profile: {e}")
        return None


def find_or_create_profile(profile_name: str, custom_params=None, base_url: str = BASE_URL, create_if_missing: bool = False):
    """
    Find a profile by name, optionally create it if not found
    
    Args:
        profile_name: Name of the profile to find
        custom_params: Custom parameters for profile creation (if create_if_missing=True)
        base_url: Base URL của GPM Login API
        create_if_missing: If False, only find existing profile and don't create. Default is True.
    
    Returns:
        Profile object nếu found/created, None nếu not found and create_if_missing=False
    """
    logging.info(f"Finding profile: {profile_name}")
    
    # Try to find existing profile
    profile = find_profile_by_name(profile_name, base_url)
    
    if profile is not None:
        logging.info(f"Using existing profile: {profile_name}")
        return profile
    
    # Profile not found
    if not create_if_missing:
        logging.error(f"Profile '{profile_name}' not found and create_if_missing=False")
        return None
    
    # Create new profile if allowed
    logging.info(f"Profile not found. Creating new profile: {profile_name}")
    new_profile = create_profile(profile_name, custom_params, base_url)
    
    if new_profile is not None:
        logging.info(f"Profile created successfully!")
        return new_profile
    else:
        logging.error(f"Failed to create profile")
        return None


def get_profile_info(profile_id: str, base_url: str = BASE_URL) -> dict | None:
    """Fetch profile details from GPM Login API (per docs)."""
    try:
        url = f"{base_url}/api/v3/profiles/{profile_id}"
        logging.info(f"Fetching profile info from {url}")
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logging.warning(f"Profile info request failed: status={resp.status_code}")
            return None
        payload = resp.json()
        logging.info(f"Profile info raw payload: {payload}")
        data: dict | None = None
        if isinstance(payload, dict):
            raw = payload.get("data", payload.get("profile"))
            if isinstance(raw, list) and raw:
                data = raw[0] if isinstance(raw[0], dict) else None
            elif isinstance(raw, dict):
                data = raw
            elif data is None:
                data = payload if "success" not in payload else None
        if isinstance(data, dict):
            logging.info(f"Profile info data parsed: {data}")
            return data
        logging.warning("Profile info response missing profile data")
        return None
    except Exception as e:
        logging.warning(f"Error fetching profile info: {e}")
        return None


def start_profile(profile_id: str, win_width: int = 1280, win_height: int = 720,
                  pos_x=None, pos_y=None, retry_attempts: int = 3,
                  base_url: str = BASE_URL,
                  user_data_dir: str | None = None,
                  profile_name: str | None = None,
                  lang: str = "en-US,en"):
    """
    Start a Chrome profile (local user-data-dir) and return Selenium WebDriver.

    Lấy thông tin profile qua API (docs.gpmloginapp.com) để xác định
    user-data-dir/profile-name, sau đó mở Chrome bằng Selenium.
    """
    profile_info = get_profile_info(profile_id, base_url=base_url) or {}
    info_user_data_dir = (
        profile_info.get("user_data_dir")
        or profile_info.get("user_data_directory")
        or profile_info.get("userDataDir")
        or profile_info.get("userDataDirectory")
        or profile_info.get("profile_path")
        or profile_info.get("profilePath")
        or profile_info.get("path")
    )
    info_profile_name = profile_info.get("name") or profile_info.get("profile_name") or profile_info.get("profileName")

    resolved_user_data_dir = user_data_dir or info_user_data_dir or CHROME_USER_DATA_DIR
    resolved_profile_name = profile_name or info_profile_name or CHROME_PROFILE_DIR or profile_id

    if not resolved_user_data_dir:
        logging.error("user_data_dir is required to start Chrome (API did not return a path)")
        return None

    logging.info(
        f"Resolved profile launch: user_data_dir='{resolved_user_data_dir}', profile_name='{resolved_profile_name}', "
        f"profile_id={profile_id}"
    )

    for attempt in range(retry_attempts):
        try:
            logging.info(
                f"Starting Chrome profile '{resolved_profile_name}' from '{resolved_user_data_dir}' "
                f"(attempt {attempt + 1}/{retry_attempts}, profile_id={profile_id})..."
            )
            driver = open_chrome_with_selenium(
                user_data_dir=resolved_user_data_dir,
                profile_name=resolved_profile_name,
                lang=lang,
            )
            try:
                driver.set_window_size(win_width, win_height)
                if pos_x is not None and pos_y is not None:
                    driver.set_window_position(pos_x, pos_y)
            except Exception as e:
                logging.warning(f"Could not resize/reposition window: {e}")
            logging.info(f"Successfully started profile {resolved_profile_name}")
            return driver
        except Exception as e:
            logging.warning(f"Failed to start profile (attempt {attempt + 1}): {e}")
            time.sleep(2)

    logging.error(f"Failed to start profile after {retry_attempts} attempts")
    return None


def start_profile_api(profile_id: str, win_width: int = 1280, win_height: int = 720,
                      pos_x=None, pos_y=None, retry_attempts: int = 3,
                      base_url: str = BASE_URL,
                      profile_name: str | None = None):
    """
    Start a Chrome profile via GPM Login API (/api/v3/profiles/start/{id}) and attach Selenium WebDriver.

    Logs the remote debugging address/port returned by the API.
    """
    resolved_profile_name = profile_name or profile_id

    for attempt in range(retry_attempts):
        try:
            logging.info(
                f"Starting profile via API (attempt {attempt + 1}/{retry_attempts}) profile_id={profile_id}"
            )
            api_url = f"{base_url}/api/v3/profiles/start/{profile_id}"
            params = {"win_width": win_width, "win_height": win_height}
            if pos_x is not None and pos_y is not None:
                params["win_pos_x"] = pos_x
                params["win_pos_y"] = pos_y
            resp = requests.get(api_url, params=params, timeout=15)
            logging.info(f"Start profile status={resp.status_code} body={resp.text[:500]}")
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            success = payload.get("success") if isinstance(payload, dict) else False
            if not success or not isinstance(data, dict):
                logging.warning(f"Start profile failed (attempt {attempt + 1}): {payload}")
                time.sleep(2)
                continue

            remote_addr = data.get("remote_debugging_address") or data.get("remoteDebuggingAddress")
            driver_path = data.get("driver_path") or data.get("driverPath")
            port = None
            if isinstance(remote_addr, str) and ":" in remote_addr:
                try:
                    port = int(remote_addr.rsplit(":", 1)[1])
                except Exception:
                    port = None
            logging.info(
                f"Debugger address: {remote_addr} (port={port if port is not None else '?'}) | driver_path={driver_path}"
            )
            if not remote_addr or not driver_path:
                logging.warning("Missing remote_debugging_address or driver_path from start API response")
                time.sleep(2)
                continue

            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", remote_addr)
            driver_service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=driver_service, options=chrome_options)
            try:
                before_handles = driver.window_handles
                before_url = None
                try:
                    before_url = driver.current_url
                except Exception:
                    before_url = None
                new_handle = None
                try:
                    _ = driver.execute_cdp_cmd("Target.createTarget", {"url": "chrome://version"})
                    # switch to the newly opened tab
                    handles_after = driver.window_handles
                    for h in handles_after:
                        if h not in before_handles:
                            new_handle = h
                            break
                    if new_handle:
                        driver.switch_to.window(new_handle)
                except Exception as cdp_err:
                    logging.warning(f"CDP createTarget failed, fallback to get(): {cdp_err}")
                    driver.get("chrome://version")
                after_url = driver.current_url
                logging.info(f"Navigated to chrome://version, before={before_url} after={after_url}")
                if before_url and before_url == after_url:
                    logging.warning("Navigation did not change URL after chrome://version request")
            except Exception as nav_err:
                logging.warning(f"Failed to navigate to chrome://version: {nav_err}")
        
            logging.info(f"Successfully attached to profile {resolved_profile_name} (id={profile_id})")
            return driver
        except Exception as e:
            logging.warning(f"Failed to start profile (attempt {attempt + 1}): {e}")
            time.sleep(2)

    logging.error(f"Failed to start profile after {retry_attempts} attempts")
    return None

