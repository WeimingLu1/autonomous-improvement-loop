"""
Detection helpers — project path, GitHub, language, agent, cron, readiness.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional


# ── Project Path Detection ────────────────────────────────────────────────────

def detect_project_path() -> Path | None:
    cwd = Path.cwd()
    if (cwd / ".ail").exists() or (cwd / "ROADMAP.md").exists():
        return cwd
    git_dir = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=5,
    )
    if git_dir.returncode == 0:
        candidate = Path(git_dir.stdout.strip())
        if candidate.exists():
            return candidate
    # Walk upward looking for a directory with .git or .ail
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists() or (parent / ".ail").exists():
            return parent
    return None


# ── GitHub Repository Detection ────────────────────────────────────────────────

def detect_github_repo(project: Path) -> str | None:
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project, capture_output=True, text=True, timeout=5,
        )
        if remote.returncode == 0:
            url = remote.stdout.strip()
            # git@github.com:owner/repo.git → https://github.com/owner/repo
            m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url)
            if m:
                return f"https://github.com/{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


# ── Project Language Detection ─────────────────────────────────────────────────

KNOWN_VERSION_FILES = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "CMakeLists.txt": "c++",
    "Makefile": "c",
    "*.c": "c",
    "*.cpp": "c++",
    "*.rs": "rust",
    "*.js": "javascript",
    "*.ts": "typescript",
    "*.java": "java",
    "*.py": "python",
}

def detect_project_language(project: Path) -> str:
    for fname in ["pyproject.toml", "setup.py", "requirements.txt", "package.json", "go.mod", "Cargo.toml"]:
        if (project / fname).exists():
            if fname in ("pyproject.toml", "setup.py", "requirements.txt"):
                return "python"
            elif fname == "package.json":
                return "node"
            elif fname == "go.mod":
                return "go"
            elif fname == "Cargo.toml":
                return "rust"
    for root, _, files in os.walk(project):
        skip = any(p in root for p in [".git", "node_modules", "__pycache__", ".venv", "venv"])
        if skip:
            continue
        for f in files:
            if f.endswith(".py"):
                return "python"
            elif f.endswith(".ts") and not f.endswith(".d.ts"):
                return "typescript"
            elif f.endswith(".js"):
                return "javascript"
            elif f.endswith(".go"):
                return "go"
            elif f.endswith(".rs"):
                return "rust"
            elif f.endswith(".java"):
                return "java"
    return "generic"


def detect_agent_language() -> str:
    # Detect from environment or config
    env_lang = os.environ.get("OPENCLAW_AGENT_LANGUAGE", "")
    if env_lang in ("zh", "en"):
        return env_lang
    # Check config file
    config_home = Path.home() / ".openclaw"
    for cfg in [config_home / "agent.yaml", config_home / "config.yaml"]:
        if cfg.exists():
            try:
                text = cfg.read_text(encoding="utf-8")
                m = re.search(r"\blanguage:\s*(\w+)", text)
                if m:
                    return m.group(1)
            except Exception:
                pass
    return ""


# ── Version File Detection ─────────────────────────────────────────────────────

def detect_version_file(project: Path) -> Path:
    for candidate in ["VERSION", "version.py", "__version__.py", "_version.py", "version.txt"]:
        p = project / candidate
        if p.exists():
            return p
    return project / "VERSION"


# ── CLI Name Detection ────────────────────────────────────────────────────────

def detect_cli_name(project: Path) -> str:
    if (project / "pyproject.toml").exists():
        try:
            text = (project / "pyproject.toml").read_text(encoding="utf-8")
            m = re.search(r'name\s*=\s*"([^"]+)"', text)
            if m:
                return m.group(1)
        except Exception:
            pass
    return project.name


# ── Agent / Chat ID Detection ─────────────────────────────────────────────────

def detect_openclaw_agent_id() -> str | None:
    try:
        result = subprocess.run(
            ["openclaw", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            return data.get("agent_id") or data.get("id")
    except Exception:
        pass
    # Fallback: check env
    return os.environ.get("OPENCLAW_AGENT_ID", "").strip() or None


def detect_telegram_chat_id() -> str | None:
    # Check skill config
    config_home = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop"
    config_file = config_home / "config.md"
    if config_file.exists():
        text = config_file.read_text(encoding="utf-8")
        m = re.search(r"(?:chat_id|telegram_chat_id):\s*(\S+)", text)
        if m:
            return m.group(1)
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None


# ── Cron Detection ────────────────────────────────────────────────────────────

def detect_existing_cron() -> str | None:
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import json
            jobs = json.loads(result.stdout)
            for job in jobs:
                label = job.get("label", "")
                if "autonomous-improvement-loop" in label:
                    return job.get("id") or job.get("cron_job_id") or label
    except Exception:
        pass
    return None


# ── Testing Detection ─────────────────────────────────────────────────────────

def detect_pytest_available() -> bool:
    result = subprocess.run(
        ["python3", "-m", "pytest", "--version"],
        capture_output=True, timeout=5,
    )
    return result.returncode == 0


def detect_any_test_command(project: Path) -> tuple[bool, str]:
    if (project / "pyproject.toml").exists():
        try:
            text = (project / "pyproject.toml").read_text(encoding="utf-8")
            if 'pytest' in text or '"pytest"' in text:
                return True, "python3 -m pytest"
        except Exception:
            pass
    if (project / "Makefile").exists():
        return True, "make test"
    if (project / "package.json").exists():
        try:
            text = (project / "package.json").read_text(encoding="utf-8")
            if '"test"' in text:
                import json
                data = json.loads(text)
                script = data.get("scripts", {}).get("test", "")
                if script:
                    return True, script
        except Exception:
            pass
    return False, ""


# ── Build Config Detection ────────────────────────────────────────────────────

def detect_build_config(project: Path) -> str:
    if (project / "pyproject.toml").exists():
        return "python"
    if (project / "Makefile").exists():
        return "make"
    if (project / "package.json").exists():
        return "node"
    if (project / "go.mod").exists():
        return "go"
    if (project / "Cargo.toml").exists():
        return "rust"
    return "unknown"


# ── GitHub Auth Detection ─────────────────────────────────────────────────────

def detect_gh_authenticated() -> bool:
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True, text=True, timeout=5,
    )
    return result.returncode == 0


# ── Readiness Checks ─────────────────────────────────────────────────────────

def _read_kind_from_config() -> str:
    config_home = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop"
    config_file = config_home / "config.md"
    if config_file.exists():
        text = config_file.read_text(encoding="utf-8")
        m = re.search(r"project_kind:\s*(\S+)", text)
        if m:
            return m.group(1)
    return "software"


def check_project_readiness(project: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    checks["README.md exists"] = (project / "README.md").exists()
    checks[".git directory"] = (project / ".git").exists()

    # Check for docs/agent
    docs_agent = project / "docs" / "agent"
    checks["docs/agent directory"] = docs_agent.exists() or (project / "docs").exists()

    # Check for test files
    has_tests = (
        (project / "tests").exists() or
        (project / "test").exists() or
        (project / "pytest.ini").exists() or
        (project / "pyproject.toml").exists()
    )
    checks["test directory or config"] = has_tests

    # Check for version file
    has_version = (
        (project / "version.py").exists() or
        (project / "__version__.py").exists() or
        (project / "VERSION").exists() or
        (project / "pyproject.toml").exists()
    )
    checks["version file"] = has_version

    # Check for docs
    has_docs = (
        docs_agent.exists() or
        (project / "docs").exists() or
        (project / "doc").exists()
    )
    checks["docs directory"] = has_docs

    return checks


# ── Config Writing ─────────────────────────────────────────────────────────────

def build_config(
    project_path: Path,
    repo: str,
    version_file: Path,
    docs_dir: Path,
    cli_name: str,
    agent_id: str,
    chat_id: str,
    language: str,
    cron_job_id: str | None,
    project_kind: str,
) -> str:
    config = textwrap.dedent(f"""\
        # Auto-generated by autonomous-improvement-loop
        project_path: {project_path}
        repo: {repo}
        version_file: {version_file}
        docs_dir: {docs_dir}
        cli_name: {cli_name}
        agent_id: {agent_id}
        telegram_chat_id: {chat_id}
        project_language: {language}
        cron_job_id: {cron_job_id or ''}
        project_kind: {project_kind}
    """)
    return config


def write_config(
    project_path: Path,
    repo: str,
    version_file: Path,
    docs_dir: Path,
    cli_name: str,
    agent_id: str,
    chat_id: str,
    language: str,
    cron_job_id: str | None,
    project_kind: str,
) -> None:
    from .state import write_file, ail_config
    config_path = ail_config(project_path)
    content = build_config(
        project_path=project_path,
        repo=repo,
        version_file=version_file,
        docs_dir=docs_dir,
        cli_name=cli_name,
        agent_id=agent_id,
        chat_id=chat_id,
        language=language,
        cron_job_id=cron_job_id,
        project_kind=project_kind,
    )
    write_file(config_path, content)