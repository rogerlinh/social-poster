#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Social poster GUI utilising Selenium-based Medium automation.

The original implementation in this repository was lost. This file rebuilds the
core behaviour so that users can keep publishing Medium posts from a desktop UI.
Key goals:
    * Provide a simple CustomTkinter interface to compose Medium content.
    * Offer basic formatting helpers that insert HTML snippets (bold, italic,
      headings, quotes, links, images, code blocks) so the user can craft posts
      visually without leaving the tool.
    * Run the Selenium workflow in a worker thread, forwarding log messages back
      to the GUI via a queue.
    * Integrate with the existing `medium_selenium` module for the actual
      browser automation. No assumptions are made about LinkedIn publishing -
      the UI still exposes the switch but the runner reports that LinkedIn is
      currently unsupported (the prior logic is unavailable).
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from tkhtmlview import HTMLLabel  # type: ignore
except Exception as exc:  # pragma: no cover - optional dependency
    HTMLLabel = None
    tkhtml_import_err: Optional[Exception] = exc
else:
    tkhtml_import_err = None

try:
    from medium_selenium import (
        start_profile as medium_start_profile,
        medium_publish_article_selenium,
        load_medium_page as medium_load_page,
        DEFAULT_MEDIUM_TITLE,
        DEFAULT_MEDIUM_BODY_HTML,
        render_medium_body_text,
    )
except Exception as exc:  # pragma: no cover - handled at runtime
    medium_start_profile = None
    medium_selenium_import_err = exc
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
    def render_medium_body_text(body_html: str, title_hint: str | None = None) -> str:
        return (body_html or "").strip()

else:
    medium_selenium_import_err = None

from config import (
    MEDIUM_DRIVER,
    CHROME_PROFILE_DIR,
    SCHEDULE_TABLE_PATH,
    SCHEDULE_CONCURRENCY,
    SCHEDULE_SHOW_CONSOLE,
)

try:
    import schedule_reader
except Exception:
    schedule_reader = None

CHROME_EXECUTABLE_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
MEDIUM_NEW_STORY_URL = "https://medium.com/new-story"
MEDIUM_LOGIN_URL = "https://medium.com/m/signin"


