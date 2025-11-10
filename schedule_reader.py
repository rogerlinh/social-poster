from __future__ import annotations

import csv
import io
import inspect
import queue
import threading
import time
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from multiprocessing import Process
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List

from config import (
    SCHEDULE_TABLE_PATH,
    SCHEDULE_CONCURRENCY,
    CHROME_USER_DATA_DIR,
    SCHEDULE_SHOW_CONSOLE,
)
from console_utils import ensure_own_console

if TYPE_CHECKING:
    from social_poster import MediumJobConfig, RunnerConfig, Runner

CSV_PATH = Path(SCHEDULE_TABLE_PATH)
ENCODING_CANDIDATES: tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "utf-16",
    "cp1258",
    "latin-1",
)
DEFAULT_LIMIT = SCHEDULE_CONCURRENCY
DEFAULT_SHOW_CONSOLE = bool(SCHEDULE_SHOW_CONSOLE)
try:  # optional Excel support
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None
try:
    from openpyxl import load_workbook  # type: ignore
except Exception:  # pragma: no cover
    load_workbook = None


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


def _preview(value: str, limit: int = 30) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


_MOJIBAKE_MARKERS = ("Ã", "Â", "Ð", "‰", "Ê", "¤", "�")


def _normalize_field(value: Any) -> str:
    text = _clean(value)
    if not text:
        return text
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        try:
            repaired = text.encode("latin-1", errors="strict").decode("utf-8")
            return repaired.strip()
        except Exception:
            return text
    return text

_MOJIBAKE_MARKERS = ("Ã", "Â", "Ð", "Ê", "¤", "�")


def _is_xlsx(path: Path) -> bool:
    lower = path.name.lower()
    if lower.endswith((".xlsx", ".xls")):
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"PK"
    except Exception:
        return False


def _read_csv_records(path: Path) -> List[Dict[str, Any]]:
    data = path.read_bytes()
    text: str | None = None
    for encoding in ENCODING_CANDIDATES:
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _read_excel_records(path: Path) -> List[Dict[str, Any]]:
    if pd is not None:
        df = pd.read_excel(path)  # type: ignore[arg-type]
        return df.fillna("").to_dict(orient="records")
    if load_workbook is None:
        raise RuntimeError("openpyxl is required for Excel schedules")
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(value or "").strip() for value in rows[0]]
    records: List[Dict[str, Any]] = []
    for row in rows[1:]:
        record: Dict[str, Any] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            record[header] = row[idx] if idx < len(row) else ""
        records.append(record)
    return records


def read_schedule(path: Path = CSV_PATH) -> Dict[str, List[str]]:
    path = path.expanduser()
    if path.suffix.lower() in (".xlsx", ".xls") or _is_xlsx(path):
        raw_rows = _read_excel_records(path)
        _log(f"INFO:READ_SCHEDULE excel rows={len(raw_rows)} file={path}")
    else:
        raw_rows = _read_csv_records(path)
        _log(f"INFO:READ_SCHEDULE csv rows={len(raw_rows)} file={path}")

    fields: Dict[str, List[str]] = {
        "platform": [],
        "email": [],
        "type": [],
        "title": [],
        "content": [],
        "images": [],
        "schedule_time": [],
        "profile_path": [],
    }

    for row in raw_rows:
        for key in fields:
            fields[key].append(_normalize_field(row.get(key, "")))

    times_preview = ", ".join(_preview(t, 8) or "-" for t in fields["schedule_time"])
    _log(f"INFO:SCHEDULE_TIMES {times_preview or '<none>'}")
    return fields


def build_jobs(columns: Dict[str, List[str]]) -> List["ScheduleJob"]:
    count = max((len(values) for values in columns.values()), default=0)
    jobs: List[ScheduleJob] = []
    for idx in range(count):
        data = {key: columns[key][idx] if idx < len(columns[key]) else "" for key in columns}
        if not any(data.values()):
            continue
        jobs.append(ScheduleJob.from_dict(data))
    _log(f"INFO:BUILD_JOBS total={len(jobs)}")
    for idx, job in enumerate(jobs, start=1):
        _log(
            f"INFO:JOB_SUMMARY #{idx} platform={job.platform} time='{job.schedule_time or 'imm'}' title='{_preview(job.title)}' content='{_preview(job.content)}'"
        )
    return jobs


