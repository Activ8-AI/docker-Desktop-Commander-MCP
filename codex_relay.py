#!/usr/bin/env python3
"""Codex Relay — routes personas to the executor and persists outputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from codex_executor import CodexExecutor


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing YAML file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML document at {path} must be an object")
    data["__file__"] = str(path)
    return data


def _attach_includes(stack: Dict[str, Any], stacks_dir: Path) -> None:
    includes: Dict[str, Any] = {}
    for include_name in stack.get("include", []):
        include_path = include_name
        include_path = stacks_dir / include_name
        includes[include_name] = _load_yaml(include_path)
    if includes:
        stack["_includes"] = includes


def _load_stack_candidates(stacks_dir: Path) -> Iterable[Dict[str, Any]]:
    for path in sorted(stacks_dir.glob("*.y*ml")):
        stack = _load_yaml(path)
        _attach_includes(stack, stacks_dir)
        yield stack


def _select_stack(
    *,
    persona: str,
    role: str,
    stacks_dir: Path,
    stack_file: Path | None,
) -> Dict[str, Any]:
    if stack_file:
        stack = _load_yaml(stack_file)
        _attach_includes(stack, stacks_dir)
        _validate_routing(stack, persona, role)
        return stack

    for stack in _load_stack_candidates(stacks_dir):
        routing = stack.get("routing", {})
        if routing.get("persona") == persona and routing.get("role") == role:
            return stack
    raise SystemExit(f"No stack matches persona={persona} role={role}")


def _validate_routing(stack: Dict[str, Any], persona: str, role: str) -> None:
    routing = stack.get("routing", {})
    if routing.get("persona") != persona or routing.get("role") != role:
        raise SystemExit(
            "Stack routing mismatch: "
            f"expected persona={persona}, role={role}, got {routing}"
        )


def _enforce_cfms(stack: Dict[str, Any]) -> Dict[str, Any]:
    includes = stack.get("_includes", {})
    cfms_doc = includes.get("_cfms_invariants.yaml", {})
    invariants = cfms_doc.get("cfms_invariants", {})
    if not invariants:
        return {"status": "missing"}
    pipeline = invariants.get("stackable", {}).get("enforcement", [])
    required_phrase = "pipeline: relay → executor → logger → evaluation → digest".lower()
    pipeline_join = " ".join(pipeline).lower()
    status = "ok" if required_phrase in pipeline_join else "warn"
    return {"status": status, "invariants": invariants}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relay payloads to the Codex executor")
    parser.add_argument("--persona", required=True, help="Persona id to route")
    parser.add_argument("--role", required=True, help="Role requested")
    parser.add_argument(
        "--payload",
        default="{}",
        help="JSON payload provided to the persona",
    )
    parser.add_argument(
        "--stacks-dir",
        type=Path,
        default=Path("stacks"),
        help="Directory that stores stack YAML files",
    )
    parser.add_argument(
        "--stack-file",
        type=Path,
        help="Optional explicit stack file path",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Directory for this run's artifacts",
    )
    parser.add_argument(
        "--policies",
        type=Path,
        default=Path("config/policies.yaml"),
        help="Policies yaml path",
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=Path("config/environment.yaml"),
        help="Environment yaml path",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid payload JSON: {exc}")

    run_dir = args.run_dir
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    stack = _select_stack(
        persona=args.persona,
        role=args.role,
        stacks_dir=args.stacks_dir,
        stack_file=args.stack_file,
    )
    cfms_status = _enforce_cfms(stack)

    executor = CodexExecutor(args.policies, args.environment)
    result = executor.execute(stack, payload)

    for agent_name, agent_output in result.get("outputs", {}).items():
        agent_path = outputs_dir / f"{agent_name}.json"
        agent_path.write_text(json.dumps(agent_output, indent=2), encoding="utf-8")

    relay_doc = {
        "run_dir": str(run_dir),
        "stack_file": stack.get("__file__"),
        "persona": args.persona,
        "role": args.role,
        "payload": payload,
        "result": result,
        "cfms": cfms_status,
    }
    json.dump(relay_doc, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
