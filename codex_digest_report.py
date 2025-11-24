#!/usr/bin/env python3
"""Codex Digest — aggregates Preservation Vault runs into a weekly report."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_timestamp(path: Path) -> Optional[str]:
    try:
        date_part = path.parent.name
        time_part = path.name
        dt.datetime.strptime(f"{date_part}T{time_part}", "%Y-%m-%dT%H%M%S")
        return f"{date_part}T{time_part}Z"
    except ValueError:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _discover_runs(vault: Path, window_days: int) -> List[Dict[str, Any]]:
    runs_root = vault / "runs"
    if not runs_root.exists():
        return []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=window_days)
    runs: List[Dict[str, Any]] = []
    for date_dir in sorted(runs_root.iterdir()):
        if not date_dir.is_dir():
            continue
        for run_dir in sorted(date_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            stamp = _parse_timestamp(run_dir)
            if stamp is None:
                continue
            stamp_dt = dt.datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ")
            if stamp_dt < cutoff:
                continue
            relay = _load_json(run_dir / "relay.json")
            if not relay:
                continue
            runs.append({
                "timestamp": stamp,
                "run_dir": str(run_dir),
                "relay": relay,
                "evaluation": _load_json(run_dir / "evaluation.json"),
            })
    return runs


def _aggregate_scores(runs: List[Dict[str, Any]]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for run in runs:
        criteria = run["relay"].get("result", {}).get("evaluation", {}).get("criteria", {})
        for key, entry in criteria.items():
            score = float(entry.get("score") if isinstance(entry, dict) else entry)
            totals[key] = totals.get(key, 0.0) + score
            counts[key] = counts.get(key, 0) + 1
    averages = {
        key: round(totals[key] / counts[key], 3) for key in totals if counts[key]
    }
    return averages


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Codex weekly digest")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("PreservationVault"),
        help="Path to the Preservation Vault",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("PreservationVault/digest.json"),
        help="Where to write the digest",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="How many days to include",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs = _discover_runs(args.vault, args.window_days)
    persona_roles = [
        {
            "persona": run["relay"].get("persona"),
            "role": run["relay"].get("role"),
        }
        for run in runs
    ]
    digest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_days": args.window_days,
        "runs_considered": len(runs),
        "persona_roles": persona_roles,
        "average_scores": _aggregate_scores(runs),
        "recent_runs": [
            {
                "timestamp": run["timestamp"],
                "stack_id": run["relay"].get("result", {}).get("stack_id"),
                "weighted_total": run["relay"].get("result", {})
                .get("evaluation", {})
                .get("weighted_total"),
            }
            for run in runs
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(digest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