@dataclass
class ScheduleJob:
    platform: str
    email: str
    type: str
    title: str
    content: str
    images: str
    schedule_time: str
    profile_path: str

    @classmethod
    def from_dict(cls, row: Dict[str, str]) -> "ScheduleJob":
        return cls(
            platform=_normalize_field(row.get("platform", "")) or "Medium",
            email=_normalize_field(row.get("email", "")),
            type=_normalize_field(row.get("type", "")) or "medium",
            title=_normalize_field(row.get("title", "")) or "Untitled",
            content=_normalize_field(row.get("content", "")),
            images=_normalize_field(row.get("images", "")),
            schedule_time=_normalize_field(row.get("schedule_time", "")),
            profile_path=_normalize_field(row.get("profile_path", "")),
        )

    def to_runner_config(self) -> "RunnerConfig":
        from social_poster import MediumJobConfig, RunnerConfig

        platform = self.platform or "Medium"
        if platform.lower() != "medium":
            return RunnerConfig(platform=platform)
        medium_cfg = MediumJobConfig(
            profile_path=self.profile_path or CHROME_USER_DATA_DIR,
            title=self.title or "Untitled",
            content=self.content or "",
        )
        return RunnerConfig(platform="Medium", medium=medium_cfg)


def _run_single_job(job: ScheduleJob) -> None:
    from social_poster import Runner

    cfg = job.to_runner_config()
    log_q: queue.Queue = queue.Queue()
    stop_evt = threading.Event()
    runner = Runner(cfg, log_q, stop_evt)

    def _pump_logs():
        while True:
            level, message = log_q.get()
            _log(f"LOG:{level.upper()} {message}")
            if level == "finished":
                break

    threading.Thread(target=_pump_logs, daemon=True).start()
    _log(
        f"INFO:LAUNCH_JOB platform={job.platform} time='{job.schedule_time}' title='{_preview(job.title)}'"
    )
    runner.start()
    runner.join()


def run_jobs(jobs: List[ScheduleJob]) -> None:
    for job in jobs:
        _run_single_job(job)


def _group_worker(group_id: str, jobs: List[ScheduleJob], show_console: bool) -> None:
    if show_console:
        try:
            ensure_own_console(f"Medium-{group_id}", verbose=False)
        except Exception:
            pass
    run_jobs(jobs)


def main(
    table: Path | None = None,
    limit: int | None = None,
    show_console: bool | None = None,
) -> None:
    table = (table or CSV_PATH).expanduser()
    limit = max(1, limit or DEFAULT_LIMIT)
    show_console = DEFAULT_SHOW_CONSOLE if show_console is None else show_console
    columns = read_schedule(table)
    jobs = build_jobs(columns)
    if not jobs:
        _log("WARN: No jobs found in schedule.")
        return
    groups: Dict[str, List[ScheduleJob]] = defaultdict(list)
    for job in jobs:
        key = (job.email or job.profile_path or "default").strip().lower() or "default"
        groups[key].append(job)

    processes: List[Process] = []
    for group_id, group_jobs in groups.items():
        while True:
            alive = [p for p in processes if p.is_alive()]
            if len(alive) < limit:
                processes = alive
                break
            _log(f"INFO:GROUP_MANAGER waiting for process slot alive={len(alive)}/{limit}")
            time.sleep(0.5)
            processes = alive
        proc = Process(target=_group_worker, args=(group_id, group_jobs, show_console))
        proc.start()
        _log(f"INFO:GROUP_PROCESS start group={group_id} pid={proc.pid} jobs={len(group_jobs)}")
        processes.append(proc)

    for proc in processes:
        proc.join()
        _log(f"INFO:GROUP_PROCESS finished pid={proc.pid}")


if __name__ == "__main__":
    main()
