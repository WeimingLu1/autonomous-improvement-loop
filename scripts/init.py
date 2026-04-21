#!/usr/bin/env python3
r"""
Autonomous Improvement Loop — setup wizard & cron hosting CLI

Supports these flows:
  a-adopt   Take over an existing project (auto-detect, configure, start)
  a-onboard Bootstrap a brand-new project
  a-status  Check project readiness and queue state

  a-start   Start cron hosting (create cron job from config.md)
  a-stop    Stop cron hosting (remove cron job)
  a-add     Create a user-sourced TASK + full plan doc
  a-current Show current task + full plan doc
  a-plan    Generate current task + full plan (PM mode)
  a-log     Show recent roadmap Done Log entries
  a-refresh [deprecated: use a-plan]
  a-trigger Execute current roadmap task
  a-config  Get or set config values

Examples:
  # Take over an existing project (most common)
  python init.py a-adopt ~/Projects/YOUR_PROJECT

  # Bootstrap a new project
  python init.py a-onboard ~/Projects/MyProject

  # Check project readiness
  python init.py a-status ~/Projects/YOUR_PROJECT

  # Start cron hosting
  python init.py a-start

  # Stop cron hosting
  python init.py a-stop

  # Add a user request as a full task plan
  python init.py a-add "Implement dark mode support"

  # Show current task
  python init.py a-current

  # Show recent roadmap log
  python init.py a-log -n 10

  # Generate next PM task
  python init.py a-plan

  # Execute current roadmap task
  python init.py a-trigger

  # Read a config value
  python init.py a-config get project_language

  # Set a config value
  python init.py a-config set project_language zh

All parameters are optional. init.py auto-detects project path, GitHub repo,
Agent ID, and Telegram Chat ID whenever possible, and only prompts when needed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Constants ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent.resolve()
SKILL_DIR = HERE.parent

# Persistent config location — survives clawhub update.
# This is SKILL-level config (agent_id, chat_id, cron settings).
# Project-level config lives in .ail/config.md inside the托管项目.
CONFIG_FILE = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop" / "config.md"

# ── AIL State Path Helpers ────────────────────────────────────────────────────
# All skill-generated state files live in .ail/ inside the托管项目 (project_path).
# This keeps the project directory clean and follows PM logic:
# everything about a project lives inside the project.


def ail_state_dir(project: Path) -> Path:
    """Return the .ail/ state directory for a project."""
    return project / ".ail"


def ail_heartbeat(project: Path) -> Path:
    """Path to HEARTBEAT.md for a project."""
    return project / ".ail" / "HEARTBEAT.md"


def ail_project_md(project: Path) -> Path:
    """Path to PROJECT.md for a project."""
    return project / ".ail" / "PROJECT.md"


def ail_roadmap(project: Path) -> Path:
    """Path to ROADMAP.md for a project."""
    return project / ".ail" / "ROADMAP.md"


def ail_plans_dir(project: Path) -> Path:
    """Path to plans/ directory for a project."""
    return project / ".ail" / "plans"


def ail_config(project: Path) -> Path:
    """Path to project-level config.md for a project."""
    return project / ".ail" / "config.md"

# ── Config path helpers ────────────────────────────────────────────────────────

def _config_template() -> Path:
    """Path to the skill's template config (shipped with the package)."""
    return SKILL_DIR / "config.md"


def read_current_config() -> dict[str, str]:
    """Read existing config values. Falls back to template if persistent config missing."""
    conf_file = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if not conf_file.exists():
        return {}
    text = read_file(conf_file)
    result = {}
    for line in text.splitlines():
        m = re.match(r"^(\w[\w_]*):\s*(.+)$", line.strip())
        if m:
            value = re.sub(r"\s+#.*$", "", m.group(2)).strip()
            result[m.group(1)] = value
    return result

DEFAULT_SCHEDULE_MS = 30 * 60 * 1000   # 30 min
DEFAULT_TIMEOUT_S = 3600                # 1 hour
DEFAULT_LANGUAGE = "en"

COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_BLUE = "\033[34m"
COLOR_BOLD = "\033[1m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{COLOR_RESET}"


def ok(msg: str) -> None:
    print(f"  {c('✓', COLOR_GREEN)} {msg}")


def warn(msg: str) -> None:
    print(f"  {c('⚠', COLOR_YELLOW)} {msg}")


def info(msg: str) -> None:
    print(f"  {c('ℹ', COLOR_BLUE)} {msg}")


def fail(msg: str) -> None:
    print(f"  {c('✗', COLOR_RED)} {msg}")


def step(msg: str) -> None:
    print(f"\n{c(msg, COLOR_BOLD)}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def ask(prompt: str, default: str | None = None) -> str:
    """TTY-friendly prompt with safe default for non-interactive runs."""
    if not sys.stdin.isatty():
        return default or ""
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def read_file(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_file(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ── Auto-detection ─────────────────────────────────────────────────────────────

def detect_project_path() -> Path | None:
    """Detect from current dir git or common project locations."""
    # Try git remote first
    r = run(["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd())
    if r.returncode == 0:
        return Path(r.stdout.strip())
    # Try git remote in a few common locations
    candidates = [
        Path.home() / "Projects",
        Path.home() / "projects",
        Path.home() / "Code",
        Path.cwd(),
    ]
    for base in candidates:
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            if p.is_dir() and (p / ".git").exists():
                return p
    return None


def detect_github_repo(project: Path) -> str | None:
    """Read git remote to get GitHub repo URL."""
    r = run(["git", "remote", "get-url", "origin"], cwd=project)
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    # git@github.com:owner/repo.git → https://github.com/owner/repo
    m = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if m:
        return f"https://github.com/{m.group(1)}"
    m = re.match(r"https?://github\.com/(.+?)(?:\.git)?$", url)
    if m:
        return f"https://github.com/{m.group(1)}"
    return None


def detect_project_language(project: Path) -> str:
    """Detect from README.md content or file extensions."""
    readme_candidates = ["README.md", "README.zh.md", "README-CN.md",
                         "README.en.md", "README.rst", "README"]
    for rn in readme_candidates:
        p = project / rn
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore")[:500]
            if re.search(r"[\u4e00-\u9fff]", content):
                return "zh"
            if re.search(r"\bthe\b.*\bto\b.*\bfor\b", content, re.I):
                return "en"
    # Fallback: count source file extensions
    exts: dict[str, int] = {}
    for p in project.rglob("*"):
        if not p.is_file() or any(x in p.parts for x in
                                   ["__pycache__", "node_modules", ".venv", "venv", ".git"]):
            continue
        ext = p.suffix.lower()
        if ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".c", ".cpp"):
            exts[ext] = exts.get(ext, 0) + 1
    if exts:
        return DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def detect_agent_language() -> str:
    """Best-effort detection of the current agent's preferred language."""
    candidates = []

    for parent in HERE.parents:
        user_md = parent / "USER.md"
        if user_md.exists():
            candidates.append(user_md)
            break

    workspace = Path.home() / ".openclaw"
    user_md = workspace / "USER.md"
    if user_md.exists():
        candidates.append(user_md)

    config_path = workspace / "openclaw.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8", errors="ignore"))
            for key in ("language", "locale", "uiLanguage"):
                value = str(data.get(key, "")).lower()
                if value.startswith("zh"):
                    return "zh"
                if value.startswith("en"):
                    return "en"
        except Exception:
            pass

    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        if "language" in lowered:
            if re.search(r"language\s*[:：].*(\u4e2d\u6587|chinese|mandarin|zh)", text, re.I):
                return "zh"
            if re.search(r"language\s*[:：].*(english|en)", text, re.I):
                return "en"

    return DEFAULT_LANGUAGE


def resolve_language(project: Path | None = None, explicit: str | None = None) -> str:
    """Resolve project/output language.

    Priority:
      1. Explicit --language
      2. Existing config.md project_language
      3. Agent language preference
      4. Project content detection
      5. DEFAULT_LANGUAGE
    """
    if explicit in {"en", "zh"}:
        return explicit

    current_config = read_current_config()
    current = current_config.get("project_language", "").strip().lower()
    configured_agent = current_config.get("agent_id", "").strip()
    configured_path = current_config.get("project_path", "").strip()
    is_template_config = configured_agent in {"", "YOUR_AGENT_ID"} or configured_path in {"", "."}
    if current in {"en", "zh"} and not is_template_config:
        return current

    agent_language = detect_agent_language()
    if agent_language in {"en", "zh"}:
        return agent_language

    if project and project.exists():
        return detect_project_language(project)

    return DEFAULT_LANGUAGE


def detect_version_file(project: Path) -> Path:
    return project / "VERSION"


def detect_cli_name(project: Path) -> str:
    """Infer CLI name from project name or pyproject.toml."""
    name = project.name
    # Try pyproject.toml
    pp = project / "pyproject.toml"
    if pp.exists():
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', pp.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1).replace("_", "-")
    # Try setup.py
    sp = project / "setup.py"
    if sp.exists():
        m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", sp.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1).replace("_", "-")
    # Default: lowercase project dir name
    return name.lower().replace("_", "-")


def detect_openclaw_agent_id() -> str | None:
    """Read agent id from openclaw config or workspace."""
    # Prefer current skill workspace path (e.g. .../.openclaw/workspace-YOUR_AGENT/...)
    for parent in HERE.parents:
        if parent.name.startswith("workspace-"):
            return parent.name.replace("workspace-", "")

    workspace = Path.home() / ".openclaw"
    # Fallback: existing config in this skill
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if conf.exists():
        m = re.search(r"^agent_id:\s*([^#\n]+)", read_file(conf), re.MULTILINE)
        if m:
            return m.group(1).strip()

    # Last-resort: any workspace dir name first found
    for d in sorted(workspace.iterdir()):
        if d.is_dir() and d.name.startswith("workspace-"):
            return d.name.replace("workspace-", "")
    # Try reading openclaw config (be fast, don't run CLI)
    config_path = workspace / "openclaw.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8", errors="ignore"))
            return data.get("agentId") or data.get("currentAgent")
        except Exception:
            pass
    return None


