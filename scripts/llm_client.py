"""LLM client for AI-powered PM plan generation via MiniMax."""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from pathlib import Path

API_BASE = "https://api.minimaxi.com"
MODEL = "MiniMax-M2.7"

class MiniMaxError(Exception):
    """Raised on API key missing, network error, or non-200 response."""

class JSONParseError(MiniMaxError, RuntimeError):
    """Raised when LLM output is not valid JSON."""

@dataclass
class PMPlan:
    title: str
    task_type: str = "improve"
    source: str = "pm"
    effort: str = "medium"
    background: str = ""
    goal: str = ""
    context: str = ""
    scope: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    execution_plan: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    why_now: str = ""
    risks: str = ""
    rollback: str = ""
    maintenance_tag: str = ""

def _get_api_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("MINIMAX_API_KEY environment variable is not set.")
    return key

def _parse_json_response(raw: str) -> PMPlan:
    """Parse LLM JSON output into PMPlan. Strips markdown fences and LLM reasoning if present."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    # MiniMax with reasoning may prefix output with <notes>...</notes>
    # Extract the first { ... } JSON block
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        stripped = stripped[first_brace:last_brace + 1]
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise JSONParseError(f"LLM output is not valid JSON: {e}\n--- raw:\n{raw[:500]}")
    return PMPlan(
        title=data.get("title", "Untitled"),
        task_type=data.get("task_type", "improve"),
        source=data.get("source", "pm"),
        effort=data.get("effort", "medium"),
        background=data.get("background", ""),
        goal=data.get("goal", ""),
        context=data.get("context", ""),
        scope=data.get("scope", []),
        non_goals=data.get("non_goals", []),
        relevant_files=data.get("relevant_files", []),
        execution_plan=data.get("execution_plan", []),
        acceptance_criteria=data.get("acceptance_criteria", []),
        why_now=data.get("why_now", ""),
        risks=data.get("risks", ""),
        rollback=data.get("rollback", ""),
        maintenance_tag=data.get("maintenance_tag", ""),
    )

def generate_pm_plan(project: Path, language: str = "zh") -> PMPlan:
    """Two-step LLM workflow: context analysis → plan generation."""
    from scripts.llm_prompts import build_plan_prompt
    api_key = _get_api_key()
    user_prompt = build_plan_prompt(project, language)
    response = _call_minimax(api_key, user_prompt, language)
    return _parse_json_response(response)

def _call_minimax(api_key: str, user_prompt: str, language: str) -> str:
    import urllib.request, urllib.error
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise MiniMaxError(f"MiniMax API HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise MiniMaxError(f"Network error: {e.reason}")
    choices = data.get("choices", [])
    if not choices:
        raise MiniMaxError(f"Empty response from MiniMax API: {data}")
    return choices[0].get("text") or choices[0].get("message", {}).get("content", "")
