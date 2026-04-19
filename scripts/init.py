#!/usr/bin/env python3
r"""
Autonomous Improvement Loop — setup wizard & cron hosting CLI

Supports these flows:
  adopt    Take over an existing project (auto-detect, configure, start)
  onboard  Bootstrap a brand-new project
  status   Check project readiness and queue state

  start    Start cron hosting (create cron job from config.md)
  stop     Stop cron hosting (remove cron job)
  add      Add a user requirement to the queue
  scan     Trigger a queue scan via project_insights.py
  clear    Clear non-user tasks from the queue

Examples:
  # Take over an existing project (most common)
  python init.py adopt ~/Projects/YOUR_PROJECT

  # Bootstrap a new project
  python init.py onboard ~/Projects/MyProject

  # Check project readiness
  python init.py status ~/Projects/YOUR_PROJECT

  # Start cron hosting
  python init.py start

  # Stop cron hosting
  python init.py stop

  # Add a user requirement
  python init.py add "Implement dark mode support"

  # Trigger queue scan
  python init.py scan

  # Clear non-user tasks
  python init.py clear

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

# ── Constants ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent.resolve()
SKILL_DIR = HERE.parent
HEARTBEAT = SKILL_DIR / "HEARTBEAT.md"
CONFIG_FILE = SKILL_DIR / "config.md"

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
    if CONFIG_FILE.exists():
        m = re.search(r"^agent_id:\s*([^#\n]+)", read_file(CONFIG_FILE), re.MULTILINE)
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
    if CONFIG_FILE.exists():
        m = re.search(r"chat_id:\s*(\d+)", read_file(CONFIG_FILE))
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
    """Detect whether a runnable verification/test command is available."""
    runners = [
        (["python3", "-m", "pytest"], "pytest", None),
        (["npm", "test"], "npm test", "npm"),
        (["cargo", "test"], "cargo test", "cargo"),
        (["go", "test", "./..."], "go test ./...", "go"),
        (["make", "test"], "make test", "make"),
    ]
    for cmd, label, binary in runners:
        if binary and shutil.which(binary) is None:
            continue
        try:
            r = run(cmd, cwd=project, timeout=10)
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
    if not CONFIG_FILE.exists():
        return "generic"
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
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


def read_current_config() -> dict[str, str]:
    """Read existing config values."""
    if not CONFIG_FILE.exists():
        return {}
    text = read_file(CONFIG_FILE)
    result = {}
    for line in text.splitlines():
        m = re.match(r"^(\w[\w_]*):\s*(.+)$", line.strip())
        if m:
            value = re.sub(r"\s+#.*$", "", m.group(2)).strip()
            result[m.group(1)] = value
    return result


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
    """Populate initial queue after init so the user gets value immediately."""
    if mode == "bootstrap":
        run(
            [
                sys.executable,
                str(HERE / "bootstrap.py"),
                "--project", str(project),
                "--skill-dir", str(SKILL_DIR),
                "--mode", "detect",
            ],
            cwd=SKILL_DIR,
            timeout=120,
        )
        return

    run(
        [
            sys.executable,
            str(HERE / "project_insights.py"),
            "--project", str(project),
            "--heartbeat", str(HEARTBEAT),
            "--language", language,
            "--refresh", "--min", "5",
        ],
        cwd=SKILL_DIR,
        timeout=120,
    )


# ── HEARTBEAT queue initialization ─────────────────────────────────────────────

def init_queue_heartbeat(mode: str, language: str) -> None:
    """Initialize or update the Run Status + empty Queue section."""
    if not HEARTBEAT.exists():
        raise RuntimeError(f"HEARTBEAT.md not found at {HEARTBEAT}")

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

    content = read_file(HEARTBEAT)

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

    write_file(HEARTBEAT, content)


def pending_queue_rows() -> list[dict[str, str]]:
    if not HEARTBEAT.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in read_file(HEARTBEAT).splitlines():
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


def write_pending_queue(rows: list[dict[str, str]]) -> None:
    content = read_file(HEARTBEAT)
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
    write_file(HEARTBEAT, content)


def update_run_status_mode(mode: str) -> None:
    if not HEARTBEAT.exists():
        return
    content = read_file(HEARTBEAT)
    content = re.sub(r"(\| mode \| )([^|]+)( \|)", rf"\1{mode}\3", content)
    write_file(HEARTBEAT, content)


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

    # Queue handling for old managed projects
    mode = "bootstrap" if new_items > 3 else "normal"
    current_rows = pending_queue_rows()
    if current_rows:
        step("📦 Existing queue detected")
        deduped_rows, removed = dedupe_pending_rows(current_rows)
        default_action = "c" if removed else "k"
        action = ask("  Queue handling (k=keep, c=dedupe and keep, r=clear and rebuild)", default_action).lower()
        if action == "r":
            init_queue_heartbeat(mode=mode, language=language)
            ok(f"HEARTBEAT.md rebuilt (mode: {mode})")
        elif action == "c":
            write_pending_queue(deduped_rows)
            update_run_status_mode(mode)
            ok(f"Queue deduplicated, removed {removed} duplicate item(s)")
        else:
            update_run_status_mode(mode)
            ok("Kept existing queue, updated run mode only")
    else:
        step("📋 Initializing HEARTBEAT.md")
        init_queue_heartbeat(mode=mode, language=language)
        ok(f"HEARTBEAT.md initialized (mode: {mode})")

    step("🧠 Generating initial queue")
    if len(pending_queue_rows()) < 5:
        seed_queue(project=project, mode=mode, language=language)
        ok("Initial queue generated and topped up")
    else:
        ok("Existing queue is already sufficient")

    # Done
    print(textwrap.dedent(f"""

    {c('✅ Takeover complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Mode: {mode}
    Language: {'Chinese' if language == 'zh' else 'English'}
    Cron: {cron_job_id or 'not created'}

    {'The first run will stay in bootstrap mode until the project is ready' if mode == 'bootstrap' else 'Cron runs automatically every 30 minutes'}

    View queue:
      cat {HEARTBEAT}

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

    # Step 7: init heartbeat
    step("📋 Initializing HEARTBEAT.md")
    init_queue_heartbeat(mode="bootstrap", language=language)
    ok("HEARTBEAT.md initialized (mode: bootstrap)")

    print(textwrap.dedent(f"""
    {c('✅ New project bootstrap complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Type: {kind}
    Directory: {project}

    Next step:
      python init.py adopt {project}  # take over the project and start Cron

    View queue:
      cat {HEARTBEAT}
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

    # Check if already exists
    r = run(["openclaw", "cron", "list"], timeout=15)
    if r.returncode == 0 and cron_job_id and cron_job_id in r.stdout:
        ok(f"Cron job already active: {cron_job_id}")
        print(f"\n  Use 'python init.py stop' to remove it, or\n"
              f"  openclaw cron run {cron_job_id}  to trigger manually.")
        return

    if not agent_id or agent_id in ("", "YOUR_AGENT_ID"):
        fail("agent_id not configured in config.md")
        sys.exit(1)

    # Build openclaw cron add command
    cmd = [
        "openclaw", "cron", "add",
        "--name", "Autonomous Improvement Loop",
        "--cron", cron_schedule,
        "--timeout-seconds", cron_timeout,
        "--agent", agent_id,
        "--session", "isolated",
        "--message", "Autonomous improvement loop triggered",
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


# ── Add: insert user requirement into queue ───────────────────────────────────

def cmd_add(content_text: str) -> None:
    step("📝 Adding user requirement to queue")

    if not HEARTBEAT.exists():
        fail(f"HEARTBEAT.md not found at {HEARTBEAT}")
        sys.exit(1)

    if not content_text or not content_text.strip():
        fail("Empty content — nothing to add")
        sys.exit(1)

    # Parse Content (first 30 chars) + Detail (full)
    content_stripped = content_text.strip()
    content_summary = content_stripped[:30] + ("…" if len(content_stripped) > 30 else "")
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read existing queue rows
    existing_rows: list[dict[str, str]] = []
    max_num = 0
    full_content = read_file(HEARTBEAT)

    queue_match = re.search(
        r"(\n## Queue\n\n)\|[\s\S]*?\n---\n",
        full_content,
    )
    if queue_match:
        queue_block = queue_match.group(0)
        for line in queue_block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|") or "---" in stripped or stripped.startswith("| #"):
                continue
            m = re.match(
                r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
                stripped,
            )
            if m:
                num = int(m.group(1))
                max_num = max(max_num, num)
                existing_rows.append(
                    {
                        "kind": m.group(2).strip(),
                        "score": m.group(3).strip(),
                        "desc": m.group(4).strip(),
                        "source": m.group(5).strip(),
                        "status": m.group(6).strip(),
                        "created": m.group(7).strip(),
                        "_num": str(num),
                    }
                )

    # Build new row (insert at top)
    new_row = {
        "kind": "improvement",
        "score": "100",
        "desc": content_summary,
        "source": "user",
        "status": "pending",
        "created": created,
        "detail": content_stripped,
        "_num": "0",
    }

    # Insert at top
    all_rows = [new_row] + existing_rows

    # Re-number
    table_lines = [
        "| # | Type | Score | Content | Source | Status | Created |",
        "|---|------|-------|---------|--------|--------|---------|",
    ]
    for i, row in enumerate(all_rows, 1):
        detail_note = f" ({row['detail']})" if "detail" in row else ""
        table_lines.append(
            f"| {i} | {row['kind']} | {row['score']} | {row['desc']}{detail_note} | {row['source']} | pending | {row['created']} |"
        )

    new_queue_block = "\n" + "\n".join(table_lines) + "\n---\n"

    if queue_match:
        new_content = full_content[:queue_match.start()] + "\n## Queue\n\n" + new_queue_block + full_content[queue_match.end():]
    else:
        # Queue section doesn't exist, insert before ---
        sep = re.search(r"\n---\n\n##", full_content)
        if sep:
            insert_at = sep.start()
            new_content = full_content[:insert_at] + "\n## Queue\n\n" + new_queue_block + full_content[insert_at:]
        else:
            new_content = full_content + "\n## Queue\n\n" + new_queue_block

    write_file(HEARTBEAT, new_content)
    ok(f"Added to queue: {content_summary}")
    info(f"Full detail stored: {content_stripped[:80]}...")


# ── Scan: trigger queue scan ──────────────────────────────────────────────────

def cmd_scan() -> None:
    step("🔍 Triggering queue scan")

    config = read_current_config()
    project_path_str = config.get("project_path", "").strip()
    heartbeat_path_str = config.get("heartbeat_path", str(HEARTBEAT)).strip()
    language = config.get("project_language", DEFAULT_LANGUAGE).strip()

    if not project_path_str or project_path_str in (".", "YOUR_PROJECT_PATH"):
        detected = detect_project_path()
        if detected:
            project_path_str = str(detected)
            ok(f"Auto-detected project: {project_path_str}")
        else:
            fail("project_path not configured in config.md and could not auto-detect")
            sys.exit(1)

    project_p = Path(project_path_str)
    heartbeat_p = Path(heartbeat_path_str) if heartbeat_path_str else HEARTBEAT

    if not project_p.exists():
        fail(f"Project path does not exist: {project_p}")
        sys.exit(1)

    ok(f"Running: project_insights.py --project {project_p} --heartbeat {heartbeat_p} --language {language} --refresh --min 3")

    r = run(
        [
            sys.executable,
            str(HERE / "project_insights.py"),
            "--project", str(project_p),
            "--heartbeat", str(heartbeat_p),
            "--language", language,
            "--refresh",
            "--min", "3",
        ],
        cwd=SKILL_DIR,
        timeout=180,
    )
    if r.returncode != 0:
        fail(f"Scan failed: {r.stderr}")
        sys.exit(1)

    ok("Queue scan complete")
    if r.stdout.strip():
        print(r.stdout[:500])


# ── Clear: remove non-user tasks ──────────────────────────────────────────────

def cmd_clear() -> None:
    step("🗑  Clearing non-user tasks from queue")

    config = read_current_config()
    heartbeat_path_str = config.get("heartbeat_path", str(HEARTBEAT)).strip()
    heartbeat_p = Path(heartbeat_path_str) if heartbeat_path_str else HEARTBEAT

    if not heartbeat_p.exists():
        fail(f"HEARTBEAT.md not found at {heartbeat_p}")
        sys.exit(1)

    ok(f"Running: queue_scanner.py --clear")

    r = run(
        [sys.executable, str(HERE / "queue_scanner.py"), "--clear"],
        cwd=SKILL_DIR,
        timeout=60,
    )
    if r.returncode != 0:
        warn(f"queue_scanner.py reported issues: {r.stderr}")

    ok("Non-user tasks cleared")
    if r.stdout.strip():
        print(r.stdout[:500])


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
    if HEARTBEAT.exists():
        content = read_file(HEARTBEAT)
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


# ── Main entry point ────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Autonomous Improvement Loop setup wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Usage examples:

              # Take over an existing project (most common)
              python init.py adopt ~/Projects/YOUR_PROJECT

              # Bootstrap a new project
              python init.py onboard ~/Projects/MyProject

              # Check project readiness
              python init.py status ~/Projects/YOUR_PROJECT

              # Start cron托管
              python init.py start

              # Stop cron托管
              python init.py stop

              # Add a user requirement
              python init.py add "Implement dark mode support"

              # Trigger queue scan
              python init.py scan

              # Clear non-user tasks
              python init.py clear
            """),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    adopt_p = sub.add_parser("adopt", help="Take over an existing project")
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

    onboard_p = sub.add_parser("onboard", help="Bootstrap a new project from scratch")
    onboard_p.add_argument("project", nargs="?", type=Path)
    onboard_p.add_argument("--agent", help="OpenClaw Agent ID")
    onboard_p.add_argument("--chat-id", help="Telegram Chat ID")
    onboard_p.add_argument("--language", "--lang", "-l", default=None,
                          choices=["en", "zh"],
                          help="Project output language")
    onboard_p.add_argument("--model", "-m", default="",
                          help="LLM model for cron sessions (empty = use OpenClaw default)")
    onboard_p.set_defaults(func=cmd_onboard)

    status_p = sub.add_parser("status", help="Check project readiness")
    status_p.add_argument("project", nargs="?", type=Path,
                          default=detect_project_path())
    status_p.set_defaults(func=cmd_status)

    # ── start ─────────────────────────────────────────────────────────────────
    start_p = sub.add_parser("start", help="Start cron托管 (create cron job)")
    start_p.set_defaults(func=lambda _a: cmd_start())

    # ── stop ──────────────────────────────────────────────────────────────────
    stop_p = sub.add_parser("stop", help="Stop cron托管 (remove cron job)")
    stop_p.set_defaults(func=lambda _a: cmd_stop())

    # ── add ───────────────────────────────────────────────────────────────────
    add_p = sub.add_parser("add", help="Add a user requirement to the queue")
    add_p.add_argument("content", nargs="+", help="Requirement content text")
    add_p.set_defaults(func=lambda a: cmd_add(" ".join(a.content)))

    # ── scan ──────────────────────────────────────────────────────────────────
    scan_p = sub.add_parser("scan", help="Trigger a queue scan")
    scan_p.set_defaults(func=lambda _a: cmd_scan())

    # ── clear ────────────────────────────────────────────────────────────────
    clear_p = sub.add_parser("clear", help="Clear non-user tasks from queue")
    clear_p.set_defaults(func=lambda _a: cmd_clear())

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
            parser.parse_args(["adopt", "--help"])
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
        if args.command == "adopt":
            cmd_adopt(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
                force_new_cron=args.force_new_cron,
            )
        elif args.command == "onboard":
            cmd_onboard(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
            )
        elif args.command == "status":
            cmd_status(args.project)
        elif args.command == "start":
            cmd_start()
        elif args.command == "stop":
            cmd_stop()
        elif args.command == "add":
            cmd_add(" ".join(args.content))
        elif args.command == "scan":
            cmd_scan()
        elif args.command == "clear":
            cmd_clear()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