def detect_telegram_chat_id() -> str | None:
    """Read chat_id from existing config.md."""
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if conf.exists():
        m = re.search(r"chat_id:\s*(\d+)", read_file(conf))
        if m:
            return m.group(1)
    return None


def detect_existing_cron() -> str | None:
    """Check if a cron job for autonomous-improvement-loop already exists."""
    r = run(["openclaw", "cron", "list"], timeout=15)
    if r.returncode != 0:
        return None
    for line in r.stdout.strip().splitlines():
        if "autonomous" in line.lower() or "improvement" in line.lower():
            m = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", line)
            if m:
                return m.group(0)
    return None


def detect_pytest_available() -> bool:
    try:
        r = run(["python3", "-m", "pytest", "--version"], timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def detect_any_test_command(project: Path) -> tuple[bool, str]:
    """Detect whether a runnable verification/test command is available.

    Uses --co -q (collect-only) instead of running tests to avoid subprocess
    deadlock when pytest forks child processes from the project directory.
    """
    python_bin = shutil.which("python3") or "python3"
    runners = [
        ([python_bin, "-m", "pytest", "--co", "-q"], "pytest", None),
        (["npm", "test"], "npm test", "npm"),
        (["cargo", "test"], "cargo test", "cargo"),
        (["go", "test", "./..."], "go test ./...", "go"),
        (["make", "test"], "make test", "make"),
    ]
    for cmd, label, binary in runners:
        if binary and shutil.which(binary) is None:
            continue
        try:
            r = run(cmd, cwd=project, timeout=15)
        except FileNotFoundError:
            continue
        if r.returncode in (0, 1):
            return True, label
    return False, ""


def detect_build_config(project: Path) -> str:
    """Detect likely build/package config for software projects."""
    candidates = [
        "pyproject.toml", "setup.py", "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml", "build.gradle",
        "Gemfile",
        "CMakeLists.txt",
    ]
    for f in candidates:
        if (project / f).exists():
            return f
    return ""


def detect_gh_authenticated() -> bool:
    r = run(["gh", "auth", "status"], timeout=10)
    return r.returncode == 0


# ── Project readiness ─────────────────────────────────────────────────────────

def _read_kind_from_config() -> str:
    """Try to read project_kind from config.md."""
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if not conf.exists():
        return "generic"
    for line in conf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("project_kind:"):
            val = line.partition(":")[2].strip()
            return val if val else "generic"
    return "generic"


def check_project_readiness(project: Path) -> dict[str, bool]:
    kind = _read_kind_from_config()
    build_cfg = detect_build_config(project)
    test_ok, test_cmd = detect_any_test_command(project)
    readme_ok = any((project / f).exists() for f in
                     ["README.md", "README.rst", "README", "README.zh.md"])

    base = {
        "Git repository": (project / ".git").exists(),
        "README exists": readme_ok,
        "GitHub CLI authenticated": detect_gh_authenticated(),
    }

    if kind == "software":
        build_label = f"Build system ({build_cfg})" if build_cfg else "Build system"
        test_label = f"Verification command ({test_cmd})" if test_cmd else "Verification command"
        return {
            **base,
            "Source directory exists": any((project / d).exists() for d in ["src", "lib", "app", "packages"]),
            build_label: bool(build_cfg),
            test_label: test_ok if test_cmd else not (project / "tests").exists(),
        }
    if kind == "writing":
        return {
            **base,
            "Content directory exists": any((project / d).exists() for d in ["chapters", "manuscript", "drafts", "scenes"]),
            "Outline exists": any((project / f).exists() for f in ["outline.md", "outline.txt"]),
            "Characters/materials directory exists": any((project / d).exists() for d in ["characters", "notes", "materials"]),
        }
    if kind == "video":
        return {
            **base,
            "Script directory exists": any((project / d).exists() for d in ["scripts", "scenes"]),
            "Storyboard/assets directory exists": any((project / d).exists() for d in ["storyboard", "assets", "footage"]),
            "Outline exists": any((project / f).exists() for f in ["outline.md", "treatment.md"]),
        }
    if kind == "research":
        return {
            **base,
            "Research content directory exists": any((project / d).exists() for d in ["papers", "notes", "references"]),
            "Outline exists": any((project / f).exists() for f in ["outline.md", "proposal.md"]),
            "References/bibliography exists": any((project / d).exists() for d in ["references", "bib"]),
        }
    return {
        **base,
        "Content directory exists": any((project / d).exists() for d in ["docs", "materials", "notes", "content", "assets"]),
        "Structure file exists": any((project / f).exists() for f in ["outline.md", "index.md", "README.md"]),
    }


# ── Config file management ─────────────────────────────────────────────────────

def build_config(
    project_path: Path,
    repo: str,
    version_file: Path | None,
    docs_dir: Path | None,
    cli_name: str | None,
    agent_id: str,
    chat_id: str,
    language: str,
    cron_job_id: str | None,
    project_kind: str | None = None,
) -> str:
    kind_line = f"project_kind: {project_kind or 'generic'}   # software | writing | video | research | generic"
    return textwrap.dedent(f"""\
    # Autonomous Improvement Loop — Project Configuration

    > Fill in this file after installing the skill to bind it to your project.

    ## Project
    project_path: {project_path.expanduser().resolve()}
    {kind_line}

    ## GitHub Repository
    repo: {repo}

    ## OpenClaw Agent ID
    agent_id: {agent_id}

    ## Telegram Chat ID
    chat_id: {chat_id}

    ## Project Language
    project_language: {language}   # "en" = English, "zh" = Chinese (clear it later to follow agent preference)

    ## Verification & Publish
    verification_command:   # empty = no auto-verification
    publish_command:        # optional: shell command after successful task

    ## Cron
    cron_schedule: */30 * * * *
    cron_timeout: {DEFAULT_TIMEOUT_S}
    cron_job_id: {cron_job_id or ""}
    """).strip()


def write_config(
    project_path: Path,
    repo: str,
    version_file: Path | None,
    docs_dir: Path | None,
    cli_name: str | None,
    agent_id: str,
    chat_id: str,
    language: str,
    cron_job_id: str | None = None,
    project_kind: str | None = None,
) -> None:
    config = build_config(
        project_path, repo, version_file, docs_dir, cli_name,
        agent_id, chat_id, language, cron_job_id, project_kind,
    )
    write_file(CONFIG_FILE, config + "\n")


# ── Cron management ─────────────────────────────────────────────────────────────

def create_cron(
    agent_id: str,
    model: str,
    chat_id: str | None,
    schedule_ms: int = DEFAULT_SCHEDULE_MS,
) -> str:
    """Create a new cron job and return its ID."""
    cmd = [
        "openclaw", "cron", "add",
        "--name", "Autonomous Improvement Loop",
        "--every", f"{schedule_ms // 60000}m",
        "--session", "isolated",
        "--agent", agent_id,
        "--timeout-seconds", str(DEFAULT_TIMEOUT_S),
        "--message", "Autonomous improvement loop triggered",
    ]
    if model and model not in {"MODEL", "YOUR_MODEL"}:
        cmd.extend(["--model", model])
    if chat_id:
        cmd.extend(["--announce", "--channel", "telegram", "--to", chat_id])
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"Failed to create cron: {r.stderr}")
    # Extract cron ID from output
    try:
        data = json.loads(r.stdout)
        return data.get("id", "")
    except Exception:
        # Fallback: parse from stdout
        m = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", r.stdout)
        return m.group(0) if m else ""


