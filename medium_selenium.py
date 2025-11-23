from __future__ import annotations

import html
import random
import secrets
import inspect
import os
import sys
import re
import time
from html.parser import HTMLParser
from html import entities as html_entities
from pathlib import Path
from typing import Iterable, Any, Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, WebDriverException

try:
    import undetected_chromedriver as uc  # type: ignore
except Exception:  # pragma: no cover
    uc = None

from config import (
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE_DIR,
    WAIT_SHORT,
    WAIT_MED,
    CLICK_JITTER_PX,
    TYPE_DELAY_MIN_S,
    TYPE_DELAY_MAX_S,
    SEL_MEDIUM,
    MEDIUM_SELENIUM_RETRIES,
    MEDIUM_RETRY_DELAY_S,
)

DEFAULT_MEDIUM_TITLE = "test tiletle"
DEFAULT_MEDIUM_BODY_HTML = (
    "<h1>Chào mừng bạn đến với bài viết HTML mẫu trên Medium</h1>\n"
    "\n"
    "<p><strong>HTML</strong> (HyperText Markup Language) là ngôn ngữ đánh dấu được sử dụng để tạo cấu trúc cho trang web.</p>\n"
    "\n"
    "<p>Bạn có thể tìm hiểu thêm tại \n"
    '<a href="https://developer.mozilla.org/vi/docs/Web/HTML" target="_blank">tài liệu MDN</a>.\n'
    "</p>\n"
    "\n"
    "<h2>Hình ảnh minh họa</h2>\n"
    "<figure>\n"
    '  <img src="https://via.placeholder.com/600x300" alt="Ảnh minh họa HTML cơ bản">\n'
    "  <figcaption>Ảnh minh họa cấu trúc HTML cơ bản.</figcaption>\n"
    "</figure>\n"
    "\n"
    "<h2>Danh sách các công nghệ web</h2>\n"
    "<ul>\n"
    "  <li><strong>HTML</strong>: Tạo khung nội dung</li>\n"
    "  <li><strong>CSS</strong>: Trang trí giao diện</li>\n"
    "  <li><strong>JavaScript</strong>: Tạo tương tác và hiệu ứng động</li>\n"
    "</ul>\n"
    "\n"
    "<h2>Đoạn mã ví dụ</h2>\n"
    "<pre><code>&lt;h1&gt;Xin chào thế giới!&lt;/h1&gt;\n"
    "&lt;p&gt;Đây là đoạn văn đầu tiên của bạn.&lt;/p&gt;\n"
    "</code></pre>\n"
    "\n"
    "<blockquote>\n"
    "  “Học HTML là bước đầu tiên để hiểu cách web hoạt động.”\n"
    "</blockquote>\n"
    "\n"
    "<hr>\n"
    "\n"
    "<p><em>&copy; 2025 Bài viết minh họa. Được tạo bởi ChatGPT.</em></p>\n"
)

TAG_CHIP_QUERY = (
    "[data-testid='publishTagChip'], "
    "[data-testid='publishTagsChip'], "
    "[data-testid='publishTopicsChip'], "
    "[data-testid*='publish'][data-testid*='Chip'], "
    ".js-tagInput-chip, "
    ".js-tagInputTag, "
    ".js-tagInput-tag, "
    ".tags-chip, "
    "button[aria-label*='Remove tag' i], "
    "button[aria-label*='Remove topic' i], "
    "button[data-action='deleteTag']"
)


def start_profile(
    user_data_dir: str | None = None,
    profile_dir: str | None = None,
    width: int = 1280,
    height: int = 900,
    x: int = 40,
    y: int = 40,
) -> webdriver.Chrome:
    """Launch Chrome with a persisted profile to keep Medium cookies/2FA."""
    user_data_dir = user_data_dir or CHROME_USER_DATA_DIR
    profile_dir = profile_dir or CHROME_PROFILE_DIR

    if uc is not None:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        if profile_dir:
            options.add_argument(f"--profile-directory={profile_dir}")
        options.add_argument("--disable-notifications")
        driver = uc.Chrome(options=options)
    else:  # Fallback to stock Selenium Chrome
        from selenium.webdriver.chrome.options import Options as ChromeOptions

        options = ChromeOptions()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        if profile_dir:
            options.add_argument(f"--profile-directory={profile_dir}")
        options.add_argument("--disable-notifications")
        driver = webdriver.Chrome(options=options)

    driver.set_window_rect(x, y, width, height)
    _log("STEP:START_CHROME profile ready")
    return driver


def wait_vis(driver: webdriver.Chrome, by: By, sel: str, t: int = WAIT_MED):
    return WebDriverWait(driver, t).until(EC.visibility_of_element_located((by, sel)))


def get_fresh(driver: webdriver.Chrome, css: str, t: int = WAIT_MED):
    """Wait for presence/visibility then always refetch element fresh from DOM."""
    WebDriverWait(driver, t).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
    try:
        return driver.find_element(By.CSS_SELECTOR, css)
    except Exception:
        # Last try with visibility wait
        wait_vis(driver, By.CSS_SELECTOR, css, t=t)
        return driver.find_element(By.CSS_SELECTOR, css)


def _sleep(min_s: float, max_s: float):
    time.sleep(random.uniform(min_s, max_s))


def perform_smooth_scroll(driver: webdriver.Chrome, px: int = 350, steps: int = 2):
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, arguments[0]);", px)
        _sleep(0.08, 0.14)


def _slow_type_keys(el, text: str, min_delay: float = 0.04, max_delay: float = 0.085):
    if not text:
        return
    for ch in text:
        el.send_keys(ch)
        _sleep(min_delay, max_delay)


def click_element_like_original(driver: webdriver.Chrome, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    rdx = random.randint(-CLICK_JITTER_PX, CLICK_JITTER_PX)
    rdy = random.randint(-CLICK_JITTER_PX, CLICK_JITTER_PX)
    try:
        rect = el.rect  # dict: x,y,width,height
        cx = rect["x"] + rect["width"] / 2 + rdx
        cy = rect["y"] + rect["height"] / 2 + rdy
        webdriver.ActionChains(driver).move_by_offset(0, 0).move_by_offset(cx, cy).click().perform()
        webdriver.ActionChains(driver).move_by_offset(-cx, -cy).perform()
    except Exception:
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)


def click_center_by_css(driver: webdriver.Chrome, css: str, t: int = WAIT_MED):
    el = get_fresh(driver, css, t)
    try:
        click_element_like_original(driver, el)
    except StaleElementReferenceException:
        el = get_fresh(driver, css, t)
        click_element_like_original(driver, el)


def type_like_user(el, text: str, min_delay: float = TYPE_DELAY_MIN_S, max_delay: float = TYPE_DELAY_MAX_S):
    """Send entire text in one go (behaves like paste)."""
    if not text:
        return
    el.send_keys(text)


def type_like_user_resilient(driver: webdriver.Chrome, css: str, text: str):
    """Send entire text but refetch element if it goes stale."""
    if not text:
        return
    attempts = 0
    while attempts < 3:
        try:
            el = get_fresh(driver, css, t=WAIT_MED)
            el.send_keys(text)
            return
        except StaleElementReferenceException:
            attempts += 1
            _log("WARN:RESILIENT_TYPING_STALE refetch element")
    raise StaleElementReferenceException("Failed to send keys after retries")


def caret_in_body(driver: webdriver.Chrome) -> bool:
    js = (
        "const s=window.getSelection&&window.getSelection();"
        "if(!s||s.rangeCount===0)return false;"
        "const n=s.anchorNode;const el=(n&&n.nodeType===1)?n:(n?n.parentElement:null);"
        "return !!(el&&el.closest&&el.closest('[data-testid=\\'editorParagraphText\\']'));"
    )
    try:
        return bool(driver.execute_script(js))
    except Exception:
        return False


def handle_popups(driver: webdriver.Chrome):
    # No-op placeholder: add dismissors here if Medium shows blockers
    pass


def open_medium_editor(driver: webdriver.Chrome):
    _log("STEP:OPEN_EDITOR checking if already on /new-story")
    try:
        current_url = driver.current_url
        if "/new-story" in current_url:
            _log("STEP:OPEN_EDITOR already on /new-story, skipping load")
        else:
            _log("STEP:OPEN_EDITOR GET /new-story")
            target_url = "https://medium.com/new-story"
            _load_medium_page(driver, target_url)
    except Exception as e:
        _log(f"WARN:OPEN_EDITOR_URL_CHECK err={e.__class__.__name__}, proceeding with load")
        target_url = "https://medium.com/new-story"
        _load_medium_page(driver, target_url)
    
    WebDriverWait(driver, WAIT_MED).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".postArticle-content"))
    )
    WebDriverWait(driver, WAIT_MED).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SEL_MEDIUM["publish_btn"]))
    )
    _log("STEP:EDITOR_READY container and publish button located")
    handle_popups(driver)


def _load_medium_page(driver: webdriver.Chrome, url: str, attempts: int = 3) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _log(f"STEP:LOAD_MEDIUM attempt={attempt}/{attempts} url={url}")
            driver.set_page_load_timeout(15)  # Set 15 second timeout for page load
            driver.get(url)
        except WebDriverException as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "err_connection_refused" in msg:
                _log(f"WARN:CONNECTION_REFUSED_GET attempt={attempt}/{attempts} retrying")
                if attempt < attempts:
                    _sleep(0.6, 1.0)
                    continue
            raise
        _sleep(1.0, 1.4)
        if _is_connection_refused_page(driver):
            last_exc = TimeoutException("Medium connection refused after reload")
            _log(f"WARN:CONNECTION_REFUSED_PAGE attempt={attempt}/{attempts} retrying")
            if attempt < attempts:
                _sleep(0.6, 1.0)
                continue
            raise last_exc
        return
    if last_exc:
        raise last_exc


