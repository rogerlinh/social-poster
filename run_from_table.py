# run_from_table.py
# -*- coding: utf-8 -*-
"""Batch scheduler for Medium automation."""

from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
import time
from dataclasses import dataclass
from multiprocessing import Process
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config import Config

try:  # optional Excel dependency
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None

CFG = Config()
DEFAULT_TABLE = Path("schedule_template.csv")
DEFAULT_CONCURRENCY = 2


def is_xlsx(path: Path) -> bool:
    lower = path.name.lower()
    if lower.endswith((".xlsx", ".xls")):
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"PK"
    except Exception:
        return False


def read_csv_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8", "cp1258", "cp1252", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("latin1", errors="replace")


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def normalize_header(header: str) -> str:
    key = clean(header).lower().replace(" ", "").replace("_", "")
    aliases = {
        "platform": "platform",
        "email": "email",
        "type": "type",
        "title": "title",
        "content": "content",
        "images": "images",
        "schedule": "schedule_time",
        "scheduletime": "schedule_time",
    }
    return aliases.get(key, key)


def map_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    fields = ["platform", "email", "type", "title", "content", "images", "schedule_time"]
    data = {field: "" for field in fields}
    for key, value in raw.items():
        norm = normalize_header(key)
        if norm in data:
            data[norm] = clean(value)
    return data


def load_jobs(table_path: Path) -> List[Dict[str, Any]]:
    path = table_path.expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    if is_xlsx(path):
        if pd is None:
            raise RuntimeError("pandas is required to read Excel files")
        df = pd.read_excel(path)  # type: ignore[arg-type]
        rows = df.fillna(" ").to_dict(orient="records")
    else:
        text = read_csv_text(path)
        rows = list(csv.DictReader(io.StringIO(text)))
    jobs = [map_row(row) for row in rows if any(clean(v) for v in row.values())]
    return jobs


@dataclass
class MediumJob:
    platform: str
    email: str
    type: str
    title: str
    content: str
    images: str
    schedule_time: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediumJob":
        return cls(
            platform=data.get("platform", "") or "Medium",
            email=data.get("email", ""),
            type=data.get("type", "") or "medium",
            title=data.get("title", "") or "Untitled",
            content=data.get("content", ""),
            images=data.get("images", ""),
            schedule_time=data.get("schedule_time", ""),
        )

    def to_args(self, script: Path) -> List[str]:
        cmd = [sys.executable, str(script), "--platform", self.platform]
        if self.email:
            cmd.extend(["--email", self.email])
        cmd.extend(["--title", self.title, "--content", self.content])
        if self.images:
            cmd.extend(["--images", self.images])
        if self.schedule_time:
            cmd.extend(["--schedule-time", self.schedule_time])
        return cmd


def launch_job(job: MediumJob, script: Path, show_console: bool = True) -> Process:
    cmd = job.to_args(script)
    kwargs = {}
    if os.name == "nt" and show_console:
        kwargs["creationflags"] = 0x00000010  # CREATE_NEW_CONSOLE
    proc = Process(target=subprocess.call, args=(cmd,), kwargs=kwargs)
    proc.start()
    return proc


def run_jobs(jobs: List[MediumJob], script: Path, concurrency: int = DEFAULT_CONCURRENCY) -> None:
    processes: List[Process] = []
    for job in jobs:
        while len([p for p in processes if p.is_alive()]) >= concurrency:
            time.sleep(1.0)
        proc = launch_job(job, script)
        processes.append(proc)
    for proc in processes:
        proc.join()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Medium jobs from schedule table")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="Path to CSV/XLSX table")
    parser.add_argument("--script", type=Path, default=Path("publish_medium.py"), help="Worker script")
    parser.add_argument("--limit", type=int, default=DEFAULT_CONCURRENCY, help="Concurrent jobs")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    jobs = [MediumJob.from_dict(row) for row in load_jobs(args.table)]
    if not jobs:
        print("No jobs found in schedule table")
        return
    run_jobs(jobs, args.script, concurrency=max(1, args.limit))


if __name__ == "__main__":
    main()
