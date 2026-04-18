#!/usr/bin/env python3
"""AI priority scorer — generates scoring prompts for the agent's LLM to evaluate.

Usage:
    python priority_scorer.py --task "Add unit tests for auth.py" --type improve
    python priority_scorer.py --task "Fix login crash" --type bug --evaluate "<LLM response>"

This script does NOT call the LLM directly. The agent uses its own LLM to evaluate
the generated prompt. This script generates the prompt and parses the LLM response.
A rule-based fallback is provided for when LLM evaluation is not available.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent

PROMPT_TEMPLATE = """\
Evaluate the priority score (0-100) for the following task.

Task type: {task_type}
Task description: {task_description}

Scoring rules:
- User request = 100 (forced to front of queue)
- Bug breaking core functionality: 90-100
- Bug in non-core feature: 70-89
- Important feature enhancement: 65-79
- General feature: 50-64
- Internal improvement (tests, docs): 30-49

Output JSON only: {{"score": <number>, "reason": "<one sentence reason>"}}
"""


def generate_prompt(task_type: str, task_description: str) -> str:
    """Generate the LLM scoring prompt."""
    if task_type == "user_request":
        return json.dumps({"score": 100, "reason": "User request, forced to the top of the queue"}, ensure_ascii=False)
    return PROMPT_TEMPLATE.format(task_type=task_type, task_description=task_description)


def parse_llm_response(raw: str) -> dict:
    """Parse JSON from LLM response text."""
    json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return {"score": 50, "reason": "Default score (failed to parse evaluation)"}


def score_task_rule_based(task_type: str, task_description: str) -> dict:
    """Rule-based fallback scoring when LLM is unavailable."""
    if task_type == "user_request":
        return {"score": 100, "reason": "user request, forced to front"}
    if task_type == "bug":
        critical_keywords = ["crash", "fatal", "break", "cannot", "fail", "critical"]
        if any(k in task_description.lower() for k in critical_keywords):
            return {"score": 88, "reason": "likely core functionality bug"}
        return {"score": 72, "reason": "general bug"}
    if task_type == "feature":
        return {"score": 65, "reason": "feature request"}
    if task_type == "improve":
        return {"score": 50, "reason": "improvement suggestion"}
    return {"score": 50, "reason": "default"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI priority scorer — generate LLM scoring prompt"
    )
    parser.add_argument("--task", required=True, help="Task description")
    parser.add_argument(
        "--type",
        required=True,
        choices=["bug", "feature", "improve", "user_request"],
    )
    parser.add_argument(
        "--evaluate",
        help="Raw output from agent LLM; score will be parsed automatically",
    )
    args = parser.parse_args()

    if args.evaluate:
        result = parse_llm_response(args.evaluate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        prompt = generate_prompt(args.type, args.task)
        fallback = score_task_rule_based(args.type, args.task)
        print("# LLM scoring prompt (evaluate with agent's own LLM):")
        print(prompt)
        print()
        print("# Rule-based fallback (used when LLM unavailable):")
        print(json.dumps(fallback, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
