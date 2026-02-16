#!/usr/bin/env python3
"""Codex Logger — captures run metadata for the Preservation Vault."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict


def _safe_git(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *command],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _capture_environment() -> Dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
        "user": os.environ.get("USER"),
        "git_head": _safe_git(["rev-parse", "HEAD"]),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log Codex run metadata")
    parser.add_argument("--run-dir", type=Path, required=True, help="Run directory")
    parser.add_argument(
        "--record-env",
        action="store_true",
        help="Record execution environment details",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_dir = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)

    log_record = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "files_present": sorted(p.name for p in run_dir.glob("*")),
    }
    if args.record_env:
        log_record["environment"] = _capture_environment()

    log_path = run_dir / "logger.json"
    log_path.write_text(json.dumps(log_record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