def load_medium_page(driver: webdriver.Chrome, url: str, attempts: int = 3) -> None:
    """Public wrapper so the GUI can leverage the same retry logic."""
    _load_medium_page(driver, url, attempts=attempts)


def _is_connection_refused_page(driver: webdriver.Chrome) -> bool:
    try:
        title = (driver.title or "").lower()
        if "this site can" in title and "be reached" in title:
            return True
    except Exception:
        pass
    try:
        body_text = driver.execute_script(
            "return document.body && document.body.innerText ? document.body.innerText : '';"
        )
        if isinstance(body_text, str):
            body_lower = body_text.lower()
            if "err_connection_refused" in body_lower:
                return True
            if "this site can't be reached" in body_lower:
                return True
            if "this site can\u2019t be reached" in body_lower:
                return True
            if "refused to connect" in body_lower and "medium.com" in body_lower:
                return True
    except Exception:
        pass
    return False


def _get_container(driver: webdriver.Chrome):
    try:
        return wait_vis(driver, By.CSS_SELECTOR, SEL_MEDIUM["container"], t=WAIT_MED)
    except TimeoutException:
        return wait_vis(driver, By.CSS_SELECTOR, ".postArticle-content", t=WAIT_MED)


def _as_selector_list(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v]
    if value:
        return [value]
    return []


def _element_plain_text(driver: webdriver.Chrome, element) -> str:
    try:
        text = driver.execute_script(
            """
            const el = arguments[0];
            if (!el) return '';
            const raw = el.innerText || el.textContent || '';
            return raw.trim();
            """,
            element,
        )
        if isinstance(text, str):
            return text.strip()
        return ""
    except StaleElementReferenceException:
        raise
    except Exception:
        try:
            return (element.text or "").strip()
        except Exception:
            return ""


def fill_title_and_body(driver: webdriver.Chrome, title: str, body: str):
    _log("STEP:RESOLVE_CONTAINER locate section-inner")
    # input("PAUSE after locating section-inner, press any keys to continue...")
    container = _get_container(driver)
    container_scope = [container] if container is not None else None

    title_selectors = _as_selector_list(SEL_MEDIUM["title"])
    if not title_selectors:
        raise TimeoutException("No selectors configured for Medium title")

    title_input = title or DEFAULT_MEDIUM_TITLE
    if _looks_like_rich_html(title_input):
        stripped_title = _html_to_plain_text(title_input)
        if stripped_title:
            title_input = stripped_title

    title_el = None
    last_exc = None
    for attempt in range(3):
        title_el = _locate_by_selectors(driver, title_selectors, scopes=container_scope)
        if not title_el:
            _sleep(0.05, 0.1)
            continue
        target = title_el
        try:
            if target is not None:
                target.click()
        except Exception:
            try:
                if target is not None:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
                        target,
                    )
            except Exception:
                target = None
        if target is None:
            title_el = None
            _sleep(0.05, 0.1)
            continue
        active = _active_element(driver)
        if active is not None:
            target = active
        if target is None:
            _sleep(0.05, 0.1)
            continue
        try:
            _slow_type_keys(target, title_input)
            _sleep(0.05, 0.12)
            title_el = target
            break
        except StaleElementReferenceException as exc:
            last_exc = exc
            _sleep(0.12, 0.2)
            continue
        except Exception:
            title_el = None
            _sleep(0.05, 0.1)
    else:
        if last_exc:
            raise last_exc
        raise TimeoutException("Could not locate Medium title field.")

    try:
        title_id = title_el.id  # type: ignore[attr-defined]
    except Exception:
        title_id = None

    _log("STEP:title_id is " + (title_id or "<unknown>"))

    body_value = body or DEFAULT_MEDIUM_BODY_HTML
    is_html, prepared_body, _ = _prepare_medium_body_content(body_value, title_input)

    body_source = prepared_body if prepared_body else body_value
    body_blob = render_medium_body_text(body_source, title_input)
    body_line_count = body_blob.count("\n") + (1 if body_blob else 0)
    _log(
        f"INFO:BODY_RICH_TEXT rendered chars={len(body_blob)} lines={body_line_count}"
    )
    _log(f"INFO:BODY_RICH_TEXT_CONTENT {body_blob!r}")

    try:
        if _type_body_plain(
            driver,
            SEL_MEDIUM.get("body_p"),
            body_blob,
            container_scope=container_scope,
            title_id=title_id,
            rich_html=prepared_body if is_html else None,
        ):
            _log("STEP:BODY_TYPED_PLAIN simple typing path completed")
            _click_optional_ok_button(driver)
    except Exception as e:
        _log(f"ERROR:BODY_TYPE exception {e}")
    # input("PAUSE after body filled, press any keys to continue...")

    


def _click_optional_ok_button(driver: webdriver.Chrome, timeout: float = 5.0) -> None:
    selectors = [
        "button[data-action='overlay-close'].button--primary",
        "button[data-action='overlay-close']",
        "button.button--primary[data-action*='close']",
    ]

    def _find_button(drv):
        for sel in selectors:
            try:
                elem = drv.find_element(By.CSS_SELECTOR, sel)
                if elem is not None and elem.is_displayed():
                    return elem
            except Exception:
                continue
        return None

    try:
        button = WebDriverWait(driver, timeout).until(lambda d: _find_button(d))
    except Exception:
        _log("INFO:BODY_OPTIONAL_OK not found or timeout")
        return
    if not button:
        _log("INFO:BODY_OPTIONAL_OK not found")
        return
    try:
        button.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", button)
        except Exception as exc:
            _log(f"WARN:BODY_OPTIONAL_OK click failed err={exc.__class__.__name__}")
            return
    _log("INFO:BODY_OPTIONAL_OK dismissed overlay")


def _publish_dialog_scopes(driver: webdriver.Chrome):
    selectors = [
        "[data-testid='publishDialog']",
        "[data-testid='prepublish-dialog']",
        "[data-testid='publishMenu']",
        "[role='dialog']",
    ]
    scopes = []
    for sel in selectors:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for cand in candidates:
            if cand is None:
                continue
            try:
                if not cand.is_displayed():
                    continue
            except Exception:
                pass
            scopes.append(cand)
    return scopes or None


def _current_medium_tags(driver: webdriver.Chrome, scope_el=None) -> list[str]:
    try:
        texts = driver.execute_script(
            """
            const selector = arguments[0];
            const scopeArg = arguments[1] || null;
            const scope = (() => {
                if (!scopeArg) return document;
                const dialog = scopeArg.closest('[data-testid=\"publishDialog\"], [data-testid=\"prepublish-dialog\"], [role=\"dialog\"]');
                if (dialog) return dialog;
                const wrapper = scopeArg.closest('[data-testid=\"publishMenu\"], form');
                return wrapper || document;
            })();
            const items = Array.from(scope.querySelectorAll(selector));
            const seen = [];
            for (const item of items) {
                let text = (item.innerText || item.textContent || '').replace(/[#\\n\\r]+/g, ' ').trim();
                if (!text) {
                    const aria = item.getAttribute('aria-label') || '';
                    if (aria) {
                        text = aria
                            .replace(/remove\\s*(tag|topic)/gi, '')
                            .replace(/delete\\s*(tag|topic)/gi, '')
                            .replace(/tag/gi, '')
                            .trim();
                    }
                }
                if (!text) continue;
                const norm = text.toLowerCase ? text.toLowerCase() : text;
                if (!seen.includes(norm)) {
                    seen.push(norm);
                }
            }
            return seen;
            """,
            TAG_CHIP_QUERY,
            scope_el,
        )
        return list(dict.fromkeys(texts))
    except Exception:
        return []


def _set_contenteditable_value(driver: webdriver.Chrome, el, value: str):
    driver.execute_script(
        """
        const el = arguments[0], val = arguments[1];
        el.focus();
        if (el.isContentEditable) {
            el.textContent = '';
            const textNode = document.createTextNode(val);
            el.appendChild(textNode);
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
        }
        let evt;
        try {
            evt = new InputEvent('input', {bubbles:true, data: val});
        } catch (err) {
            evt = new Event('input', {bubbles:true});
        }
        el.dispatchEvent(evt);
        """,
        el,
        value,
    )