def delete_cron(cron_id: str) -> None:
    run(["openclaw", "cron", "rm", cron_id])


def seed_queue(project: Path, mode: str, language: str) -> None:
    """Populate initial roadmap state after init so the user gets value immediately."""
    roadmap_path = ail_roadmap(project)
    from scripts.roadmap import init_roadmap
    if not roadmap_path.exists():
        # Ensure .ail/ directory exists
        ail_state_dir(project).mkdir(parents=True, exist_ok=True)
        init_roadmap(roadmap_path)
    # Generate the first PM task using the same project configured by adopt/onboard.
    cmd_plan(force=True)


# ── HEARTBEAT queue initialization ─────────────────────────────────────────────

def init_queue_heartbeat(project: Path, mode: str, language: str) -> None:
    """Initialize or update the Run Status + empty Queue section."""
    if not ail_heartbeat(project).exists():
        raise RuntimeError(f"HEARTBEAT.md not found at {ail_heartbeat(project)}")

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    run_status = f"""\
| Field | Value |
|-------|-------|
| last_run_time | — |
| last_run_commit | — |
| last_run_result | unknown |
| last_run_task | — |
| cron_lock | false |
| mode | {mode} |
| rollback_on_fail | true |
"""

    empty_queue = f"""\
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
"""

    content = read_file(ail_heartbeat(project))

    # Replace Run Status section
    content = re.sub(
        r"(## Run Status\n\n)\|[\s\S]*?(\n---\n)",
        f"\\1{run_status}\\2",
        content,
    )

    # Replace Queue section (keep it empty/minimal for new adopt)
    content = re.sub(
        r"(\n## Queue\n\n)[\s\S]*?(\n---\n)",
        f"\\1{empty_queue}\n---\n",
        content,
    )

    write_file(ail_heartbeat(project), content)


def pending_queue_rows(project: Path) -> list[dict[str, str]]:
    if not ail_heartbeat(project).exists():
        return []
    rows: list[dict[str, str]] = []
    for line in read_file(ail_heartbeat(project)).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        m = re.match(
            r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
            stripped,
        )
        if not m:
            continue
        num, kind, score, desc, source, status, created = m.groups()
        if status.strip().lower() == "pending":
            rows.append(
                {
                    "num": num,
                    "kind": kind.strip(),
                    "score": score.strip(),
                    "desc": desc.strip(),
                    "source": source.strip(),
                    "status": status.strip(),
                    "created": created.strip(),
                }
            )
    return rows


def write_pending_queue(project: Path, rows: list[dict[str, str]]) -> None:
    content = read_file(ail_heartbeat(project))
    table = [
        "| # | Type | Score | Content | Source | Status | Created |",
        "|---|------|-------|---------|--------|--------|---------|",
    ]
    for i, row in enumerate(rows, 1):
        table.append(
            f"| {i} | {row['kind']} | {row['score']} | {row['desc']} | {row['source']} | pending | {row['created']} |"
        )
    content = re.sub(
        r"(\n## Queue\n\n)[\s\S]*?(\n---\n)",
        "\\1" + "\n".join(table) + "\n\\2",
        content,
    )
    write_file(ail_heartbeat(project), content)


def update_run_status_mode(project: Path, mode: str) -> None:
    if not ail_heartbeat(project).exists():
        return
    content = read_file(ail_heartbeat(project))
    content = re.sub(r"(\| mode \| )([^|]+)( \|)", rf"\1{mode}\3", content)
    write_file(ail_heartbeat(project), content)


def dedupe_pending_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    removed = 0
    for row in rows:
        key = re.sub(r"\s+", " ", row["desc"]).strip().lower()
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, removed


# ── Adopt: existing project takeover ──────────────────────────────────────────

