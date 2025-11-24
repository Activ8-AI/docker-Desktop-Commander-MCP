#!/usr/bin/env python3
"""Codex Executor — produces normalized advisory outputs for persona stacks."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML document at {path} must be an object")
    return data


class CodexExecutor:
    """Materializes persona guidance while enforcing CFMS invariants."""

    def __init__(
        self,
        policies_path: Path = Path("config/policies.yaml"),
        environment_path: Path = Path("config/environment.yaml"),
        evaluation_schema_path: Path = Path("codex_evaluation.json"),
    ) -> None:
        self.policies = _load_yaml(policies_path).get("policies", {})
        self.environment = _load_yaml(environment_path).get("environment", {})
        self.evaluation_schema = self._load_evaluation_schema(evaluation_schema_path)

    def execute(self, stack: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        persona = stack.get("routing", {}).get("persona", "unknown")
        role = stack.get("routing", {}).get("role", "unknown")
        normalized_payload = self._normalize_payload(payload)

        outputs = self._build_outputs(stack, normalized_payload)
        evaluation = self._evaluate(outputs)

        return {
            "timestamp": timestamp,
            "stack_id": stack.get("meta", {}).get("id"),
            "persona": persona,
            "role": role,
            "inputs": normalized_payload,
            "outputs": outputs,
            "evaluation": evaluation,
            "policy_bundle": list(self.policies.keys()),
            "environment": self.environment,
            "invariants_snapshot": stack.get("_includes", {}),
        }

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"payload": payload}
        return payload

    def _build_outputs(self, stack: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        agents = stack.get("agents", [])
        outputs: Dict[str, Any] = {}
        for agent in agents:
            name = agent.get("name", "agent")
            outputs[name] = {
                "format": agent.get("outputs", [{}])[0].get("format", "json"),
                "normalize": agent.get("outputs", [{}])[0].get("normalize", True),
                "content": {
                    "persona_summary": self._summarize_persona(stack, payload),
                    "advice": self._craft_advice(stack, payload),
                    "next_steps": self._craft_next_steps(payload),
                    "policy_refs": self._policy_refs_for_agent(name),
                },
            }
        return outputs

    def _summarize_persona(self, stack: Dict[str, Any], payload: Dict[str, Any]) -> str:
        persona = stack.get("routing", {}).get("persona", "persona")
        purpose = stack.get("meta", {}).get("purpose", "advisory")
        if payload:
            key_points = ", ".join(
                f"{k}={str(v)[:60]}" for k, v in list(payload.items())[:3]
            )
            return f"{persona} operating in {purpose}; latest payload: {key_points}."
        return f"{persona} operating in {purpose}; awaiting explicit payload."

    def _craft_advice(self, stack: Dict[str, Any], payload: Dict[str, Any]) -> str:
        persona = stack.get("routing", {}).get("persona", "persona")
        role = stack.get("routing", {}).get("role", "advisor")
        if not payload:
            return (
                f"{persona} ({role}) recommends collecting concrete context before acting. "
                "Start with the highest-signal question and log assumptions per CFMS invariants."
            )
        intent = payload.get("intent") or payload.get("goal")
        if intent:
            return (
                f"{persona} ({role}) confirms the goal '{intent}' and suggests a "
                "three-step advisory loop: clarify constraints, map actions to policy, "
                "and capture outcomes for the weekly digest."
            )
        return (
            f"{persona} ({role}) has parsed the payload and proposes iterating via relay → "
            "executor → logger to keep the stack composable and fungible."
        )

    def _craft_next_steps(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        base_steps = [
            {
                "action": "Validate charter alignment",
                "owner": "advisor_agent",
                "due": "P0",
            },
            {
                "action": "Record environment snapshot",
                "owner": "logger",
                "due": "P1",
            },
            {
                "action": "Publish digest entry",
                "owner": "digest",
                "due": "P2",
            },
        ]
        if payload.get("next_action"):
            base_steps.insert(
                0,
                {
                    "action": payload["next_action"],
                    "owner": payload.get("owner", "persona"),
                    "due": payload.get("due", "P0"),
                },
            )
        return base_steps

    def _policy_refs_for_agent(self, agent_name: str) -> List[str]:
        refs = []
        for key, value in self.policies.items():
            summary = value.get("summary") or key
            refs.append(f"{key}:{summary}")
        if not refs:
            refs.append(f"no-policies-configured-for:{agent_name}")
        return refs

    def _evaluate(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        criteria_scores = {}
        for criterion in self.evaluation_schema.get("criteria", []):
            key = criterion["key"]
            weight = float(criterion.get("weight", 0))
            criteria_scores[key] = {
                "score": self._score_criterion(key, outputs),
                "weight": weight,
            }
        weighted_total = sum(
            entry["score"] * entry["weight"] for entry in criteria_scores.values()
        )
        return {"criteria": criteria_scores, "weighted_total": weighted_total}

    def _score_criterion(self, key: str, outputs: Dict[str, Any]) -> float:
        content_blob = json.dumps(outputs)
        if key == "charter_alignment":
            return 0.9 if "policy" in content_blob else 0.75
        if key == "clarity":
            return 0.85 if "persona_summary" in content_blob else 0.7
        if key == "actionability":
            return 0.88 if "next_steps" in content_blob else 0.6
        if key == "compliance":
            return 0.92 if "normalize" in content_blob else 0.65
        return 0.5

    def _load_evaluation_schema(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {"criteria": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a Codex stack standalone")
    parser.add_argument("stack", type=Path, help="Path to the stack YAML file")
    parser.add_argument(
        "--payload",
        default="{}",
        help="JSON payload to feed the executor",
    )
    parser.add_argument(
        "--policies",
        type=Path,
        default=Path("config/policies.yaml"),
        help="Policies YAML path",
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=Path("config/environment.yaml"),
        help="Environment YAML path",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    stack = _load_yaml(args.stack)
    executor = CodexExecutor(args.policies, args.environment)
    payload = json.loads(args.payload)
    result = executor.execute(stack, payload)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