HTML_BLOCK_RE = re.compile(
    r"<\s*(p|strong|em|b|i|u|a|h[1-6]|blockquote|pre|code|ul|ol|li|figure|figcaption|img|section|div|span|br|hr)\b",
    re.I,
)
SCRIPT_TAG_RE = re.compile(r"(?is)<\s*(script|style|iframe)[^>]*>.*?<\s*/\s*\1\s*>")
ON_ATTR_RE = re.compile(r"\son[a-z]+\s*=\s*(['\"]).*?\1", re.I)
WRAPPER_TAG_RE = re.compile(r"(?is)</?\s*(html|head|body|article|main|section|nav|aside)[^>]*>")
FULL_DOCUMENT_RE = re.compile(r"(?is)<!DOCTYPE|<html\b|<head\b|<body\b")
NBSP_RE = re.compile(r"&nbsp;", re.I)
NAMED_ENTITY_RE = re.compile(r"&([a-zA-Z][a-zA-Z0-9]+);")
ALLOWED_TAGS: dict[str, set[str] | None] = {
    "p": set(),
    "strong": set(),
    "em": set(),
    "b": set(),
    "i": set(),
    "u": set(),
    "a": {"href", "title"},
    "blockquote": set(),
    "pre": set(),
    "code": set(),
    "ul": set(),
    "ol": set(),
    "li": set(),
    "br": None,
    "img": {"src", "alt", "title"},
    "h1": set(),
    "h2": set(),
    "h3": set(),
    "h4": set(),
    "h5": set(),
    "h6": set(),
    "span": set(),
    "figure": {"class", "data-image-id", "data-width", "data-height", "data-delayed-src", "data-action", "role", "style", "tabindex"},
    "figcaption": {"class", "contenteditable", "data-default-value", "style"},
    "section": {"class", "name"},
    "div": {"class", "style", "data-action-scope", "data-used", "id", "role", "tabindex"},
    "hr": set(),
}
SELF_CLOSING_TAGS = {"br", "img", "hr"}
URL_ATTRS = {"href", "src"}
ALLOWED_SCHEMES = ("http://", "https://", "mailto:", "tel:")
MEDIUM_MARKUP_HINTS = (
    "data-testid=\"editorparagraphtext\"",
    "data-testid='editorparagraphtext'",
    "data-testid=\"editorheadingtext\"",
    "data-testid='editorheadingtext'",
    "postarticle-content",
    "graf--",
)


def _looks_like_rich_html(text: str) -> bool:
    return bool(text and HTML_BLOCK_RE.search(text))


class _MediumHTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._append_start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._append_start(tag, attrs, True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in SELF_CLOSING_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if data:
            self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self.parts)

    def _append_start(self, tag, attrs, self_closing: bool):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        allowed_attrs = ALLOWED_TAGS[tag]
        attr_parts: list[str] = []
        if allowed_attrs:
            for attr_name, attr_value in attrs:
                if attr_value is None:
                    continue
                attr_name = attr_name.lower()
                if attr_name not in allowed_attrs:
                    continue
                attr_value = attr_value.strip()
                if attr_name in URL_ATTRS:
                    if attr_value and not attr_value.lower().startswith(ALLOWED_SCHEMES):
                        continue
                attr_parts.append(f'{attr_name}="{html.escape(attr_value, quote=True)}"')
        attr_str = f" {' '.join(attr_parts)}" if attr_parts else ""
        if tag in SELF_CLOSING_TAGS or self_closing:
            self.parts.append(f"<{tag}{attr_str}/>")
        else:
            self.parts.append(f"<{tag}{attr_str}>")


def _looks_like_medium_editor_markup(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in MEDIUM_MARKUP_HINTS)


def _extract_medium_editable_inner(raw_html: str) -> str:
    if not raw_html:
        return ""
    match = re.search(
        r"(?is)<div[^>]+postArticle-content[^>]*>(.*?)</div>",
        raw_html,
    )
    if match:
        return match.group(1)
    return raw_html


def _sanitize_medium_html(raw_html: str, preserve_medium_markup: bool = False) -> str:
    cleaned = SCRIPT_TAG_RE.sub("", raw_html or "")
    cleaned = ON_ATTR_RE.sub("", cleaned)
    if not preserve_medium_markup:
        cleaned = WRAPPER_TAG_RE.sub("", cleaned)
    cleaned = cleaned.replace("<b>", "<strong>").replace("</b>", "</strong>")
    cleaned = cleaned.replace("<i>", "<em>").replace("</i>", "</em>")
    cleaned = cleaned.replace("<u>", "<span style=\"text-decoration:underline\">").replace("</u>", "</span>")
    cleaned = NBSP_RE.sub("&#160;", cleaned)

    def _replace_named_entity(match):
        name = match.group(1)
        lower = name.lower()
        if lower in {"lt", "gt", "amp", "quot", "apos"}:
            return match.group(0)
        codepoint = html_entities.name2codepoint.get(name)
        if codepoint is None:
            return match.group(0)
        return f"&#{codepoint};"

    cleaned = NAMED_ENTITY_RE.sub(_replace_named_entity, cleaned)
    if preserve_medium_markup:
        return cleaned.strip()
    parser = _MediumHTMLFilter()
    parser.feed(cleaned)
    parser.close()
    html_out = parser.get_html()
    return html_out.strip()


def _is_full_html_document(text: str) -> bool:
    return bool(text and FULL_DOCUMENT_RE.search(text))


def _extract_document_body(raw_html: str) -> str:
    html_text = raw_html or ""
    article_match = re.search(r"(?is)<article[^>]*>(.*?)</article>", html_text)
    if article_match:
        return article_match.group(1)
    body_match = re.search(r"(?is)<body[^>]*>(.*?)</body>", html_text)
    if body_match:
        return body_match.group(1)
    main_match = re.search(r"(?is)<main[^>]*>(.*?)</main>", html_text)
    if main_match:
        return main_match.group(1)
    return html_text


def _prepare_medium_body_content(raw_body: str, title_hint: str | None = None) -> tuple[bool, str, bool]:
    if not raw_body:
        return False, "", False
    body = raw_body.strip()
    if not body:
        return False, "", False
    is_medium_markup = _looks_like_medium_editor_markup(body)
    if _is_full_html_document(body):
        _log("INFO:BODY_HTML_FULLDOC detected full HTML document, sanitizing")
        fragment = _extract_document_body(body)
        fragment = _extract_medium_editable_inner(fragment)
        if not is_medium_markup:
            is_medium_markup = _looks_like_medium_editor_markup(fragment)
        sanitized = _sanitize_medium_html(fragment, preserve_medium_markup=False)
        if sanitized and _looks_like_rich_html(sanitized):
            _log("INFO:BODY_HTML_CONVERT_DISABLED using sanitized document body")
            return True, sanitized, False
        return False, _html_to_plain_text(fragment), False
    if _looks_like_rich_html(body):
        sanitized = _sanitize_medium_html(
            _extract_medium_editable_inner(body) if is_medium_markup else body,
            preserve_medium_markup=False,
        )
        if sanitized and _looks_like_rich_html(sanitized):
            _log("INFO:BODY_HTML_CONVERT_DISABLED using sanitized fragment body")
            return True, sanitized, False
        return False, _html_to_plain_text(body), False
    return False, body, False


def _render_inline_text(elem) -> str:
    parts: list[str] = []
    text = elem.text or ""
    if text:
        parts.append(text)
    for child in list(elem):
        tag = (child.tag or "").lower()
        if tag == "br":
            parts.append("\n")
        else:
            parts.append(_render_inline_text(child))
        tail = child.tail or ""
        if tail:
            parts.append(tail)
    return "".join(parts)


def _html_fragment_to_blocks(fragment: str) -> list[dict[str, Any]]:
    fragment = _normalize_html_entities_for_xml(fragment)
    try:
        root = ET.fromstring(f"<root>{fragment}</root>")
    except ET.ParseError:
        return [{"type": "paragraph", "text": _html_to_plain_text(fragment)}]

    blocks: list[dict[str, Any]] = []

    def add_paragraph(text: str):
        stripped = text.strip()
        if stripped:
            blocks.append({"type": "paragraph", "text": stripped})

    def add_heading(text: str, level: int):
        stripped = text.strip()
        if stripped:
            blocks.append({"type": "heading", "level": level, "text": stripped})

    def add_quote(lines: list[str]):
        clean = [line.strip() for line in lines if line.strip()]
        if clean:
            blocks.append({"type": "quote", "lines": clean})

    def add_list(items: list[str], ordered: bool):
        clean = [item.strip() for item in items if item.strip()]
        if clean:
            blocks.append({"type": "ol" if ordered else "ul", "items": clean})

    def add_code(text: str):
        if text:
            blocks.append({"type": "code", "text": text})

    def process_element(element):
        tag = (element.tag or "").lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            add_heading(_render_inline_text(element), level)
        elif tag == "p":
            add_paragraph(_render_inline_text(element))
        elif tag == "blockquote":
            lines = []
            for child in list(element):
                if (child.tag or "").lower() == "p":
                    lines.append(_render_inline_text(child))
                else:
                    lines.append(_render_inline_text(child))
            if element.text and element.text.strip():
                lines.insert(0, element.text)
            add_quote(lines)
        elif tag == "ul":
            items = [_render_inline_text(li) for li in element.findall("./li")]
            add_list(items, ordered=False)
        elif tag == "ol":
            items = [_render_inline_text(li) for li in element.findall("./li")]
            add_list(items, ordered=True)
        elif tag == "pre":
            text = element.text or ""
            if not text:
                text = "".join(element.itertext())
            add_code(text.rstrip("\n"))
        elif tag == "code" and (element.text or "").strip():
            add_code(element.text.strip())
        elif tag == "hr":
            blocks.append({"type": "hr"})
        else:
            text = _render_inline_text(element)
            if text.strip():
                blocks.append({"type": "paragraph", "text": text})

    for child in list(root):
        process_element(child)

    return blocks


_HTML_ENTITY_PATTERN = re.compile(r"&([a-zA-Z][a-zA-Z0-9]+);")
_HTML_ENTITY_SKIP = {"lt", "gt"}


def _normalize_html_entities_for_xml(fragment: str) -> str:
    if not fragment or "&" not in fragment:
        return fragment

    def _replace(match):
        name = match.group(1)
        if not name:
            return match.group(0)
        lower = name.lower()
        if lower in _HTML_ENTITY_SKIP:
            return match.group(0)
        codepoint = html_entities.name2codepoint.get(lower)
        if codepoint is None:
            return match.group(0)
        return chr(codepoint)

    return _HTML_ENTITY_PATTERN.sub(_replace, fragment)