def cmd_adopt(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    model: str = "",
    force_new_cron: bool = False,
) -> None:
    step("🔍 Existing project takeover — setup wizard")

    # Detect / validate project
    if not project.exists():
        fail(f"Project path does not exist: {project}")
        sys.exit(1)

    repo = detect_github_repo(project)
    version_file = detect_version_file(project)
    docs_dir = project / "docs" / "agent"
    cli_name = detect_cli_name(project)
    try:
        from project_insights import detect_project_type
        from project_md import generate_project_md
        project_kind = detect_project_type(project)
    except Exception:
        project_kind = "generic"
    readiness = check_project_readiness(project)

    # Show project info
    print(f"\n  {c('Project:', COLOR_BOLD)} {project.name}")
    print(f"  {c('Path:', COLOR_BOLD)} {project}")
    print(f"  {c('GitHub:', COLOR_BOLD)} {repo or c('Not detected (configure manually later)', COLOR_YELLOW)}")
    print(f"  {c('CLI name:', COLOR_BOLD)} {cli_name}")
    print(f"  {c('Language:', COLOR_BOLD)} {'Chinese' if language == 'zh' else 'English'}")
    print(f"  {c('Project type:', COLOR_BOLD)} {project_kind}")
    print(f"  {c('Agent ID:', COLOR_BOLD)} {agent_id or c('Not detected', COLOR_RED)}")

    # Show readiness
    step("📋 Project readiness check")
    new_items = sum(1 for v in readiness.values() if not v)
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} {c('(missing)', COLOR_YELLOW)}")
    print()

    if new_items > 3:
        warn(f"Project has {new_items} missing readiness item(s). It is safer to fix them first, or take over now and let the loop stay in bootstrap mode.")
        print("  Continuing anyway... (the loop will wait in bootstrap mode)\n")

    # Existing cron?
    existing_cron = detect_existing_cron()
    if existing_cron and not force_new_cron:
        ok(f"Existing Cron Job: {existing_cron}")
        cron_job_id = existing_cron
        use_existing = ask(
            f"  {c('Cron handling (s=keep, r=delete and recreate)', COLOR_BOLD)}",
            "s",
        ).lower()
        if use_existing == "r":
            delete_cron(existing_cron)
            existing_cron = None
            print("  Deleted the old Cron. A new one will be created.")
        else:
            print("  Keeping the existing Cron.")
    else:
        existing_cron = None

    # Create cron if needed
    if not existing_cron:
        if not agent_id:
            fail("Cannot create Cron: Agent ID is not set. Configure the OpenClaw agent first.")
            sys.exit(1)
        if not chat_id:
            warn("Telegram Chat ID is not set. Cron will not send notifications. Continue? [y/N]")
            if ask("  >", "n").lower() != "y":
                sys.exit(0)

        step("⏰ Creating Cron Job")
        try:
            cron_job_id = create_cron(agent_id, model, chat_id)
            ok(f"Cron Job created: {cron_job_id}")
        except Exception as e:
            warn(f"Cron creation failed: {e}")
            warn("Cron was not created. Run it manually with: openclaw cron add ...")
            cron_job_id = None
    else:
        cron_job_id = existing_cron

    # Write config
    step("📝 Writing config.md")
    write_config(
        project_path=project,
        repo=repo or "https://github.com/OWNER/REPO",
        version_file=version_file,
        docs_dir=docs_dir,
        cli_name=cli_name,
        agent_id=agent_id or "YOUR_AGENT_ID",
        chat_id=chat_id or "YOUR_TELEGRAM_CHAT_ID",
        language=language,
        cron_job_id=cron_job_id,
        project_kind=project_kind,
    )
    ok("config.md updated")

    step("🧭 Generating PROJECT.md")
    try:
        from project_md import generate_project_md

        generate_project_md(project, ail_project_md(project), language=language, repo=repo)
        ok("PROJECT.md generated")
    except Exception as e:
        warn(f"PROJECT.md generation failed: {e}")

    # Queue handling for old managed projects
    mode = "bootstrap" if new_items > 3 else "normal"
    current_rows = pending_queue_rows(project)
    if current_rows:
        step("📦 Existing queue detected")
        deduped_rows, removed = dedupe_pending_rows(current_rows)
        default_action = "c" if removed else "k"
        action = ask("  Queue handling (k=keep, c=dedupe and keep, r=clear and rebuild)", default_action).lower()
        if action == "r":
            init_queue_heartbeat(project, mode=mode, language=language)
            ok(f"HEARTBEAT.md rebuilt (mode: {mode})")
        elif action == "c":
            write_pending_queue(project, deduped_rows)
            update_run_status_mode(project, mode)
            ok(f"Queue deduplicated, removed {removed} duplicate item(s)")
        else:
            update_run_status_mode(project, mode)
            ok("Kept existing queue, updated run mode only")
    else:
        step("📋 Initializing HEARTBEAT.md")
        init_queue_heartbeat(project, mode=mode, language=language)
        ok(f"HEARTBEAT.md initialized (mode: {mode})")

    roadmap_path = ail_roadmap(project)
    if not roadmap_path.exists():
        step("🧠 Generating initial roadmap task")
        seed_queue(project=project, mode=mode, language=language)
        ok("Initial roadmap task generated")
    else:
        ok("Existing roadmap state detected, skipped auto-generation")

    # Done
    print(textwrap.dedent(f"""

    {c('✅ Takeover complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Mode: {mode}
    Language: {'Chinese' if language == 'zh' else 'English'}
    Cron: {cron_job_id or 'not created'}

    {'The first run will stay in bootstrap mode until the project is ready' if mode == 'bootstrap' else 'Cron runs automatically every 30 minutes'}

    View queue:
      cat {ail_heartbeat(project)}

    Trigger Cron manually:
      openclaw cron run {cron_job_id}

    Delete Cron:
      openclaw cron delete {cron_job_id}
    """))


# ── Onboard: bootstrap a new project ──────────────────────────────────────────

_KNOWN_TYPES = {
    "software": "Software/CLI project (src/, tests/, build config)",
    "writing": "Writing project (chapters/, outline.md, characters/)",
    "video": "Video/media project (scripts/, scenes/, storyboard/)",
    "research": "Academic/research project (papers/, references/, notes/)",
    "generic": "Generic project (docs/, materials/, README)",
}


def _scaffold_project(project: Path, kind: str) -> None:
    """Create minimal directory structure based on project kind."""
    project.mkdir(parents=True, exist_ok=True)
    if kind == "software":
        (project / "src").mkdir(exist_ok=True)
        (project / "tests").mkdir(exist_ok=True)
        (project / "docs").mkdir(exist_ok=True)
        (project / "docs" / "agent").mkdir(exist_ok=True)
        (project / "src" / ".gitkeep").touch()
        (project / "tests" / ".gitkeep").touch()
    elif kind == "writing":
        (project / "chapters").mkdir(exist_ok=True)
        (project / "characters").mkdir(exist_ok=True)
        (project / "outline.md").write_text("# Outline\n\n", encoding="utf-8")
        (project / "characters" / "README.md").write_text("# Character Settings\n\n", encoding="utf-8")
        (project / "chapters" / ".gitkeep").touch()
    elif kind == "video":
        (project / "scripts").mkdir(exist_ok=True)
        (project / "scenes").mkdir(exist_ok=True)
        (project / "storyboard").mkdir(exist_ok=True)
        (project / "assets").mkdir(exist_ok=True)
        (project / "scripts" / "outline.md").write_text("# Script Outline\n\n", encoding="utf-8")
        (project / "scenes" / ".gitkeep").touch()
    elif kind == "research":
        (project / "papers").mkdir(exist_ok=True)
        (project / "references").mkdir(exist_ok=True)
        (project / "notes").mkdir(exist_ok=True)
        (project / "outline.md").write_text("# Research Outline\n\n", encoding="utf-8")
        (project / "references" / "README.md").write_text("# References\n\n", encoding="utf-8")
    else:
        (project / "docs").mkdir(exist_ok=True)
        (project / "materials").mkdir(exist_ok=True)
        (project / "docs" / "README.md").write_text("# Documentation\n\n", encoding="utf-8")


def cmd_onboard(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    model: str = "",
) -> None:
    step("🆕 Bootstrapping a new project")

    if project.exists() and any(project.iterdir()):
        warn(f"Directory {project} is not empty. Use adopt mode for an existing project.")
        print(f"  python init.py adopt {project}")
        sys.exit(1)

    # Step 1: pick project kind
    step("📂 Select project type")
    for key, desc in _KNOWN_TYPES.items():
        print(f"  {c(key, COLOR_GREEN):12} {desc}")
    print()
    kind = ask("Project type (software / writing / video / research / generic)", "generic").strip().lower()
    if kind not in _KNOWN_TYPES:
        warn(f"Unknown type '{kind}', using generic.")
        kind = "generic"

    # Step 2: confirm
    print(textwrap.dedent(f"""
    This wizard helps create an AI-ready new project structure.

    After completion it will:
    1. Create a base directory structure for {kind}
    2. Initialize a Git repository
    3. Configure the Autonomous Improvement Loop
    4. Prepare the project for Cron takeover

    Project directory: {project}
    Project type: {kind}
    Language: {'Chinese' if language == 'zh' else 'English'}
    """))

    if ask("\n  Continue?", "n").lower() != "y":
        print("Cancelled.")
        sys.exit(0)

    # Step 3: scaffold
    step("🏗  Creating project structure")
    _scaffold_project(project, kind)
    ok(f"Directory structure created ({kind})")

    # Step 4: git
    if not (project / ".git").exists():
        run(["git", "init"], cwd=project)
        ok("Git repository initialized")

    # Step 5: GitHub repo (optional)
    gh_remote = ask("\n  GitHub repo URL (optional, press Enter to skip)")
    if gh_remote:
        run(["git", "remote", "add", "origin", gh_remote], cwd=project)
        ok(f"Git remote set: {gh_remote}")

    # Step 6: write config
    step("📝 Writing config.md")
    write_config(
        project_path=project,
        repo=gh_remote or "https://github.com/OWNER/REPO",
        version_file=None,
        docs_dir=None,
        cli_name=None,
        agent_id=agent_id or "YOUR_AGENT_ID",
        chat_id=chat_id or "YOUR_TELEGRAM_CHAT_ID",
        language=language,
        cron_job_id=None,
        project_kind=kind,
    )
    ok("config.md written")

    step("🧭 Generating PROJECT.md")
    try:
        from project_md import generate_project_md

        generate_project_md(project, ail_project_md(project), language=language, repo=gh_remote or None)
        ok("PROJECT.md generated")
    except Exception as e:
        warn(f"PROJECT.md generation failed: {e}")

    # Step 7: init heartbeat — create .ail/ dir and seed HEARTBEAT.md first
    step("📋 Initializing HEARTBEAT.md")
    ail_state_dir(project).mkdir(parents=True, exist_ok=True)
    # Seed a blank/minimal HEARTBEAT.md so init_queue_heartbeat can update it
    blank_heartbeat = f"""\
## Run Status

| Field | Value |
|-------|-------|
| last_run_time | — |
| last_run_commit | — |
| last_run_result | unknown |
| last_run_task | — |
| cron_lock | false |
| mode | bootstrap |
| rollback_on_fail | true |

## Queue

| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|

---
"""
    hb_path = ail_heartbeat(project)
    hb_path.write_text(blank_heartbeat, encoding="utf-8")
    init_queue_heartbeat(project, mode="bootstrap", language=language)
    ok("HEARTBEAT.md initialized (mode: bootstrap)")

    step("📋 Generating PROJECT.md")
    try:
        generate_project_md(project=project, output=ail_project_md(project), language=language)
        ok("PROJECT.md generated")
    except Exception as e:
        warn(f"PROJECT.md generation failed: {e}")

    print(textwrap.dedent(f"""
    {c('✅ New project bootstrap complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Type: {kind}
    Directory: {project}

    Next step:
      python init.py adopt {project}  # take over the project and start Cron

    View queue:
      cat {ail_heartbeat(project)}
    """))