def threaded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to run function in a daemon thread."""

    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread

    return wrapper


def fmt_bool(value: bool) -> str:
    return "Yes" if value else "No"


@dataclass
class MediumJobConfig:
    profile_path: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    headless: bool = False
    keep_browser_open: bool = True
    manual_login: bool = False
    publish_now: bool = True
    profile_name: str = CHROME_PROFILE_DIR or "Default"
    manual_login_timeout: int = 180  # seconds


@dataclass
class RunnerConfig:
    platform: str
    medium: Optional[MediumJobConfig] = None


class Runner(threading.Thread):
    """Background worker responsible for publishing posts."""

    def __init__(self, config: RunnerConfig, out_queue: queue.Queue, stop_evt: threading.Event):
        super().__init__(daemon=True)
        self.config = config
        self.out_queue = out_queue
        self.stop_evt = stop_evt

    def _put(self, level: str, message: str) -> None:
        self.out_queue.put((level, message))

    def log(self, message: str) -> None:
        self._put("info", message)

    def warn(self, message: str) -> None:
        self._put("warn", message)

    def error(self, message: str) -> None:
        self._put("error", message)

    def run(self) -> None:  # pragma: no cover - integration path
        try:
            if self.config.platform == "Medium":
                if not self.config.medium:
                    raise ValueError("Missing Medium configuration")
                self._run_medium(self.config.medium)
            elif self.config.platform == "LinkedIn":
                self.warn(
                    "LinkedIn automation has not been reconstructed yet. "
                    "Please publish manually for now."
                )
            else:
                self.warn(f"Unsupported platform: {self.config.platform}")
            self._put("finished", "Done")
        except Exception as exc:  # pylint: disable=broad-except
            self.error(f"Failure: {exc}")
            self._put("finished", "Aborted")


class AutoPostWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Autopost Scheduler")
        self.geometry("420x220")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._hide)
        self.table_var = tk.StringVar(value=str(Path(SCHEDULE_TABLE_PATH).expanduser()))
        self.limit_var = tk.IntVar(value=max(1, int(SCHEDULE_CONCURRENCY)))
        self.console_var = tk.BooleanVar(value=bool(SCHEDULE_SHOW_CONSOLE))
        self._running = False
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": (10, 4)}
        ctk.CTkLabel(self, text="Excel/CSV file").grid(row=0, column=0, sticky="w", **pad)
        entry = ctk.CTkEntry(self, textvariable=self.table_var, width=260)
        entry.grid(row=0, column=1, sticky="ew", pady=(10, 4))
        ctk.CTkButton(self, text="Browse", command=self._choose_file).grid(
            row=0, column=2, padx=10, pady=(10, 4)
        )

        ctk.CTkLabel(self, text="Concurrency").grid(row=1, column=0, sticky="w", **pad)
        spin = ctk.CTkEntry(self, textvariable=self.limit_var, width=80)
        spin.grid(row=1, column=1, sticky="w", pady=(4, 4))

        ctk.CTkCheckBox(self, text="Open new console per email", variable=self.console_var).grid(
            row=2, column=0, columnspan=3, padx=12, pady=(6, 4), sticky="w"
        )

        self.run_btn = ctk.CTkButton(self, text="Run Schedule", command=self._start_schedule)
        self.run_btn.grid(row=3, column=0, columnspan=3, padx=12, pady=(12, 10), sticky="ew")

    def _hide(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.focus()

    def _choose_file(self):
        filename = filedialog.askopenfilename(
            title="Select schedule file",
            filetypes=[("Spreadsheet", "*.csv;*.xlsx;*.xls"), ("All files", "*.*")],
        )
        if filename:
            self.table_var.set(filename)

    def _start_schedule(self):
        if self._running:
            messagebox.showinfo("Autopost", "Scheduler is already running.")
            return
        if schedule_reader is None:
            messagebox.showerror("Autopost", "schedule_reader module is unavailable.")
            return
        table = self.table_var.get().strip()
        if not table:
            messagebox.showerror("Autopost", "Please choose a schedule file.")
            return
        try:
            table_path = Path(table)
        except Exception as exc:
            messagebox.showerror("Autopost", f"Invalid path: {exc}")
            return
        try:
            limit = max(1, int(self.limit_var.get()))
        except Exception:
            messagebox.showerror("Autopost", "Concurrency must be a positive integer.")
            return
        show_console = bool(self.console_var.get())
        self._running = True
        self.run_btn.configure(state="disabled", text="Running...")
        threading.Thread(
            target=self._run_schedule,
            args=(table_path, limit, show_console),
            daemon=True,
        ).start()

    def _run_schedule(self, table_path: Path, limit: int, show_console: bool):
        try:
            schedule_reader.main(table=table_path, limit=limit, show_console=show_console)
            messagebox.showinfo("Autopost", "Schedule run completed.")
        except Exception as exc:
            messagebox.showerror("Autopost", f"Schedule run failed: {exc}")
        finally:
            self._running = False
            self.run_btn.configure(state="normal", text="Run Schedule")

    # --------------------------------------------------------------------- Medium

    def _run_medium(self, cfg: MediumJobConfig) -> None:
        if medium_selenium_import_err is not None:
            raise RuntimeError(f"Cannot import medium_selenium: {medium_selenium_import_err}")

        if medium_start_profile is None:
            raise RuntimeError("medium_start_profile unavailable")

        if MEDIUM_DRIVER.lower() != "selenium":
            raise RuntimeError(
                f"MEDIUM_DRIVER={MEDIUM_DRIVER} is not supported by this rebuilt tool. "
                "Only 'selenium' is currently implemented."
            )

        if cfg.headless:
            self.warn(
                "Headless flag requested but Selenium profile launcher does not currently "
                "support headless mode. Proceeding with visible browser window."
            )

        profile_path = Path(cfg.profile_path).expanduser()
        if not profile_path.exists():
            self.log(f"Creating profile directory: {profile_path}")
            profile_path.mkdir(parents=True, exist_ok=True)

        self.log("Launching Chrome with Medium profile...")
        driver = medium_start_profile(
            user_data_dir=str(profile_path),
            profile_dir=cfg.profile_name or "Default",
        )

        try:
            self.log(f"Driver ready. keep_browser_open={fmt_bool(cfg.keep_browser_open)}")
            if self.stop_evt.is_set():
                self.warn("Stop requested before navigation.")
                return

            if cfg.manual_login:
                self._handle_manual_login(driver, cfg)
                if self.stop_evt.is_set():
                    return

            self.log("Opening Medium new-story page...")
            try:
                medium_load_page(driver, MEDIUM_NEW_STORY_URL, attempts=3)
            except TimeoutException:
                self.error("Medium refused the connection (ERR_CONNECTION_REFUSED) after three automatic retries.")
                raise
            except WebDriverException as exc:
                if "ERR_CONNECTION_REFUSED" in str(exc):
                    self.error("Chrome reported ERR_CONNECTION_REFUSED when opening Medium. Check your connection or VPN and try again.")
                raise
            time.sleep(2)
            self.log(
                "When the editor loads, type the story title manually in Chrome. "
                "The automation will continue once the Publish button is enabled."
            )

            tags = cfg.tags[:5]
            self.log(
                f"Publishing Medium article | title='{cfg.title[:40]}' | "
                f"tags={tags if tags else '(none)'}"
            )
            print(f"Publishing Medium article | title='{cfg.title[:40]}' | "
                f"tags={tags if tags else '(none)'}")
            publish_url = medium_publish_article_selenium(
                driver=driver,
                title=cfg.title,
                content=cfg.content,
                tags=tags,
                publish_now=cfg.publish_now,
            )
            print(f"Published URL: {publish_url}")
            if publish_url:
                self.log(f"Medium publish workflow completed. URL: {publish_url}")
                self._put('success', f"Medium URL: {publish_url}")
            else:
                self.log("Medium publish workflow completed.")
        finally:
            if not cfg.keep_browser_open:
                self.log("Closing browser window.")
                try:
                    driver.quit()
                except Exception:
                    pass

    def _handle_manual_login(self, driver, cfg: MediumJobConfig) -> None:
        self.log("Manual login requested. Opening Medium login page.")
        driver.get(MEDIUM_LOGIN_URL)
        self.log(
            "Please authenticate in Chrome. The automation waits until you close this prompt "
            "or the timeout passes."
        )
        timeout = max(30, cfg.manual_login_timeout)
        start_ts = time.monotonic()

        def finished() -> bool:
            try:
                url = driver.current_url
            except Exception:
                return False
            return url.startswith(MEDIUM_NEW_STORY_URL)

        while not self.stop_evt.is_set():
            if finished():
                self.log("Detected Medium editor. Proceeding with publish flow.")
                return
            if (time.monotonic() - start_ts) > timeout:
                self.warn(
                    f"Manual login timeout ({timeout}s) reached. Continuing with automation."
                )
                return
            time.sleep(1.0)


# ---------------------------------------------------------------------- GUI Layer

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Social Poster")
        self.geometry("1024x720")
        ctk.set_appearance_mode("dark")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.is_running = False
        self.stop_evt = threading.Event()
        self.out_queue: queue.Queue = queue.Queue()
        self.runner: Optional[Runner] = None

        self.platform_var = tk.StringVar(value="Medium")
        self.medium_profile_var = tk.StringVar(value=str(Path.cwd() / "profile medium"))
        self.medium_profile_name_var = tk.StringVar(value=CHROME_PROFILE_DIR or "Default")
        self.title_var = tk.StringVar(value=DEFAULT_MEDIUM_TITLE)
        self.headless_var = tk.BooleanVar(value=False)
        self.keep_open_var = tk.BooleanVar(value=True)
        self.manual_login_var = tk.BooleanVar(value=False)
        self.manual_login_timeout_var = tk.IntVar(value=180)
        self.publish_now_var = tk.BooleanVar(value=True)
        self.preview_supports_html = HTMLLabel is not None
        self.preview_widget: Any | None = None
        self._preview_update_job: Optional[str] = None
        self.mode_var = tk.StringVar(value="Manual")
        self.schedule_path_var = tk.StringVar(value=str(Path(SCHEDULE_TABLE_PATH).expanduser()))
        self.schedule_limit_var = tk.IntVar(value=max(1, int(SCHEDULE_CONCURRENCY)))
        self.schedule_console_var = tk.BooleanVar(value=bool(SCHEDULE_SHOW_CONSOLE))
        self._schedule_running = False

        self._build_ui()
        self.log_box_write("info", "Ready. Fill in the details and press Publish.")
        self.after(200, self._poll_queue)
        self.autopost_window: AutoPostWindow | None = None
        if schedule_reader is not None:
            self.autopost_window = AutoPostWindow(self)
            self.autopost_window.lift()

    def _build_ui(self) -> None:
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        form = ctk.CTkFrame(main)
        form.grid(row=0, column=0, padx=(0, 8), pady=8, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=1)
        form.rowconfigure(8, weight=1)

        # Platform selector
        ctk.CTkLabel(form, text="Platform").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        platform_btn = ctk.CTkSegmentedButton(
            form,
            values=["Medium", "LinkedIn"],
            variable=self.platform_var,
            command=self._update_platform_views,
        )
        platform_btn.grid(row=0, column=1, columnspan=2, padx=10, pady=(10, 4), sticky="ew")

        # Medium specific inputs
        self.medium_section = ctk.CTkFrame(form)
        self.medium_section.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=0, pady=(4, 4))
        self.medium_section.columnconfigure(1, weight=1)
        self.medium_section.columnconfigure(2, weight=1)
        self._build_medium_section(self.medium_section)

        # Content editor
        ctk.CTkLabel(form, text="Content").grid(row=6, column=0, padx=10, pady=(10, 4), sticky="w")
        toolbar = ctk.CTkFrame(form)
        toolbar.grid(row=6, column=1, columnspan=2, padx=10, pady=(10, 4), sticky="ew")
        toolbar.columnconfigure(tuple(range(7)), weight=1)
        self._add_toolbar_buttons(toolbar)

        actions = ctk.CTkFrame(form)
        actions.grid(row=7, column=0, columnspan=3, padx=10, pady=(0, 6), sticky="ew")
        actions.columnconfigure((0, 1, 2), weight=1)

        self.publish_button = ctk.CTkButton(
            actions,
            text="Publish",
            command=self.start_run,
            fg_color="#2E7D32",
            hover_color="#1B5E20",
        )
        self.publish_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancel",
            command=self.stop_run,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        self.autopost_button = ctk.CTkButton(
            actions,
            text="Autopost Scheduler",
            command=self.show_autopost_window,
            fg_color="#455A64",
            hover_color="#263238",
        )
        self.autopost_button.grid(row=0, column=2, padx=4, pady=4, sticky="ew")

        editor_container = ctk.CTkFrame(form)
        editor_container.grid(
            row=8, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew"
        )
        editor_container.columnconfigure(0, weight=1)
        editor_container.rowconfigure(0, weight=1)
        editor_container.rowconfigure(1, weight=1)

        self.content_box = ctk.CTkTextbox(editor_container, height=220)
        self.content_box.grid(row=0, column=0, padx=6, pady=(6, 8), sticky="nsew")
        self.content_box.bind("<KeyRelease>", self._on_content_input)
        self.content_box.bind("<<Paste>>", self._on_content_input)
        self.content_box.bind("<<Cut>>", self._on_content_input)
        self.content_box.insert("1.0", DEFAULT_MEDIUM_BODY_HTML)
        self._schedule_preview_update(50)

        preview_frame = ctk.CTkFrame(editor_container)
        preview_frame.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(preview_frame, text="Rich Preview").grid(
            row=0, column=0, padx=6, pady=(6, 2), sticky="w"
        )

        if self.preview_supports_html:
            holder = tk.Frame(preview_frame, background="white", borderwidth=0, highlightthickness=0)
            holder.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)
            self.preview_widget = HTMLLabel(holder, html=self._empty_preview_html(), background="white")
            self.preview_widget.pack(fill="both", expand=True)
        else:
            message = self._preview_fallback_message()
            preview_box = ctk.CTkTextbox(preview_frame, state="normal")
            preview_box.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")
            preview_box.insert("1.0", message)
            preview_box.configure(state="disabled")
            self.preview_widget = preview_box

        # Footer controls
        log_frame = ctk.CTkFrame(main)
        log_frame.grid(row=0, column=1, padx=(8, 0), pady=8, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Activity Log").grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky="w"
        )
        self.log_box = ctk.CTkTextbox(log_frame, state="disabled")
        self.log_box.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

    def _build_medium_section(self, frame: ctk.CTkFrame) -> None:
        ctk.CTkLabel(frame, text="Chrome profile folder").grid(
            row=0, column=0, padx=10, pady=6, sticky="w"
        )
        profile_entry = ctk.CTkEntry(frame, textvariable=self.medium_profile_var)
        profile_entry.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        ctk.CTkButton(frame, text="Browse", command=self._choose_profile_dir).grid(
            row=0, column=2, padx=(0, 10), pady=6, sticky="ew"
        )

        ctk.CTkLabel(
            frame, text="Chrome profile name (folder inside profile, optional)"
        ).grid(
            row=1, column=0, padx=10, pady=6, sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=self.medium_profile_name_var).grid(
            row=1, column=1, padx=10, pady=6, sticky="ew"
        )

        ctk.CTkLabel(frame, text="Title").grid(row=2, column=0, padx=10, pady=6, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.title_var).grid(
            row=2, column=1, columnspan=2, padx=10, pady=6, sticky="ew"
        )

        ctk.CTkCheckBox(
            frame, text="Headless (experimental)", variable=self.headless_var
        ).grid(row=3, column=0, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(
            frame, text="Keep browser open", variable=self.keep_open_var
        ).grid(row=3, column=1, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(
            frame, text="Require manual login", variable=self.manual_login_var
        ).grid(row=3, column=2, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(frame, text="Manual login timeout (s)").grid(
            row=4, column=0, padx=10, pady=6, sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=self.manual_login_timeout_var).grid(
            row=4, column=1, padx=10, pady=6, sticky="ew"
        )
        ctk.CTkCheckBox(
            frame, text="Publish now", variable=self.publish_now_var
        ).grid(row=4, column=2, padx=10, pady=6, sticky="w")

    def _add_toolbar_buttons(self, toolbar: ctk.CTkFrame) -> None:
        buttons = [
            ("B", lambda: self._wrap_selection("strong")),
            ("I", lambda: self._wrap_selection("em")),
            ("Link", self._insert_link),
            ("H2", lambda: self._wrap_selection("h2", placeholder="Section heading")),
            ("Quote", lambda: self._wrap_selection("blockquote", placeholder="Quote text")),
            ("Code", self._insert_code_block),
            ("Img", self._insert_image),
        ]
        for idx, (label, command) in enumerate(buttons):
            btn = ctk.CTkButton(toolbar, text=label, command=command, height=30)
            btn.grid(row=0, column=idx, padx=3, pady=3, sticky="ew")

    # ---------------------------------------------------------------- preview helpers

    def _preview_fallback_message(self) -> str:
        lines = ["Install tkhtmlview (pip install tkhtmlview) to enable rich preview output."]
        if tkhtml_import_err is not None:
            lines.append(f"Import error: {tkhtml_import_err}")
        return "\n".join(lines)

    def _empty_preview_html(self) -> str:
        return "<p><em>Enter content to preview.</em></p>"

    def _on_content_input(self, _event: Optional[tk.Event] = None) -> None:
        self._schedule_preview_update()

    def _schedule_preview_update(self, delay_ms: int = 250) -> None:
        if self._preview_update_job:
            try:
                self.after_cancel(self._preview_update_job)
            except Exception:
                pass
        self._preview_update_job = self.after(delay_ms, self._refresh_preview)

    def _refresh_preview(self) -> None:
        self._preview_update_job = None
        raw = self.content_box.get("1.0", "end-1c")
        html_fragment = self._build_preview_html(raw)
        if self.preview_supports_html and self.preview_widget and hasattr(self.preview_widget, "set_html"):
            try:
                self.preview_widget.set_html(html_fragment)
                fit_height = getattr(self.preview_widget, "fit_height", None)
                if callable(fit_height):
                    fit_height()
            except Exception as exc:
                self.preview_widget.set_html(self._preview_error_html(exc))
                fit_height = getattr(self.preview_widget, "fit_height", None)
                if callable(fit_height):
                    fit_height()
        elif isinstance(self.preview_widget, ctk.CTkTextbox):
            self.preview_widget.configure(state="normal")
            self.preview_widget.delete("1.0", "end")
            title_hint = self.title_var.get().strip() or DEFAULT_MEDIUM_TITLE
            text_version = render_medium_body_text(raw, title_hint)
            if not text_version.strip():
                text_version = "Preview unavailable without tkhtmlview."
            self.preview_widget.insert("1.0", text_version)
            self.preview_widget.configure(state="disabled")

    def _build_preview_html(self, raw: str) -> str:
        content = raw.strip()
        if not content:
            return self._empty_preview_html()
        if re.search(r"<[^>]+>", content):
            return content
        paragraphs: list[str] = []
        buffer: list[str] = []
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if line.strip():
                buffer.append(html.escape(line))
            elif buffer:
                paragraphs.append("<p>" + "<br/>".join(buffer) + "</p>")
                buffer = []
        if buffer:
            paragraphs.append("<p>" + "<br/>".join(buffer) + "</p>")
        return "".join(paragraphs) or self._empty_preview_html()

    def _html_to_plain_preview(self, fragment: str) -> str:
        text = re.sub(r"<br\\s*/?>", "\n", fragment, flags=re.I)
        text = re.sub(r"</p>", "\n\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text).strip()

    def _preview_error_html(self, exc: Exception) -> str:
        safe_message = html.escape(str(exc))
        return f"<p><strong>Preview error:</strong> {safe_message}</p>"

    # ---------------------------------------------------------------- selection helpers

    def _get_selection(self) -> tuple[str, str, str, bool]:
        try:
            start = self.content_box.index("sel.first")
            end = self.content_box.index("sel.last")
            text = self.content_box.get(start, end)
            return start, end, text, True
        except tk.TclError:
            index = self.content_box.index("insert")
            return index, index, "", False

    def _replace_selection(
        self,
        start: str,
        end: str,
        snippet: str,
        select_inner: Optional[tuple[int, int]] = None,
    ) -> None:
        self.content_box.delete(start, end)
        self.content_box.insert(start, snippet)
        self.content_box.tag_remove("sel", "1.0", "end")
        if select_inner:
            begin = self.content_box.index(f"{start}+{select_inner[0]}c")
            finish = self.content_box.index(f"{start}+{select_inner[1]}c")
            self.content_box.tag_add("sel", begin, finish)
            self.content_box.mark_set("insert", finish)
        else:
            self.content_box.mark_set("insert", f"{start}+{len(snippet)}c")
        self.content_box.focus_set()
        self._schedule_preview_update()

    def _wrap_selection(self, tag: str, placeholder: Optional[str] = None) -> None:
        start, end, text, has_selection = self._get_selection()
        inner = text if has_selection and text else (placeholder or "")
        snippet = f"<{tag}>{inner}</{tag}>"
        select_inner = None
        if not has_selection and inner:
            offset = len(tag) + 2  # <tag>
            select_inner = (offset, offset + len(inner))
        self._replace_selection(start, end, snippet, select_inner)

    def _insert_link(self) -> None:
        start, end, text, has_selection = self._get_selection()
        url = simpledialog.askstring("Insert link", "URL:", parent=self)
        if not url:
            return
        display = text.strip() if has_selection and text.strip() else url
        escaped_url = html.escape(url, quote=True)
        escaped_display = html.escape(display)
        snippet = f'<a href="{escaped_url}">{escaped_display}</a>'
        cursor = len(f'<a href="{escaped_url}">')
        self._replace_selection(start, end, snippet, (cursor, cursor + len(escaped_display)))

    def _insert_image(self) -> None:
        start, end, _, _ = self._get_selection()
        url = simpledialog.askstring("Insert image", "Image URL:", parent=self)
        if not url:
            return
        alt = simpledialog.askstring("Insert image", "Alt text (optional):", parent=self) or ""
        snippet = f'<figure><img src="{html.escape(url, quote=True)}" alt="{html.escape(alt, quote=True)}"/></figure>'
        self._replace_selection(start, end, snippet)

    def _insert_code_block(self) -> None:
        start, end, text, has_selection = self._get_selection()
        inner = text if has_selection and text else "code snippet"
        escaped = html.escape(inner)
        snippet = f"<pre><code>{escaped}</code></pre>"
        base = len("<pre><code>")
        self._replace_selection(start, end, snippet, (base, base + len(escaped)))

    # ---------------------------------------------------------------- events

    def _update_platform_views(self, *_args) -> None:
        platform = self.platform_var.get()
        state = "normal" if platform == "Medium" else "disabled"
        for child in self.medium_section.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
        if platform != "Medium":
            self.log_box_write(
                "warn",
                "LinkedIn automation is currently unavailable. "
                "Only Medium publishing is supported.",
            )

    def _choose_profile_dir(self) -> None:
        directory = filedialog.askdirectory()
        if directory:
            self.medium_profile_var.set(directory)

    # ---------------------------------------------------------------- Runner control

    def start_run(self) -> None:

        if self.is_running:
            messagebox.showwarning("Busy", "A job is already running.")
            return

        platform = self.platform_var.get()

        try:
            cfg = self._build_runner_config(platform)
        except ValueError as exc:
            messagebox.showerror("Configuration error", str(exc))
            return

        self.log_box_write("info", f"Starting job for {platform}...")
        self.stop_evt.clear()
        self.out_queue = queue.Queue()
        self.runner = Runner(cfg, self.out_queue, self.stop_evt)
        self.runner.start()
        self.is_running = True
        self.publish_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")

    def stop_run(self) -> None:
        if not self.is_running:
            return
        self.log_box_write("warn", "Stop requested. Waiting for worker to finish...")
        self.stop_evt.set()
        if self.runner and self.runner.is_alive():
            self.runner.join(timeout=5)
        self.is_running = False
        self.publish_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def show_autopost_window(self) -> None:
        if self.autopost_window is None:
            messagebox.showerror("Autopost", "Batch scheduler module unavailable.")
            return
        self.autopost_window.show()

    def _build_runner_config(self, platform: str) -> RunnerConfig:
        if platform == "Medium":
            profile_path = self.medium_profile_var.get().strip()
            if not profile_path:
                raise ValueError("Chrome profile folder is required.")
            title = self.title_var.get().strip()
            if not title:
                raise ValueError("Title cannot be empty.")
            content = self.content_box.get("1.0", "end-1c").strip()
            if not content:
                raise ValueError("Content cannot be empty.")
            medium_cfg = MediumJobConfig(
                profile_path=profile_path,
                profile_name=self.medium_profile_name_var.get().strip() or "Default",
                title=title,
                content=content,
                tags=[],
                headless=self.headless_var.get(),
                keep_browser_open=self.keep_open_var.get(),
                manual_login=self.manual_login_var.get(),
                manual_login_timeout=self.manual_login_timeout_var.get(),
                publish_now=self.publish_now_var.get(),
            )
            return RunnerConfig(platform="Medium", medium=medium_cfg)

        # Fallback configuration for unsupported platform
        return RunnerConfig(platform=platform)

    # ---------------------------------------------------------------- logging helpers

    def _poll_queue(self) -> None:
        try:
            while True:
                level, message = self.out_queue.get_nowait()
                self.log_box_write(level, message)
                if level == "finished":
                    self.is_running = False
                    self.publish_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def log_box_write(self, level: str, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level.upper():7}] {message}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", formatted)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main() -> None:  # pragma: no cover
    schedule_path = Path(SCHEDULE_TABLE_PATH).expanduser()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
"""  """