def _html_fragment_to_rich_lines(body_html: str) -> list[str]:
    """Convert raw body HTML into the lines Medium typing flow expects."""
    if not body_html:
        return []
    blocks = _html_fragment_to_blocks(body_html)
    lines = _blocks_to_medium_lines(blocks)
    if lines:
        return lines
    return _text_to_medium_lines(_html_to_plain_text(body_html))


def _collapse_medium_lines(lines: Iterable[str]) -> list[str]:
    collapsed: list[str] = []

    def _append_piece(text: str):
        cleaned = text.rstrip()
        if cleaned:
            collapsed.append(cleaned)
        else:
            if collapsed and collapsed[-1] == "":
                return
            collapsed.append("")

    for value in lines:
        if value is None:
            _append_piece("")
            continue
        normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
        parts = normalized.split("\n")
        for part in parts:
            _append_piece(part)

    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return collapsed


def render_medium_body_text(body_html: str, title_hint: str | None = None) -> str:
    """Public helper to convert HTML/plain content into the final text blob Medium receives."""
    body_value = body_html or ""
    is_html, prepared_body, _ = _prepare_medium_body_content(body_value, title_hint)
    if is_html:
        lines = _html_fragment_to_rich_lines(prepared_body)
        if not lines:
            lines = _text_to_medium_lines(_html_to_plain_text(prepared_body))
    else:
        lines = _text_to_medium_lines(prepared_body)
    if not lines and prepared_body:
        lines = [prepared_body]
    collapsed = _collapse_medium_lines(lines)
    text_blob = "\n".join(collapsed)
    text_blob = re.sub(r"\n{2,}", "\n", text_blob).strip("\n")
    return text_blob


def _describe_element(element) -> str:
    if element is None:
        return "<None>"
    try:
        tag = (element.tag_name or "").lower()
    except Exception:
        tag = "?"
    try:
        el_id = element.get_attribute("id") or ""
    except Exception:
        el_id = ""
    try:
        cls = element.get_attribute("class") or ""
    except Exception:
        cls = ""
    bits = [tag or "?"]
    if el_id:
        bits.append(f"#{el_id}")
    if cls:
        bits.append(f".{cls.strip().replace(' ', '.')}")
    return "".join(bits)


def _resolve_medium_body_typing_node(driver: webdriver.Chrome, element):
    """Ensure we type on a real Medium contenteditable node (p/div vs placeholder span)."""
    if element is None:
        return None
    try:
        ce_attr = element.get_attribute("contenteditable") or ""
        if ce_attr.lower() == "true":
            return element
    except StaleElementReferenceException:
        raise
    except Exception:
        pass
    try:
        ancestor = driver.execute_script(
            """
            const el = arguments[0];
            if (!el) return null;
            const selector = "[data-testid='editorParagraphText'], [contenteditable='true']";
            if (typeof el.matches === "function" && el.matches(selector)) return el;
            return el.closest(selector);
            """,
            element,
        )
    except Exception:
        ancestor = None
    return ancestor or element


def _type_body_plain(
    driver: webdriver.Chrome,
    selectors,
    lines,
    *,
    container_scope=None,
    title_id: str | None = None,
    rich_html: str | None = None,
) -> bool:
    selectors_list = _as_selector_list(selectors)
    if not selectors_list:
        return False

    if isinstance(lines, str):
        text_blob = lines
    elif isinstance(lines, Iterable):
        text_blob = "".join("" if line is None else str(line) for line in lines)
    else:
        text_blob = str(lines or "")

    if not text_blob:
        _log("WARN:BODY_TYPE empty body input")
        return True

    text_blob = text_blob.replace("\r\n", "\n").replace("\r", "\n")
    line_count = text_blob.count("\n") + (0 if text_blob.endswith("\n") else 1)
    _log(
        f"STEP:BODY_TYPE_PLAIN lines={line_count} selectors={selectors_list}"
    )
    _log(f"DEBUG:BODY_TYPE text_blob={text_blob}")

    def _acquire_body_element(existing=None, phase="locate"):
        body_candidate = existing
        for attempt in range(1, 4):
            _log(f"STEP:BODY_TYPE {phase} attempt={attempt}")
            if body_candidate is None:
                try:
                    body_candidate = _locate_by_selectors(
                        driver,
                        selectors_list,
                        exclude_ids=[title_id],
                        scopes=container_scope,
                    )
                except Exception as exc:
                    _log(
                        f"WARN:BODY_TYPE {phase} locate error attempt={attempt} err={exc.__class__.__name__}: {exc}"
                    )
                    body_candidate = None
                if not body_candidate:
                    _log("WARN:BODY_TYPE no candidate element found")
                    _sleep(0.05, 0.1)
                    continue
            body_candidate = _resolve_medium_body_typing_node(driver, body_candidate)
            if body_candidate is None:
                _log("WARN:BODY_TYPE resolved typing node is None")
                _sleep(0.05, 0.1)
                continue
            try:
                body_candidate.click()
            except Exception as exc:
                _log(f"WARN:BODY_TYPE click failed err={exc.__class__.__name__}")
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
                        body_candidate,
                    )
                except Exception as js_exc:
                    _log(
                        f"WARN:BODY_TYPE js click failed err={js_exc.__class__.__name__}"
                    )
                    body_candidate = None
                    _sleep(0.05, 0.1)
                    continue
            active = _active_element(driver)
            if active is not None and _element_is_body(active, title_id):
                body_candidate = active
            else:
                body_candidate = _resolve_medium_body_typing_node(driver, body_candidate)
            if body_candidate is None:
                _log("WARN:BODY_TYPE active element unusable after focus")
                _sleep(0.05, 0.1)
                continue
            _log(f"STEP:BODY_TYPE focused element {_describe_element(body_candidate)}")
            return body_candidate
        return None

    body_el = _acquire_body_element()

    if body_el is None:
        _log("ERROR:BODY_TYPE failed to acquire body element after retries")
        return False
    
    clipboard_ok = False
    if _clipboard_copy_content(driver, text_blob, rich_html):
        clipboard_ok = _paste_from_clipboard_into_element(driver, body_el)
        if clipboard_ok:
            _log("STEP:BODY_TYPE clipboard paste succeeded")
            return True
        _log("WARN:BODY_TYPE clipboard paste failed after copy")
    return False
    # debug_path = Path("temp_medium_body.txt")
    # try:
    #     debug_path.write_text(text_blob, encoding="utf-8")
    #     _log(
    #         f"INFO:BODY_TYPE saved_body_debug file={debug_path.name} lines={line_count} path={debug_path.resolve()}"
    #     )
    # except Exception as exc:
    #     _log(f"WARN:BODY_TYPE save_debug_failed err={exc.__class__.__name__}")

    # for attempt in range(1, 4):
    #     try:
    #         body_el.send_keys(text_blob)
    #         break
    #     except StaleElementReferenceException as stale_exc:
    #         _log(
    #             f"WARN:BODY_TYPE stale element during paste attempt={attempt} err={stale_exc.__class__.__name__}"
    #         )
    #     except Exception as type_exc:
    #         _log(
    #             f"ERROR:BODY_TYPE paste failed attempt={attempt} err={type_exc.__class__.__name__}"
    #         )
    #         raise

    #     if attempt < 3:
    #         body_el = _acquire_body_element(phase="reacquire")
    #         if body_el is None:
    #             _log(
    #                 "ERROR:BODY_TYPE unable to reacquire body element during paste retry"
    #             )
    #             raise
    #     else:
    #         raise

    # return True


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


def _generate_graf_id() -> str:
    return secrets.token_hex(2)


def _inner_html(element: ET.Element) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in list(element):
        parts.append(ET.tostring(child, encoding="unicode", method="html"))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _medium_block_from_element(element: ET.Element) -> Optional[Any]:
    tag = (element.tag or "").lower()
    inner = _inner_html(element)
    if tag in {"div", "section", "article", "main"}:
        blocks: list[dict[str, Any]] = []
        if element.text and element.text.strip():
            text = element.text.strip()
            blocks.append({"type": "paragraph", "html": html.escape(text), "text": text})
        for child in list(element):
            child_block = _medium_block_from_element(child)
            if isinstance(child_block, list):
                blocks.extend(child_block)
            elif child_block:
                blocks.append(child_block)
            if child.tail and child.tail.strip():
                tail_text = child.tail.strip()
                blocks.append({"type": "paragraph", "html": html.escape(tail_text), "text": tail_text})
        return blocks
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        return {"type": "heading", "level": level, "html": inner, "text": _strip_tags(inner)}
    if tag == "p":
        images = element.findall(".//img")
        if (
            len(images) == 1
            and (element.text or "").strip() == ""
            and all((img.tail or "").strip() == "" for img in images)
        ):
            img = images[0]
            return {
                "type": "image",
                "src": img.attrib.get("src", ""),
                "alt": img.attrib.get("alt", ""),
                "title": img.attrib.get("title", ""),
                "width": img.attrib.get("data-width") or img.attrib.get("width"),
                "height": img.attrib.get("data-height") or img.attrib.get("height"),
                "caption": "",
            }
        if inner:
            return {"type": "paragraph", "html": inner, "text": _strip_tags(inner)}
        return None
    if tag == "img":
        return {
            "type": "image",
            "src": element.attrib.get("src", ""),
            "alt": element.attrib.get("alt", ""),
            "title": element.attrib.get("title", ""),
            "width": element.attrib.get("data-width") or element.attrib.get("width"),
            "height": element.attrib.get("data-height") or element.attrib.get("height"),
            "caption": "",
        }
    if tag == "figure":
        img = element.find(".//img")
        if img is None:
            return None
        caption_el = element.find(".//figcaption")
        caption_html = _inner_html(caption_el) if caption_el is not None else ""
        return {
            "type": "image",
            "src": img.attrib.get("src", ""),
            "alt": img.attrib.get("alt", ""),
            "title": img.attrib.get("title", ""),
            "width": img.attrib.get("data-width") or img.attrib.get("width"),
            "height": img.attrib.get("data-height") or img.attrib.get("height"),
            "caption": caption_html,
        }
    if tag in {"ul", "ol"}:
        items = []
        for li in element.findall("./li"):
            item_html = _inner_html(li)
            if item_html:
                items.append({"html": item_html, "text": _strip_tags(item_html)})
        if items:
            return {
                "type": "ol" if tag == "ol" else "ul",
                "items": items,
            }
        return None
    if tag == "blockquote":
        if inner:
            return {"type": "quote", "html": inner, "text": _strip_tags(inner)}
        return None
    if tag == "pre":
        text = element.text or inner
        return {"type": "code", "text": text.rstrip("\n")}
    if tag == "code":
        text = (element.text or "").strip()
        if text:
            return {"type": "code", "text": text}
        return None
    if tag == "hr":
        return {"type": "hr"}
    if inner:
        return {"type": "paragraph", "html": inner, "text": _strip_tags(inner)}
    return None