# ── Start: launch cron托管 ────────────────────────────────────────────────────

def cmd_start() -> None:
    step("⏰ Starting Autonomous Improvement Loop cron")

    config = read_current_config()
    cron_job_id = config.get("cron_job_id", "").strip()
    cron_schedule = config.get("cron_schedule", "*/30 * * * *").strip().strip('"').strip("'")
    cron_timeout = config.get("cron_timeout", str(DEFAULT_TIMEOUT_S)).strip()
    agent_id = config.get("agent_id", "").strip()
    chat_id = config.get("chat_id", "").strip()
    project_path = config.get("project_path", "").strip()
    project_language = config.get("project_language", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    project = Path(project_path).expanduser().resolve() if project_path else None

    # Clean up ANY existing "Autonomous Improvement Loop" cron jobs first.
    # This ensures a-start always results in exactly 1 cron — idempotent.
    r = run(["openclaw", "cron", "list"], timeout=15)
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if "Autonomous Improvement Loop" in line:
                # Extract ID: first field before whitespace
                existing_id = line.split()[0]
                run(["openclaw", "cron", "delete", existing_id], timeout=15)
                print(f"  Removed stale cron: {existing_id}")

    if not agent_id or agent_id in ("", "YOUR_AGENT_ID"):
        fail("agent_id not configured in config.md")
        sys.exit(1)

    _ail_roadmap = str(ail_roadmap(project)) if project else '<project>/.ail/ROADMAP.md'
    _ail_project_md = str(ail_project_md(project)) if project else '<project>/.ail/PROJECT.md'
    _ail_plans = f'{project}/.ail/plans/' if project else '<project>/.ail/plans/'
    cron_message = textwrap.dedent(
        f"""
        Autonomous Improvement Loop triggered for project: {project_path or '(unset)'}.

        Follow this workflow exactly:
        1. Read {CONFIG_FILE} and {_ail_roadmap}. If {_ail_project_md} exists, read it too.
        2. Open the current plan from `{_ail_plans}TASK-xxx.md`.
        3. Execute the current roadmap task.
        4. Record the result through `python3 {HERE / 'init.py'} a-trigger --force`.
        5. Send a concise final summary (commit, result, next task if any).

        IMPORTANT: ROADMAP.md is the source of truth. Do not rely on the old HEARTBEAT queue flow.
        """
    ).strip()

    # Build openclaw cron add command
    cmd = [
        "openclaw", "cron", "add",
        "--name", "Autonomous Improvement Loop",
        "--cron", cron_schedule,
        "--timeout-seconds", cron_timeout,
        "--agent", agent_id,
        "--session", "isolated",
        "--message", cron_message,
    ]
    if chat_id and chat_id not in ("", "YOUR_TELEGRAM_CHAT_ID"):
        cmd.extend(["--announce", "--channel", "telegram", "--to", chat_id])

    run_result = run(cmd)
    if run_result.returncode != 0:
        fail(f"Failed to create cron: {run_result.stderr}")
        sys.exit(1)

    # Extract cron job ID from output
    new_id = cron_job_id
    if not new_id or new_id in ("", "YOUR_AGENT_ID"):
        m = re.search(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            run_result.stdout,
        )
        new_id = m.group(0) if m else ""

    # Update config with new cron_job_id
    if CONFIG_FILE.exists():
        content = read_file(CONFIG_FILE)
        content = re.sub(
            r"(^cron_job_id:\s*).+$",
            rf"\g<1>{new_id}",
            content,
            flags=re.MULTILINE,
        )
        write_file(CONFIG_FILE, content)

    ok(f"Cron job created: {new_id}")
    print(f"\n  Schedule : {cron_schedule}")
    print(f"  Timeout  : {cron_timeout}s")
    print(f"  Agent    : {agent_id}")
    if project_path:
        print(f"  Project  : {project_path}")
    print(f"\n  Run now manually: openclaw cron run {new_id}")


# ── Stop: halt cron托管 ────────────────────────────────────────────────────────

def cmd_stop() -> None:
    step("⏹  Stopping Autonomous Improvement Loop cron")

    config = read_current_config()
    cron_job_id = config.get("cron_job_id", "").strip()

    if not cron_job_id or cron_job_id in ("", "YOUR_AGENT_ID"):
        # Fallback: try to detect from openclaw cron list
        r = run(["openclaw", "cron", "list"], timeout=15)
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                if "autonomous" in line.lower() or "improvement" in line.lower():
                    m = re.search(
                        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
                        line,
                    )
                    if m:
                        cron_job_id = m.group(0)
                        break

    if not cron_job_id or cron_job_id in ("", "YOUR_AGENT_ID"):
        warn("cron job not found")
        return

    r = run(["openclaw", "cron", "rm", cron_job_id], timeout=15)
    if r.returncode != 0:
        warn(f"Failed to remove cron: {r.stderr}")
        sys.exit(1)

    ok(f"Cron job removed: {cron_job_id}")

    # Clear cron_job_id from config
    if CONFIG_FILE.exists():
        content = read_file(CONFIG_FILE)
        content = re.sub(
            r"(^cron_job_id:\s*).+$",
            r"\1",
            content,
            flags=re.MULTILINE,
        )
        write_file(CONFIG_FILE, content)


# ── Add: create user-request task + full plan ─────────────────────────────────

def cmd_add(content_text: str) -> None:
    step("📝 Adding user request as current task")

    if not content_text or not content_text.strip():
        fail("Empty content — nothing to add")
        sys.exit(1)

    content_text = re.sub(r"\s*\n\s*", " ", content_text).strip()
    project, roadmap_path = _get_roadmap_and_project()

    from scripts.roadmap import load_roadmap, set_current_task, init_roadmap, CurrentTask
    from scripts.task_ids import next_task_id
    from scripts.plan_writer import write_plan_doc

    plans_dir = ail_plans_dir(project)
    plans_dir.mkdir(parents=True, exist_ok=True)
    if not roadmap_path.exists():
        init_roadmap(roadmap_path)
        ok(f"Initialized ROADMAP.md at {roadmap_path}")

    roadmap = load_roadmap(roadmap_path)
    if roadmap.current_task and roadmap.current_task.status == "doing":
        warn(f"Current task {roadmap.current_task.task_id} is doing, not interrupting it")
        task_id = next_task_id(plans_dir)
        plan_path = write_plan_doc(
            plans_dir=plans_dir,
            task_id=task_id,
            title=content_text,
            task_type="user",
            source="user",
            context="Direct user request captured via a-add.",
            why_now="User explicitly requested this work and user tasks take priority once the current doing task finishes.",
            scope=[content_text],
            non_goals=["Do not interrupt the currently doing task"],
            relevant_files=["TBD during execution"],
            execution_plan=["Wait for current doing task to finish", "Execute user-requested task next"],
            acceptance_criteria=["Requested change is implemented", "Verification is recorded in the plan execution output"],
            verification=["Run relevant tests or checks for the requested change"],
            risks=["Details may need refinement during implementation"],
        )
        set_current_task(
            roadmap_path,
            roadmap.current_task,
            plan_path=roadmap.current_plan_path,
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            reserved_user_task_id=task_id,
        )
        ok(f"Reserved user task {task_id} for after current doing task")
        print()
        _print_plan_doc(plan_path)
        return

    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=content_text,
        task_type="user",
        source="user",
        context="Direct user request captured via a-add.",
        why_now="User explicitly requested this work and user tasks take priority over PM-generated tasks.",
        scope=[content_text],
        non_goals=["Do not expand scope beyond the user request unless required to complete it"],
        relevant_files=["TBD during implementation"],
        execution_plan=["Understand requested change", "Implement the change", "Verify behavior and summarize result"],
        acceptance_criteria=["Requested change is implemented", "The resulting task plan is visible via a-current"],
        verification=["Run relevant tests or checks for the requested change"],
        risks=["User request may need clarification if ambiguous"],
    )
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type="user",
        source="user",
        title=content_text,
        status="pending",
        created=created,
    )
    set_current_task(
        roadmap_path,
        task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type=roadmap.next_default_type,
        improves_since_last_idea=roadmap.improves_since_last_idea,
        reserved_user_task_id="",
    )
    ok(f"User request saved as {task_id}")
    print()
    _print_plan_doc(plan_path)


# ── Status: inspect project state ─────────────────────────────────────────────

def cmd_status(project: Path) -> None:
    step("📋 Project readiness")

    if not project.exists():
        fail(f"Project path does not exist: {project}")
        sys.exit(1)

    readiness = check_project_readiness(project)
    new_items = sum(1 for v in readiness.values() if not v)
    mode = "bootstrap" if new_items > 3 else "normal"

    repo = detect_github_repo(project)
    config = read_current_config()
    resolved_language = resolve_language(project, explicit=config.get("project_language"))

    print(f"\n  Project: {project.name}")
    print(f"  Path: {project}")
    print(f"  GitHub: {repo or c('not configured', COLOR_YELLOW)}")
    print(f"  Language: {'Chinese' if resolved_language == 'zh' else 'English'}")
    print(f"  Run mode: {c(mode, COLOR_GREEN if mode == 'normal' else COLOR_YELLOW)}")
    print()
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} (missing)")
    print()

    # Queue status
    if ail_heartbeat(project).exists():
        content = read_file(ail_heartbeat(project))
        pending_rows: list[tuple[str, str, str, str]] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|") or stripped.startswith("|---"):
                continue
            m = re.match(
                r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
                stripped,
            )
            if not m:
                continue
            num, kind, score, desc, _source, status = m.groups()
            if status.strip().lower() == "pending":
                pending_rows.append((num, kind.strip(), score, desc.strip()))

        print(f"  Pending queue tasks: {len(pending_rows)} item(s)")
        for num, kind, score, desc in pending_rows[:10]:
            print(f"    #{num} [{kind}/{score}] {desc}")
        if len(pending_rows) > 10:
            print(f"    ... {len(pending_rows) - 10} more item(s) omitted")

    # Cron status
    cron_id = config.get("cron_job_id") or detect_existing_cron()
    if cron_id:
        r = run(["openclaw", "cron", "list"], timeout=10)
        status_text = "active"
        if r.returncode == 0 and cron_id in r.stdout:
            status_text = c("active", COLOR_GREEN)
        print(f"\n  Cron Job: {cron_id} ({status_text})")
    else:
        warn("  Cron Job: not detected")

    print()


# ── a_plan: generate PM task + plan ──────────────────────────────────────────

def _get_roadmap_and_project():
    config = read_current_config()
    project_path_str = config.get("project_path", "").strip()
    if not project_path_str or project_path_str in (".", "YOUR_PROJECT_PATH"):
        detected = detect_project_path()
        project_path_str = str(detected) if detected else str(Path.cwd())
    project = Path(project_path_str).expanduser().resolve()
    roadmap_path = ail_roadmap(project)
    return project, roadmap_path


def cmd_plan(force: bool = False) -> None:
    step("🗺️  Generating current task + plan")
    project, roadmap_path = _get_roadmap_and_project()
    from scripts.roadmap import load_roadmap, set_current_task, init_roadmap, CurrentTask
    from scripts.task_planner import choose_next_task
    from scripts.task_ids import next_task_id
    from scripts.plan_writer import write_plan_doc

    plans_dir = ail_plans_dir(project)

    # Ensure plans dir exists
    plans_dir.mkdir(parents=True, exist_ok=True)

    # Init roadmap if missing
    if not roadmap_path.exists():
        init_roadmap(roadmap_path)
        ok(f"Initialized ROADMAP.md at {roadmap_path}")

    roadmap = load_roadmap(roadmap_path)

    # Check for reserved user task
    if roadmap.reserved_user_task_id and not force:
        warn(f"User task {roadmap.reserved_user_task_id} is reserved — use --force to regenerate anyway")
        cmd_current()
        return

    if roadmap.current_task and roadmap.current_task.status in ("pending", "doing") and not force:
        ok("Current task already exists. Use --force to regenerate.")
        cmd_current()
        return

    # Build done_titles for dedup
    done_titles: set[str] = set()
    for line in roadmap_path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 5 and cells[0].startswith("TASK-"):
            done_titles.add(cells[4])

    language = read_current_config().get("project_language", DEFAULT_LANGUAGE).strip() or "zh"
    planned = choose_next_task(project, roadmap, done_titles, language)

    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=planned.title,
        task_type=planned.task_type,
        source=planned.source,
        context=planned.context,
        why_now=planned.why_now,
        scope=planned.scope,
        non_goals=planned.non_goals,
        relevant_files=planned.relevant_files,
        execution_plan=planned.execution_plan,
        acceptance_criteria=planned.acceptance_criteria,
        verification=planned.verification,
        risks=planned.risks,
    )

    from datetime import datetime, timezone
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type=planned.task_type,
        source=planned.source,
        title=planned.title,
        status="pending",
        created=created,
    )

    next_type = "improve" if roadmap.next_default_type == "idea" else "idea"
    improves = roadmap.improves_since_last_idea + (1 if planned.task_type == "improve" else 0)

    set_current_task(
        roadmap_path, task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type=next_type,
        improves_since_last_idea=improves,
        reserved_user_task_id=roadmap.reserved_user_task_id,
    )
    ok(f"Task {task_id} generated and set as current")
    print()
    _print_plan_doc(plan_path)


# ── a_current: show current task + full plan ──────────────────────────────────

def cmd_current() -> None:
    step("📌 Current Task")
    project, roadmap_path = _get_roadmap_and_project()
    if not roadmap_path.exists():
        ok("ROADMAP.md not found. Run a-plan to generate the first task.")
        return

    from scripts.roadmap import load_roadmap
    roadmap = load_roadmap(roadmap_path)

    if not roadmap.current_task:
        ok("No current task. Run a-plan to generate one.")
        return

    task = roadmap.current_task
    print(f"  Task ID   : {task.task_id}")
    print(f"  Type      : {task.task_type}")
    print(f"  Source    : {task.source}")
    print(f"  Title     : {task.title}")
    print(f"  Status    : {task.status}")
    print(f"  Created   : {task.created}")
    if task.status == "doing":
        print(f"  Plan Path : {roadmap.current_plan_path}")
    print()
    if roadmap.current_plan_path:
        # Plan path is stored as relative to .ail/ e.g. "plans/TASK-001.md"
        plan_path = project / ".ail" / roadmap.current_plan_path
        if plan_path.exists():
            _print_plan_doc(plan_path)
        else:
            warn(f"Plan file not found: {plan_path}")
    elif roadmap.reserved_user_task_id:
        ok(f"Reserved user task: {roadmap.reserved_user_task_id}")