def _medium_blocks_from_fragment(fragment: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(f"<root>{fragment}</root>")
    except ET.ParseError:
        _log("WARN:BODY_HTML_PARSE_ERROR fragment could not be parsed as XML")
        try:
            Path("temp_block.txt").write_text(fragment, encoding="utf-8")
            _log(f"INFO:BODY_HTML_DEBUG_WRITTEN path=temp_block.txt size={len(fragment)}")
        except Exception as exc:
            _log(f"WARN:BODY_HTML_DEBUG_WRITE_FAIL err={exc.__class__.__name__}")
        return []
    blocks: list[dict[str, Any]] = []
    if root.text and root.text.strip():
        text = root.text.strip()
        blocks.append({"type": "paragraph", "html": html.escape(text), "text": text})
    for child in list(root):
        block = _medium_block_from_element(child)
        if isinstance(block, list):
            blocks.extend(block)
        elif block:
            blocks.append(block)
        if child.tail and child.tail.strip():
            tail_text = child.tail.strip()
            blocks.append({"type": "paragraph", "html": html.escape(tail_text), "text": tail_text})
    return blocks


def _medium_after_class(prev_type: str) -> str:
    mapping = {
        "title": "title",
        "heading": "h3",
        "paragraph": "p",
        "quote": "blockquote",
        "code": "pre",
        "image": "figure",
        "ul": "li",
        "ol": "li",
        "li": "li",
    }
    return mapping.get(prev_type, "p")


def _render_medium_title(title_html: str) -> str:
    return (
        f'<h3 data-testid="editorTitleParagraph" name="{_generate_graf_id()}" '
        f'class="graf graf--h3 graf--leading graf--title">{title_html}</h3>'
    )


def _render_medium_heading(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = [ "graf", "graf--h3", f"graf-after--{after}" ]
    if trailing:
        classes.append("graf--trailing")
    return (
        f'<h3 data-testid="editorHeadingText" name="{_generate_graf_id()}" '
        f'class="{" ".join(classes)}">{block.get("html","")}</h3>'
    )


def _render_medium_paragraph(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = ["graf", "graf--p", f"graf-after--{after}"]
    if trailing:
        classes.append("graf--trailing")
    return (
        f'<p data-testid="editorParagraphText" name="{_generate_graf_id()}" '
        f'class="{" ".join(classes)}">{block.get("html","")}</p>'
    )


def _render_medium_quote(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = ["graf", "graf--blockquote", f"graf-after--{after}"]
    if trailing:
        classes.append("graf--trailing")
    return (
        f'<blockquote data-testid="editorParagraphText" name="{_generate_graf_id()}" '
        f'class="{" ".join(classes)}">{block.get("html","")}</blockquote>'
    )


def _render_medium_code(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = ["graf", "graf--pre", f"graf-after--{after}"]
    if trailing:
        classes.append("graf--trailing")
    code_html = html.escape(block.get("text", "") or "")
    return (
        f'<pre data-testid="editorParagraphText" name="{_generate_graf_id()}" '
        f'class="{" ".join(classes)}"><code>{code_html}</code></pre>'
    )


def _render_medium_image(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = ["graf", "graf--figure", f"graf-after--{after}"]
    if trailing:
        classes.append("graf--trailing")
    width = block.get("width")
    height = block.get("height")
    ratio = 56.3
    try:
        if width and height:
            ratio = max(5.0, min(150.0, (float(height) / float(width)) * 100))
    except Exception:
        ratio = 56.3
    src = html.escape(block.get("src") or "")
    alt = html.escape(block.get("alt") or "")
    title = html.escape(block.get("title") or "")
    caption_html = block.get("caption") or ""
    figcaption = (
        caption_html
        if caption_html
        else '<span class="defaultValue">Type caption for image (optional)</span><br>'
    )
    return (
        f'<figure tabindex="0" contenteditable="false" data-testid="editorImageParagraph" '
        f'name="{_generate_graf_id()}" class="{" ".join(classes)}">'
        f'<div class="aspectRatioPlaceholder is-locked" style="max-width: 700px; max-height: 394px;">'
        f'<div class="aspectRatioPlaceholder-fill" style="padding-bottom: {ratio:.1f}%;"></div>'
        f'<img class="graf-image" src="{src}" alt="{alt}" title="{title}"/>'
        f'<div class="crosshair u-ignoreBlock"></div>'
        f'</div>'
        f'<figcaption class="imageCaption" contenteditable="true" data-default-value="Type caption for image (optional)">{figcaption}</figcaption>'
        f'</figure>'
    )


def _render_medium_list(block: dict[str, Any], prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    list_tag = "ol" if block.get("type") == "ol" else "ul"
    list_classes = ["postList"]
    items_html: list[str] = []
    current_prev = prev_type
    items = block.get("items") or []
    for index, item in enumerate(items):
        item_after = _medium_after_class("li" if index else current_prev)
        item_classes = ["graf", "graf--li", f"graf-after--{item_after}"]
        if trailing and index == len(items) - 1:
            item_classes.append("graf--trailing")
        items_html.append(
            f'<li data-testid="editorParagraphText" name="{_generate_graf_id()}" class="{" ".join(item_classes)}">{item.get("html","")}</li>'
        )
        current_prev = "li"
    list_html = f"<{list_tag} class=\"{' '.join(list_classes)}\">{''.join(items_html)}</{list_tag}>"
    return list_html


def _render_medium_hr(prev_type: str, trailing: bool) -> str:
    after = _medium_after_class(prev_type)
    classes = ["graf", "graf--hr", f"graf-after--{after}"]
    if trailing:
        classes.append("graf--trailing")
    return f'<hr data-testid="editorParagraphText" name="{_generate_graf_id()}" class="{" ".join(classes)}"/>'


def _convert_sanitized_html_to_medium_markup(fragment: str, title_hint: str | None = None) -> Optional[str]:
    blocks = _medium_blocks_from_fragment(fragment)
    if not blocks:
        if fragment.strip():
            _log("WARN:BODY_HTML_CONVERT_NO_BLOCKS despite non-empty fragment")
        return None
    working_blocks = [dict(block) for block in blocks]
    title_html: Optional[str] = None
    hint = (title_hint or "").strip()
    if hint:
        title_html = html.escape(hint)
        if working_blocks and working_blocks[0].get("type") == "heading":
            heading_text = working_blocks[0].get("text", "").strip()
            if heading_text and heading_text.lower() == _strip_tags(title_html).lower():
                working_blocks.pop(0)
    elif working_blocks and working_blocks[0].get("type") == "heading":
        title_html = working_blocks.pop(0).get("html", "")
    else:
        first_text = working_blocks[0].get("text", "Untitled story")
        title_html = html.escape(first_text.strip() or "Untitled story")
    rendered_blocks: list[str] = []
    prev_type = "title"
    for index, block in enumerate(working_blocks):
        trailing = index == len(working_blocks) - 1
        btype = block.get("type")
        if btype == "heading":
            rendered_blocks.append(_render_medium_heading(block, prev_type, trailing))
            prev_type = "heading"
        elif btype == "paragraph":
            rendered_blocks.append(_render_medium_paragraph(block, prev_type, trailing))
            prev_type = "paragraph"
        elif btype == "quote":
            rendered_blocks.append(_render_medium_quote(block, prev_type, trailing))
            prev_type = "quote"
        elif btype == "code":
            rendered_blocks.append(_render_medium_code(block, prev_type, trailing))
            prev_type = "code"
        elif btype == "image":
            rendered_blocks.append(_render_medium_image(block, prev_type, trailing))
            prev_type = "image"
        elif btype in {"ul", "ol"}:
            rendered_blocks.append(_render_medium_list(block, prev_type, trailing))
            prev_type = "li"
        elif btype == "hr":
            rendered_blocks.append(_render_medium_hr(prev_type, trailing))
            prev_type = "hr"
        else:
            rendered_blocks.append(_render_medium_paragraph(block, prev_type, trailing))
            prev_type = "paragraph"
    section_name = _generate_graf_id()
    title_block = _render_medium_title(title_html or "")
    body_inner = title_block + "".join(rendered_blocks)
    section_html = (
        f'<section name="{section_name}" class="section section--body section--first section--last">'
        f'<div class="section-divider"><hr class="section-divider"></div>'
        f'<div class="section-content"><div class="section-inner sectionLayout--insetColumn">'
        f'{body_inner}'
        f'</div></div></section>'
    )
    try:
        debug_path = Path("temp_block_medium.html")
        debug_path.write_text(section_html, encoding="utf-8")
        _log(f"INFO:BODY_HTML_DEBUG_MEDIUM path={debug_path} bytes={debug_path.stat().st_size}")
    except Exception as exc:
        _log(f"WARN:BODY_HTML_DEBUG_MEDIUM_FAIL err={exc.__class__.__name__}")
    return section_html


def _blocks_to_medium_lines(blocks: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "heading":
            level = max(1, min(6, int(block.get("level", 2))))
            prefix = "#" * level
            lines.append(f"{prefix} {block.get('text', '').strip()}")
            lines.append("")
        elif btype == "paragraph":
            text = block.get("text", "").strip()
            lines.append(text)
            lines.append("")
        elif btype == "quote":
            for line in block.get("lines", []):
                lines.append(f"> {line.strip()}")
            lines.append("")
        elif btype == "ul":
            for item in block.get("items", []):
                lines.append(f"- {item.strip()}")
            lines.append("")
        elif btype == "ol":
            for idx, item in enumerate(block.get("items", []), start=1):
                lines.append(f"{idx}. {item.strip()}")
            lines.append("")
        elif btype == "code":
            lines.append("```")
            code_text = block.get("text", "")
            if code_text:
                for line in code_text.splitlines():
                    lines.append(line.rstrip("\n"))
            lines.append("```")
            lines.append("")
        elif btype == "hr":
            lines.append("---")
            lines.append("")
    # Trim trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _text_to_medium_lines(text: str) -> list[str]:
    if not text:
        return []
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in raw_lines]
    return lines



def _plain_text_to_medium_html(text: str) -> str:
    if not text:
        return "<p></p>"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            buffer.append(html.escape(stripped))
        else:
            if buffer:
                paragraphs.append("<p>" + "<br/>".join(buffer) + "</p>")
                buffer = []
    if buffer:
        paragraphs.append("<p>" + "<br/>".join(buffer) + "</p>")
    return "".join(paragraphs) if paragraphs else "<p></p>"


def _html_to_plain_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = raw_html.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _active_element(driver):
    try:
        return driver.execute_script("return document.activeElement;")
    except Exception:
        return None


def _element_is_body(el, title_id=None):
    if el is None:
        return False
    try:
        if title_id and getattr(el, "id", None) == title_id:
            return False
    except Exception:
        pass
    try:
        testid = (el.get_attribute("data-testid") or "").lower()
        if "title" in testid:
            return False
        if "editorparagraphtext" in testid:
            return True
        if el.get_attribute("contenteditable") == "true":
            return True
    except StaleElementReferenceException:
        return False
    except Exception:
        pass
    return False


def _resolve_scopes(driver: webdriver.Chrome, scopes=None):
    resolved = []
    scope_items = scopes
    if scope_items and not isinstance(scope_items, (list, tuple, set)):
        scope_items = [scope_items]
    if scope_items:
        for scope in scope_items:
            if not scope:
                continue
            if isinstance(scope, str):
                try:
                    resolved.extend(driver.find_elements(By.CSS_SELECTOR, scope))
                except Exception:
                    continue
            else:
                resolved.append(scope)
    if not resolved:
        container_sel = SEL_MEDIUM.get("container")
        if container_sel:
            try:
                resolved.extend(driver.find_elements(By.CSS_SELECTOR, container_sel))
            except Exception:
                pass
    filtered = []
    for candidate in resolved:
        if candidate is None:
            continue
        try:
            candidate.is_enabled()
        except StaleElementReferenceException:
            continue
        except Exception:
            pass
        filtered.append(candidate)
    return filtered or [driver]


def _locate_by_selectors(driver: webdriver.Chrome, selectors, exclude_ids=(), scopes=None):
    exclude = {eid for eid in (exclude_ids or []) if eid}
    scope_elements = _resolve_scopes(driver, scopes)
    for sel in selectors:
        if not sel:
            continue
        try:
            WebDriverWait(driver, WAIT_MED).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
        except TimeoutException:
            continue
        for scope in scope_elements:
            try:
                if scope is driver:
                    candidates = driver.find_elements(By.CSS_SELECTOR, sel)
                else:
                    candidates = scope.find_elements(By.CSS_SELECTOR, sel)
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
            for cand in candidates:
                if cand is None:
                    continue
                try:
                    if cand.id in exclude:
                        continue
                except StaleElementReferenceException:
                    continue
                except Exception:
                    pass
                try:
                    if not cand.is_displayed():
                        continue
                except StaleElementReferenceException:
                    continue
                except Exception:
                    pass
                return cand
    return None


def _focus_element(driver, element):
    if element is None:
        return None
    try:
        click_element_like_original(driver, element)
    except Exception:
        try:
            driver.execute_script("arguments[0].focus();", element)
        except Exception:
            return None
        else:
            active = _active_element(driver)
            return active if active is not None else element
    else:
        active = _active_element(driver)
        if active is not None:
            return active
        try:
            driver.execute_script(
                """
                const el = arguments[0];
                if (!el) return;
                const rect = el.getBoundingClientRect();
                const centerX = rect.left + rect.width / 2;
                const centerY = rect.top + Math.min(rect.height / 2, 60);
                const opts = {bubbles: true, cancelable: true, clientX: centerX, clientY: centerY, buttons: 1};
                const types = ['pointerover','pointerenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'];
                for (const type of types) {
                    el.dispatchEvent(new MouseEvent(type, opts));
                }
                if (typeof el.focus === 'function') {
                    el.focus({preventScroll: true});
                }
                """,
                element,
            )
        except Exception:
            pass
    active = _active_element(driver)
    return active if active is not None else element


def _copy_html_to_clipboard(driver: webdriver.Chrome, html: str) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const html = arguments[0];
                const temp = document.createElement('div');
                temp.setAttribute('contenteditable', 'true');
                temp.style.position = 'fixed';
                temp.style.pointerEvents = 'none';
                temp.style.opacity = '0';
                temp.style.zIndex = '2147483647';
                temp.style.whiteSpace = 'pre-wrap';
                document.body.appendChild(temp);
                temp.innerHTML = html;
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(temp);
                sel.removeAllRanges();
                sel.addRange(range);
                const copied = document.execCommand('copy');
                sel.removeAllRanges();
                document.body.removeChild(temp);
                return copied;
                """,
                html,
            )
        )
    except Exception:
        return False


def _resolve_medium_body_target(driver: webdriver.Chrome, hint=None):
    try:
        result = driver.execute_script(
            """
            const hint = arguments[0] || null;
            const root = document.querySelector("div.postArticle-content[g_editable='true']");
            if (!root) return [null, null];
            const title = root.querySelector("[data-testid='editorTitleParagraph']");
            const isUsable = (el) => {
                if (!el) return false;
                if (title && el === title) return false;
                if (!root.contains(el)) return false;
                const testid = (el.getAttribute('data-testid') || '').toLowerCase();
                if (testid.includes('editorparagraphtext')) return true;
                if (el.isContentEditable) return true;
                return false;
            };
            let target = null;
            if (hint && isUsable(hint)) {
                target = hint;
            }
            if (!target) {
                const candidate = root.querySelector("[data-testid='editorParagraphText']");
                if (candidate) target = candidate;
            }
            if (!target) {
                const created = document.createElement('p');
                created.setAttribute('data-testid', 'editorParagraphText');
                created.className = 'graf graf--p graf-after--title graf--trailing';
                created.innerHTML = '<br>';
                root.appendChild(created);
                target = created;
            }
            return [target, root];
            """,
            hint,
        )
    except Exception:
        return None, None
    if not result or len(result) < 2:
        return None, None
    return result[0], result[1]


def _paste_medium_html_via_clipboard(
    driver: webdriver.Chrome, html: str, hint=None
) -> bool:
    target, root = _resolve_medium_body_target(driver, hint)
    if not target or not root:
        _log("WARN:BODY_CLIPBOARD_TARGET_NOT_FOUND")
        return False
    _log("INFO:BODY_CLIPBOARD_PASTE attempt via ActionChains")
    try:
        actions = webdriver.ActionChains(driver)
        actions.move_to_element(target)
        actions.pause(0.06)
        actions.click()
        actions.perform()
    except Exception:
        try:
            target.click()
        except Exception:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                    target,
                )
            except Exception:
                return False
    _sleep(0.08, 0.14)
    try:
        actions = webdriver.ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
    except Exception:
        pass
    _sleep(0.05, 0.1)
    try:
        webdriver.ActionChains(driver).send_keys(Keys.BACKSPACE).perform()
    except Exception:
        pass
    _sleep(0.05, 0.1)
    if not _copy_html_to_clipboard(driver, html):
        _log("WARN:BODY_CLIPBOARD_COPY_FAILED")
        return False
    _sleep(0.05, 0.1)
    try:
        actions = webdriver.ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
    except Exception:
        _log("WARN:BODY_CLIPBOARD_PASTE_KEYSEQ_FAILED")
        return False
    _sleep(0.25, 0.35)
    try:
        inner_html = driver.execute_script("return arguments[0].innerHTML;", root) or ""
    except Exception:
        inner_html = ""
    cleaned_inner = re.sub(r"\s+", "", inner_html)
    if not cleaned_inner or cleaned_inner in {"", "<p><br></p>", "<p></p>"}:
        _log("WARN:BODY_CLIPBOARD_EMPTY_AFTER_PASTE")
        return False
    try:
        driver.execute_script(
            """
            const root = arguments[0];
            const events = ['input','change','keyup','keydown','keypress'];
            for (const type of events) {
                root.dispatchEvent(new Event(type, {bubbles:true}));
            }
            """,
            root,
        )
    except Exception:
        pass
    _log("INFO:BODY_CLIPBOARD_PASTE success")
    return True


def _copy_text_to_clipboard(driver: webdriver.Chrome, text: str) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const text = arguments[0] ?? '';
                const temp = document.createElement('textarea');
                temp.style.position = 'fixed';
                temp.style.pointerEvents = 'none';
                temp.style.opacity = '0';
                temp.style.zIndex = '2147483647';
                temp.value = text;
                document.body.appendChild(temp);
                temp.focus();
                temp.select();
                const copied = document.execCommand('copy');
                document.body.removeChild(temp);
                return copied;
                """,
                text,
            )
        )
    except Exception:
        return False


def _clipboard_copy_content(driver: webdriver.Chrome, text: str, rich_html: str | None) -> bool:
    if rich_html:
        if _copy_html_to_clipboard(driver, rich_html):
            _log("INFO:BODY_CLIPBOARD copied rich HTML payload")
            return True
        _log("WARN:BODY_CLIPBOARD rich HTML copy failed, falling back to text")
    if text:
        if _copy_text_to_clipboard(driver, text):
            _log("INFO:BODY_CLIPBOARD copied plain text payload")
            return True
    return False


def _html_to_plain_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = raw_html.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()




def _clear_tag_input(driver: webdriver.Chrome, el):
    try:
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
    except Exception:
        try:
            el.clear()
        except Exception:
            driver.execute_script(
                """
                const el = arguments[0];
                if (el.isContentEditable) {
                    el.textContent = '';
                } else {
                    el.value = '';
                }
                """,
                el,
            )


def _type_tag_characters(el, text: str):
    for ch in text:
        el.send_keys(ch)
        _sleep(0.03, 0.06)


def _confirm_tag_with_comma(driver: webdriver.Chrome, el) -> bool:
    try:
        el.send_keys(Keys.COMMA)
        return True
    except Exception:
        try:
            el.send_keys(",")
            return True
        except Exception:
            try:
                el.send_keys(Keys.ENTER)
                return True
            except Exception:
                try:
                    driver.execute_script(
                        """
                        const el = arguments[0];
                        const eventInit = {bubbles:true, key:',', code:'Comma', keyCode:188, which:188};
                        for (const type of ['keydown','keypress','keyup']) {
                            el.dispatchEvent(new KeyboardEvent(type, eventInit));
                        }
                        """,
                        el,
                    )
                    return True
                except Exception:
                    return False


def _resolve_tag_input_field(driver: webdriver.Chrome, el):
    try:
        if el is not None:
            attr = (el.get_attribute("data-testid") or "").lower()
            if el.get_attribute("contenteditable") == "true":
                return el
            if "publishtopicsinput" in attr and el.get_attribute("role") == "textbox":
                return el
    except Exception:
        pass
    try:
        field = driver.execute_script(
            """
            const root = arguments[0];
            if (!root) return null;
            if (root.isContentEditable) return root;
            const selectors = [
                "[data-testid='publishTopicsInput'][contenteditable='true']",
                "body > div.overlay.overlay--white > div > div > div > div:nth-child(3) > div.u-width100pct.u-marginBottom24 > div[contenteditable='true']",
                ".js-tagInput.tags-input.editable[contenteditable='true']",
                "div[role='textbox'][contenteditable='true']",
                "[contenteditable='true']"
            ];
            for (const sel of selectors) {
                const candidate = root.matches && root.matches(sel) ? root : root.querySelector(sel);
                if (candidate) return candidate;
            }
            return root;
            """,
            el,
        )
        if field:
            return field
    except Exception:
        pass
    try:
        selectors = [
            "[data-testid='publishTopicsInput']",
            ".js-tagInput.tags-input.editable",
            "div[role='textbox'][contenteditable='true']",
        ]
        for sel in selectors:
            candidates = el.find_elements(By.CSS_SELECTOR, sel)
            if candidates:
                return candidates[0]
    except Exception:
        pass
    return el



def _add_medium_tag(driver: webdriver.Chrome, tag_text: str, existing: list[str], scopes=None):
    tag = (tag_text or "").strip()
    if not tag:
        return existing
    tag_lower = tag.lower()
    if tag_lower in (existing or []):
        _log(f"INFO:TAG_SKIP_ALREADY_SET tag={tag}")
        return existing

    tag_selectors = _as_selector_list(SEL_MEDIUM["tags_input"])
    if not tag_selectors:
        _log("WARN:TAGS_SELECTOR_EMPTY")
        return existing or []

    tag_input = _locate_by_selectors(driver, tag_selectors, scopes=scopes)
    if not tag_input:
        _log("WARN:TAG_INPUT_NOT_FOUND")
        return existing or []

    tag_field = _resolve_tag_input_field(driver, tag_input) or tag_input
    try:
        attrs = {
            "id": tag_field.get_attribute("id"),
            "data-testid": tag_field.get_attribute("data-testid"),
            "role": tag_field.get_attribute("role"),
            "contenteditable": tag_field.get_attribute("contenteditable"),
        }
        _log(f"INFO:TAG_FIELD attrs={attrs}")
    except Exception:
        _log("INFO:TAG_FIELD attrs=<unavailable>")

    try:
        click_element_like_original(driver, tag_field)
    except Exception:
        try:
            driver.execute_script("arguments[0].focus();", tag_field)
        except Exception:
            _log("WARN:TAG_INPUT_FOCUS_FAIL")
            return existing or []

    _clear_tag_input(driver, tag_field)

    typed = False
    for attempt in range(2):
        try:
            _log(f"INFO:TAG_TYPE attempt={attempt+1} tag='{tag}'")
            _type_tag_characters(tag_field, tag)
            typed = True
            _log(f"INFO:TAG_TYPED tag='{tag}' via keystrokes")
            break
        except Exception:
            _sleep(0.05, 0.1)
            try:
                driver.execute_script(
                    """
                    const el = arguments[0], val = arguments[1];
                    if (el.isContentEditable) {
                        el.textContent = val;
                    } else {
                        el.value = val;
                    }
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    """,
                    tag_field,
                    tag,
                )
                typed = True
                _log(f"INFO:TAG_TYPED tag='{tag}' via script fallback")
                break
            except Exception as exc:
                if attempt == 1:
                    _log(f"WARN:TAG_TYPE_FAILED err={exc.__class__.__name__}")
    if not typed:
        return existing or []

    _sleep(0.05, 0.12)
    if not _confirm_tag_with_comma(driver, tag_field):
        _log(f"WARN:TAG_COMMA_FAILED tag={tag}")

    def _chip_added(drv: webdriver.Chrome):
        tags_now = _current_medium_tags(drv, tag_field)
        return tag_lower in tags_now

    try:
        WebDriverWait(driver, WAIT_SHORT).until(_chip_added)
    except TimeoutException:
        _log(f"WARN:TAG_ADD_TIMEOUT tag={tag}")

    updated = _current_medium_tags(driver, tag_field)
    if tag_lower in updated:
        _log(f"INFO:TAG_ADDED '{tag}'")
    return updated if updated else existing or []


def _normalize_medium_url(raw_url):
    if not raw_url:
        return None
    url = str(raw_url).strip()
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    path = parts.path or "/"
    if path.endswith("/edit"):
        path = path[:-5] or "/"
    normalized = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return normalized


def _extract_publish_link(driver: webdriver.Chrome):
    try:
        raw = driver.execute_script(
            "return (document.querySelector('[data-testid=\\'storyPublishShareLink\\']')?.href || document.querySelector('[data-testid=\\'post-sharelink-input\\']')?.value || document.location.href);"
        )
        url = _normalize_medium_url(raw)
        if url:
            return url
    except Exception:
        try:
            return _normalize_medium_url(driver.current_url)
        except Exception:
            return None


def _await_publish_url(driver: webdriver.Chrome, timeout: int = 10):
    def _condition(drv):
        try:
            url = drv.current_url
        except Exception:
            url = None
        if url and 'new-story' not in url and '/draft' not in url:
            clean = _normalize_medium_url(url)
            return clean or url
        link = _extract_publish_link(drv)
        if link and 'new-story' not in link:
            return link
        return False

    try:
        return WebDriverWait(driver, timeout).until(_condition)
    except TimeoutException:
        return _extract_publish_link(driver)


def _detect_publish_quota_block(driver: webdriver.Chrome, timeout: float = 5.0) -> bool:
    warning_text = (
        "The author of this story has published or scheduled the maximum of three stories in the past 24 hours."
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "div.overlay-content")
        except Exception:
            candidates = []
        for el in candidates:
            try:
                text = (el.text or "").strip()
            except Exception:
                continue
            if warning_text.lower() in text.lower():
                _log("ERROR:PUBLISH_LIMIT Medium báo đã đạt giới hạn 3 bài/24h")
                return True
        _sleep(0.2, 0.4)
    _log("INFO:PUBLISH_LIMIT không thấy cảnh báo giới hạn publish")
    return False


def _wait_publish_ready(driver: webdriver.Chrome, timeout: int = 20, require_body: bool = True):
    def _condition(drv):
        try:
            return drv.execute_script(
                """
                const requireBody = arguments[0] === true;
                const selectors = [
                    "button[data-testid='publishButton']",
                    "button.js-publishButton",
                    "button[data-action='publish']",
                    "button[data-delayed-action='show-prepublish']"
                ];
                let button = null;
                for (const sel of selectors) {
                    const cand = document.querySelector(sel);
                    if (cand) { button = cand; break; }
                }
                if (!button) return false;

                const style = window.getComputedStyle(button);
                const attr = (button.getAttribute('aria-disabled') || '').toLowerCase();
                const classList = Array.from(button.classList || []).map(cls => cls.toLowerCase());
                const actionAttr = (button.getAttribute('data-action') || '').toLowerCase();
                const delayedAttr = (button.getAttribute('data-delayed-action') || '').toLowerCase();

                const disabled = button.disabled === true
                    || attr === 'true'
                    || classList.includes('is-disabled')
                    || classList.includes('loading')
                    || classList.includes('button--disabledprimary')
                    || classList.includes('button--disabled')
                    || actionAttr === 'show-disabled-button-info'
                    || (actionAttr && actionAttr !== 'show-prepublish' && actionAttr !== 'publish')
                    || (delayedAttr === 'show-prepublish' && actionAttr !== 'show-prepublish')
                    || style.pointerEvents === 'none'
                    || parseFloat(style.opacity || '1') < 0.8;

                if (disabled) return false;
                if (actionAttr && actionAttr !== 'show-prepublish' && actionAttr !== 'publish') {
                    return false;
                }
                if (!actionAttr && delayedAttr === 'show-prepublish') {
                    return false;
                }

                const title = document.querySelector("[data-testid='editorTitleParagraph']");
                const titleText = title ? title.innerText.trim() : '';
                if (!titleText) return false;

                if (requireBody) {
                    const bodyNodes = Array.from(document.querySelectorAll("div.postArticle-content [data-testid='editorParagraphText']"))
                        .filter(el => !el.closest("[data-testid='editorTitleParagraph']"));
                    const hasBody = bodyNodes.some(node => (node.innerText || node.textContent || '').trim().length > 0);
                    if (!hasBody) return false;
                }

                const statusEl = document.querySelector('[data-testid=\"storyStatus\"], [data-testid=\"story-draft-status\"], .js-draftStatus');
                if (statusEl) {
                    const statusText = (statusEl.textContent || '').toLowerCase();
                    if (statusText.includes('saving') || statusText.includes('syncing')) {
                        return false;
                    }
                }
                return true;
                """,
                require_body,
            )
        except Exception:
            return False

    try:
        WebDriverWait(driver, timeout).until(_condition)
        _log("INFO:PUBLISH_READY button enabled and draft saved")
        return True
    except TimeoutException:
        _log("WARN:PUBLISH_READY_TIMEOUT button still disabled")
        return False


def click_publish_confirm_button(driver: webdriver.Chrome) -> bool:
    publish_xpath = (
        "//button[contains(@class,'js-publishButton') and contains(@class,'button--primary') "
        "and @data-action='publish' and .//span[contains(@class,'js-publishButtonText') "
        "and (normalize-space()='Publish now' or normalize-space()='Publish')]]"
    )
    try:
        button = WebDriverWait(driver, WAIT_MED).until(
            lambda d: d.find_element(By.XPATH, publish_xpath)
        )
    except Exception:
        _log("WARN:PUBLISH_CONFIRM không tìm thấy nút Publish now")
        return False
    try:
        button.click()
        _log("STEP:PUBLISH_CONFIRM click trực tiếp")
        return True
    except Exception:
        pass
    try:
        driver.execute_script(
            """
            const btn = arguments[0];
            if (!btn) return false;
            btn.scrollIntoView({block:'center', inline:'center'});
            const events = ['mouseover','mouseenter','mousemove','mousedown','mouseup','click'];
            for (const evt of events) {
                try {
                    btn.dispatchEvent(new MouseEvent(evt, {bubbles:true, cancelable:true, view:window}));
                } catch (err) {}
            }
            return true;
            """,
            button,
        )
        _log("STEP:PUBLISH_CONFIRM click bằng JavaScript")
        return True
    except Exception as exc:
        _log(f"WARN:PUBLISH_CONFIRM click thất bại err={exc.__class__.__name__}")
        return False

def open_publish_and_fill(driver: webdriver.Chrome, tags: Iterable[str] | None, publish_now: bool = True):
    try:
        btn = wait_vis(driver, By.CSS_SELECTOR, SEL_MEDIUM["publish_btn"], t=WAIT_MED)
        click_element_like_original(driver, btn)
        _log("STEP:OPEN_PUBLISH dialog launched")
    except Exception:
        pass
    _sleep(0.2, 0.5)

    if tags:
        _log("INFO:TAGS_SKIP skipping tag input per updated automation")

    if publish_now:

        def _is_publish_dialog_open() -> bool:
            try:
                dialog = driver.execute_script(
                    """
                    const selectors = [
                        "[data-testid='publishDialog']",
                        "[data-testid='prepublish-dialog']",
                        "[data-testid='publishMenu']",
                        "div.overlay.overlay--white"
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) return true;
                    }
                    return false;
                    """
                )
                return bool(dialog)
            except Exception:
                try:
                    candidates = driver.find_elements(
                        By.CSS_SELECTOR,
                        "[data-testid='publishDialog'], [data-testid='prepublish-dialog'], div.overlay.overlay--white",
                    )
                    for cand in candidates:
                        try:
                            if cand.is_displayed():
                                return True
                        except Exception:
                            continue
                except Exception:
                    pass
                return False

        def _wait_publish_dialog_close(timeout: float = 8.0) -> bool:
            end = time.time() + timeout
            while time.time() < end:
                if not _is_publish_dialog_open():
                    return True
                _sleep(0.2, 0.4)
            return False
        def _click_publish_once(attempt: int, timeout: int) -> bool:
            end = time.time() + timeout
            while time.time() < end:
                if click_publish_confirm_button(driver):
                    return True
                _sleep(0.2, 0.4)
            _log(f"WARN:PUBLISH_BUTTON_NOT_FOUND attempt={attempt}")
            return False

        if _click_publish_once(1, WAIT_MED):
            if not _wait_publish_dialog_close(timeout=6.0):
                _log("WARN:PUBLISH_DIALOG_STILL_OPEN retrying confirm button")
                _sleep(0.35, 0.6)
                if _click_publish_once(2, WAIT_SHORT):
                    if not _wait_publish_dialog_close(timeout=6.0):
                        _log("WARN:PUBLISH_DIALOG_PERSIST after second attempt")
                else:
                    _log("WARN:PUBLISH_SECOND_ATTEMPT_FAILED publish dialog may still be open")


def medium_publish_article_selenium(
    driver: webdriver.Chrome,
    title: str,
    content: str,
    tags: Iterable[str] | None = None,
    publish_now: bool = True,
    retries: int = MEDIUM_SELENIUM_RETRIES,
):
    # input("STEP:COMPLETE publishing flow finished Press Enter to continue...")
    last_exc = None
    try:
        _log("STEP:PUBLISH_START opening Medium editor")
        open_medium_editor(driver)
        _log("STEP:PUBLISH_EDITOR_OPEN filling title and body")
        fill_title_and_body(driver, title, content)
        _log("STEP:PUBLISH_BODY_FILLED waiting for publish button to be ready")
        _wait_publish_ready(driver)
        _log("STEP:PUBLISH_READY opening publish dialog and filling details")
        open_publish_and_fill(driver, tags, publish_now)
        _log("STEP:PUBLISH_DIALOG_FILLED clicking publish confirm button")
        click_publish_confirm_button(driver)
        _log("STEP:PUBLISH_CLICKED checking for publish quota block")
        if _detect_publish_quota_block(driver):
            _log("ERROR:PUBLISH_QUOTA Medium publish quota exceeded (3 posts per 24 hours)")
            raise RuntimeError("Medium publish quota exceeded (3 posts per 24 hours).")
        _log("STEP:PUBLISH_QUOTA_OK waiting for publish URL")
        publish_url = None
        publish_url = _await_publish_url(driver, timeout=10)
        _log(f"STEP:COMPLETE publishing flow finished url={publish_url}")
        return publish_url
    except Exception as e:
        last_exc = e
        _log(f"WARN:PUBLISH_ATTEMPT_FAILED  err={e.__class__.__name__}")
        raise e
    return None

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
def _paste_from_clipboard_into_element(driver: webdriver.Chrome, element, ensure_click: bool = True) -> bool:
    if element is None:
        return False
    try:
        if ensure_click:
            actions = webdriver.ActionChains(driver)
            actions.move_to_element(element)
            actions.pause(0.05)
            actions.click()
            actions.perform()
    except Exception:
        try:
            element.click()
        except Exception:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                    element,
                )
            except Exception:
                return False
    _sleep(0.05, 0.1)
    try:
        actions = webdriver.ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
    except Exception:
        _log("WARN:BODY_CLIPBOARD paste key sequence failed")
        return False
    _sleep(0.2, 0.3)
    return True