def _print_plan_doc(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # Print key sections
    for section in ["## Goal", "## Context", "## Why now", "## Scope",
                    "## Non-goals", "## Relevant Files", "## Execution Plan",
                    "## Acceptance Criteria", "## Verification", "## Risks / Notes"]:
        if section in text:
            lines = text.split(section, 1)
            if len(lines) > 1:
                content = lines[1].split("\n## ", 1)[0].strip()
                print(f"{c(section, COLOR_BOLD)}")
                print(f"  {content[:300]}")
                print()


# ── Main entry point ────────────────────────────────────────────────────────────

# ── a_queue: show current queue ───────────────────────────────────────────────

def cmd_queue(all_items: bool = False) -> None:
    step("📋 Current Queue")
    if not ail_heartbeat(project).exists():
        fail(f"HEARTBEAT.md not found at {ail_heartbeat(project)}")
        return

    content = read_file(ail_heartbeat(project))

    # Parse ALL rows from ALL ## Queue sections (handles multi-section corruption)
    all_rows: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or stripped.startswith("| #"):
            continue
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if not cells or not re.match(r"^\d+$", cells[0]):
            continue
        if len(cells) >= 8:
            all_rows.append({
                "num": cells[0], "type": cells[1], "score": cells[2],
                "content": cells[3], "detail": cells[4],
                "source": cells[5], "status": cells[6], "created": cells[7],
            })
        elif len(cells) >= 7:
            all_rows.append({
                "num": cells[0], "type": cells[1], "score": cells[2],
                "content": cells[3], "detail": cells[3],
                "source": cells[4], "status": cells[5], "created": cells[6],
            })

    if not all_rows:
        ok("Queue is empty")
        return

    # Deduplicate by normalized content (same logic as project_insights.py)
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for row in all_rows:
        norm = re.sub(r"\s+", " ", row["content"].strip()).lower()
        if norm not in seen:
            seen.add(norm)
            rows.append(row)

    if not rows:
        ok("Queue is empty")
        return

    pending = sum(1 for r in rows if r["status"].lower() != "done")
    print(f"  {len(rows)} total ({pending} pending)\n")
    print(f"  {'#':<3} {'Sc':<4} {'Content':<46} {'Status'}")
    print(f"  {'-'*3} {'-'*4} {'-'*46} {'-'*10}")
    visible_rows = [row for row in rows if all_items or row["status"].lower() != "done"]
    for display_num, row in enumerate(visible_rows, 1):
        marker = c("✓", COLOR_GREEN) if row["status"].lower() == "done" else c("○", COLOR_YELLOW)
        content_short = (row["content"][:43] + "…") if len(row["content"]) > 46 else row["content"]
        print(f"  {c(str(display_num), COLOR_BOLD):<3} {row['score']:<4} {content_short:<46} {marker} {row['status']}")


# ── a_log: show recent Done Log ───────────────────────────────────────────────

def cmd_log(n: int = 10) -> None:
    step("📜 Recent Done Log")
    project, roadmap_path = _get_roadmap_and_project()
    if not roadmap_path.exists():
        ok("ROADMAP.md not found")
        return

    content = read_file(roadmap_path)
    log_match = re.search(r"(## Done Log\n\n)(\| time[\s\S]*?\n)(\|[\s\S]*?)(?=\n## |\Z)", content, re.IGNORECASE)
    if not log_match:
        ok("Done Log section not found")
        return

    data_lines: list[str] = []
    for line in log_match.group(3).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or stripped.lower().startswith("| time"):
            continue
        data_lines.append(stripped)

    if not data_lines:
        ok("Done Log is empty")
        return

    print(f"  Last {min(n, len(data_lines))} of {len(data_lines)} entries\n")
    for line in data_lines[:n]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 7:
            continue
        time_val, task_id, task_type, source, title, result, commit = cells[:7]
        result_mark = c("✓", COLOR_GREEN) if result.lower() == "pass" else c("✗", COLOR_RED)
        task_short = (title[:50] + "…") if len(title) > 50 else title
        print(f"  {time_val[:16]}  {result_mark}  {task_id:<9}  {task_short}  ({commit})")


# ── a_trigger: run current roadmap task immediately ──────────────────────────

def _git_head_short(project: Path) -> str:
    r = run(["git", "rev-parse", "--short", "HEAD"], cwd=project)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "manual"


def cmd_trigger(force: bool = False) -> None:
    step("⚡ Triggering plan execution")
    project, roadmap_path = _get_roadmap_and_project()
    if not roadmap_path.exists():
        fail("ROADMAP.md not found. Run a-plan first.")
        sys.exit(1)

    from scripts.roadmap import load_roadmap, append_done_log, set_current_task, CurrentTask
    roadmap = load_roadmap(roadmap_path)
    if not roadmap.current_task:
        fail("No current task found. Run a-plan first.")
        sys.exit(1)

    current = roadmap.current_task
    if current.status == "doing" and not force:
        warn("Current task is already doing. Use --force to re-run.")
        sys.exit(1)

    ok(f"Started {current.task_id}: {current.title}")
    commit = _git_head_short(project)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    append_done_log(
        roadmap_path,
        timestamp=timestamp,
        task_id=current.task_id,
        task_type=current.task_type,
        source=current.source,
        title=current.title,
        result="pass",
        commit=commit,
    )

    next_task = None
    next_plan_path = ""
    reserved = roadmap.reserved_user_task_id.strip()
    plans_dir = ail_plans_dir(project)
    if reserved:
        reserved_plan = plans_dir / f"{reserved}.md"
        title = reserved
        if reserved_plan.exists():
            first_line = reserved_plan.read_text(encoding="utf-8").splitlines()[0].strip()
            m = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
            title = m.group(1).strip() if m else title
        next_task = CurrentTask(
            task_id=reserved,
            task_type="user",
            source="user",
            title=title,
            status="pending",
            created=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        next_plan_path = str(Path(".ail") / "plans" / f"{reserved}.md")

    if next_task:
        set_current_task(
            roadmap_path,
            next_task,
            plan_path=next_plan_path,
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            reserved_user_task_id="",
        )
        ok(f"Execution recorded, next user task is now current: {next_task.task_id}")
    else:
        set_current_task(
            roadmap_path,
            None,
            plan_path="",
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            reserved_user_task_id="",
        )
        ok("Execution recorded in Done Log")


# ── a_config: get/set config values ─────────────────────────────────────────

def cmd_config(action: str, key: str, value: str | None = None) -> None:
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if action == "get":
        step(f"⚙  Config: {key}")
        config = read_current_config()
        val = config.get(key, "").strip()
        if val:
            ok(f"{key} = {val}")
        else:
            # Try reading directly from config.md (persistent or template)
            if conf.exists():
                raw = read_file(conf)
                m = re.search(rf"^(\s*{re.escape(key)}:\s*)(.*)$", raw, re.MULTILINE)
                if m:
                    print(f"  {key} = {m.group(2).strip()}")
                else:
                    warn(f"Key '{key}' not found in config.md")
            else:
                warn(f"Key '{key}' not found in config.md")
    elif action == "set":
        if not value:
            fail("'set' requires a value argument")
            sys.exit(1)
        step(f"⚙  Config: {key} = {value}")
        # Read from template if persistent doesn't exist yet
        raw = read_file(conf) if conf.exists() else ""
        if not re.search(rf"^{re.escape(key)}:", raw, re.MULTILINE):
            fail(f"Key '{key}' not found in config.md — cannot set unregistered key")
            sys.exit(1)
        current_match = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", raw, re.MULTILINE)
        if current_match and re.sub(r"\s+#.*$", "", current_match.group(1)).strip() == value:
            ok(f"Set {key} = {value} (unchanged)")
            return
        new_raw = re.sub(
            rf"(^\s*{re.escape(key)}:\s*).+$",
            rf"\g<1>{value}",
            raw, flags=re.MULTILINE
        )
        if new_raw == raw:
            fail(f"Pattern did not match for key '{key}'")
            sys.exit(1)
        write_file(CONFIG_FILE, new_raw)
        ok(f"Set {key} = {value}")




def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Autonomous Improvement Loop setup wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Usage examples:

              # Take over an existing project (most common)
              python init.py a-adopt ~/Projects/YOUR_PROJECT

              # Bootstrap a new project
              python init.py a-onboard ~/Projects/MyProject

              # Check project readiness
              python init.py a-status ~/Projects/YOUR_PROJECT

              # Start cron hosting
              python init.py a-start

              # Stop cron hosting
              python init.py a-stop

              # Add a user requirement
              python init.py a-add "Implement dark mode support"

              # Trigger queue scan
              python init.py a-scan

              # Clear non-user tasks
              python init.py a-clear

              # Show current queue
              python init.py a-queue

              # Show recent done log
              python init.py a-log -n 10

              # Full queue refresh (clear + scan)
              python init.py a-refresh

              # Trigger cron immediately
              python init.py a-trigger

              # Read config value
              python init.py a-config get project_language

              # Write config value
              python init.py a-config set project_language zh
            """),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    adopt_p = sub.add_parser("a-adopt", help="Take over an existing project")
    adopt_p.add_argument("project", nargs="?", type=Path)
    adopt_p.add_argument("--agent", help="OpenClaw Agent ID")
    adopt_p.add_argument("--chat-id", help="Telegram Chat ID")
    adopt_p.add_argument("--language", "--lang", "-l", default=None,
                         choices=["en", "zh"],
                         help="Project output language")
    adopt_p.add_argument("--model", "-m", default="",
                         help="LLM model for cron sessions (empty = use OpenClaw default)")
    adopt_p.add_argument("--force-new-cron", action="store_true",
                         help="Force recreation of the Cron Job (replace existing)")
    adopt_p.set_defaults(func=cmd_adopt)

    onboard_p = sub.add_parser("a-onboard", help="Bootstrap a new project from scratch")
    onboard_p.add_argument("project", nargs="?", type=Path)
    onboard_p.add_argument("--agent", help="OpenClaw Agent ID")
    onboard_p.add_argument("--chat-id", help="Telegram Chat ID")
    onboard_p.add_argument("--language", "--lang", "-l", default=None,
                          choices=["en", "zh"],
                          help="Project output language")
    onboard_p.add_argument("--model", "-m", default="",
                          help="LLM model for cron sessions (empty = use OpenClaw default)")
    onboard_p.set_defaults(func=cmd_onboard)

    status_p = sub.add_parser("a-status", help="Check project readiness")
    status_p.add_argument("project", nargs="?", type=Path,
                          default=detect_project_path())
    status_p.set_defaults(func=cmd_status)

    # ── start ─────────────────────────────────────────────────────────────────
    start_p = sub.add_parser("a-start", help="Start cron托管 (create cron job)")
    start_p.set_defaults(func=lambda _a: cmd_start())

    # ── stop ──────────────────────────────────────────────────────────────────
    stop_p = sub.add_parser("a-stop", help="Stop cron托管 (remove cron job)")
    stop_p.set_defaults(func=lambda _a: cmd_stop())

    # ── add ───────────────────────────────────────────────────────────────────
    add_p = sub.add_parser("a-add", help="Create a user-sourced TASK + full plan doc")
    add_p.add_argument("content", nargs="+", help="Requirement content text")
    add_p.set_defaults(func=lambda a: cmd_add(" ".join(a.content)))

    # ── a_plan ────────────────────────────────────────────────────────────────
    plan_p = sub.add_parser("a-plan", help="Generate current task and full plan (PM mode)")
    plan_p.add_argument("--force", action="store_true", help="Regenerate even if current task exists")
    plan_p.set_defaults(func=lambda a: cmd_plan(force=a.force))

    # ── a_current ──────────────────────────────────────────────────────────────
    current_p = sub.add_parser("a-current", help="Show current task + full plan doc")
    current_p.set_defaults(func=lambda _a: cmd_current())

    # ── a_queue (deprecated alias) ──────────────────────────────────────────────
    queue_p = sub.add_parser("a-queue", help="[deprecated: use a-current]")
    queue_p.add_argument("--all", action="store_true", help="Include done items")
    queue_p.set_defaults(func=lambda _a: cmd_current())

    # ── a_log ──────────────────────────────────────────────────────────────────
    log_p = sub.add_parser("a-log", help="Show recent Done Log entries")
    log_p.add_argument("-n", "--count", type=int, default=10,
                      help="Number of entries to show (default: 10)")
    log_p.set_defaults(func=lambda a: cmd_log(n=a.count))

    # ── a_refresh ──────────────────────────────────────────────────────────────
    refresh_p = sub.add_parser("a-refresh", help="[deprecated alias: use a-plan]")
    refresh_p.set_defaults(func=lambda _a: cmd_plan(force=True))

    # ── a_trigger ──────────────────────────────────────────────────────────────
    trigger_p = sub.add_parser("a-trigger", help="Execute current roadmap task immediately")
    trigger_p.add_argument("--force", action="store_true",
                          help="Re-run even if current task is already marked doing")
    trigger_p.set_defaults(func=lambda a: cmd_trigger(force=a.force))

    # ── a_config ───────────────────────────────────────────────────────────────
    config_sp = sub.add_parser("a-config", help="Get or set config values")
    config_sp.add_argument("action", choices=["get", "set"],
                          help="'get' to read a value, 'set' to write")
    config_sp.add_argument("key", help="Config key (e.g. project_language)")
    config_sp.add_argument("value", nargs="?", help="New value (required for 'set')")
    config_sp.set_defaults(func=lambda a: cmd_config(action=a.action, key=a.key, value=a.value))

    args = parser.parse_args()

    # Auto-detect project path if not given
    if hasattr(args, "project") and args.project is None:
        detected = detect_project_path()
        if detected:
            print(f"Auto-detected project: {detected}")
            args.project = detected
        else:
            print("Error: could not auto-detect a project path. Pass one explicitly or run inside a project directory.")
            print("\nNo Git repository was found in:")
            print("  ~/Projects/")
            print("  ~/projects/")
            print("  ~/Code/")
            print("\nSpecify one manually, for example: python init.py adopt ~/Projects/YourProject")
            parser.parse_args(["a-adopt", "--help"])
            sys.exit(1)

    # Auto-detect agent_id
    if hasattr(args, "agent") and not args.agent:
        args.agent = detect_openclaw_agent_id()

    # Auto-detect chat_id
    if hasattr(args, "chat_id") and not getattr(args, "chat_id", None):
        args.chat_id = detect_telegram_chat_id()

    # Auto-detect language
    if hasattr(args, "language") and not args.language:
        args.language = resolve_language(getattr(args, "project", None), explicit=None)

    try:
        if args.command == "a-adopt":
            cmd_adopt(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
                force_new_cron=args.force_new_cron,
            )
        elif args.command == "a-onboard":
            cmd_onboard(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
            )
        elif args.command == "a-status":
            cmd_status(args.project)
        elif args.command == "a-start":
            cmd_start()
        elif args.command == "a-stop":
            cmd_stop()
        elif args.command == "a-add":
            cmd_add(" ".join(args.content))
        elif args.command == "a-plan":
            cmd_plan(force=args.force)
        elif args.command == "a-current":
            cmd_current()
        elif args.command == "a-queue":
            cmd_current()
        elif args.command == "a-log":
            cmd_log(n=args.count)
        elif args.command == "a-refresh":
            cmd_plan(force=True)
        elif args.command == "a-trigger":
            cmd_trigger(force=args.force)
        elif args.command == "a-config":
            cmd_config(action=args.action, key=args.key, value=args.value)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
