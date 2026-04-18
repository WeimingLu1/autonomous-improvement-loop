#!/usr/bin/env python3
r"""
Autonomous Improvement Loop — 初始化向导

支持两种场景：
  adopt    接管已有项目（自动检测、配置、一键启动）
  onboard  从零初始化新项目

用法：
  # 接管已有项目（最常用）
  python init.py adopt ~/Projects/YOUR_PROJECT

  # 从零初始化新项目
  python init.py onboard ~/Projects/MyProject

  # 查看项目就绪状态
  python init.py status ~/Projects/YOUR_PROJECT

  # 交互式向导（自动检测所有信息）
  python init.py adopt

所有参数均为可选：init.py 会自动检测项目路径、GitHub 仓库、
Agent ID、Telegram Chat ID，必要时才询问。
"""

from __future__ import annotations

import json
import os
import re
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
DEFAULT_LANGUAGE = "zh"

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
        dominant = max(exts, key=exts.get)
        # Python projects typically have Chinese docs
        return "zh"
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
        "Git 仓库": (project / ".git").exists(),
        "README 存在": readme_ok,
        "GitHub CLI 已认证": detect_gh_authenticated(),
    }

    if kind == "software":
        build_label = f"构建系统 ({build_cfg})" if build_cfg else "构建系统"
        test_label = f"验证命令 ({test_cmd})" if test_cmd else "验证命令"
        return {
            **base,
            "源码目录存在": any((project / d).exists() for d in ["src", "lib", "app", "packages"]),
            build_label: bool(build_cfg),
            test_label: test_ok if test_cmd else not (project / "tests").exists(),
        }
    if kind == "writing":
        return {
            **base,
            "内容目录存在": any((project / d).exists() for d in ["chapters", "manuscript", "drafts", "scenes"]),
            "大纲存在": any((project / f).exists() for f in ["outline.md", "outline.txt"]),
            "角色/素材目录存在": any((project / d).exists() for d in ["characters", "notes", "materials"]),
        }
    if kind == "video":
        return {
            **base,
            "脚本目录存在": any((project / d).exists() for d in ["scripts", "scenes"]),
            "分镜/素材目录存在": any((project / d).exists() for d in ["storyboard", "assets", "footage"]),
            "大纲存在": any((project / f).exists() for f in ["outline.md", "treatment.md"]),
        }
    if kind == "research":
        return {
            **base,
            "研究内容目录存在": any((project / d).exists() for d in ["papers", "notes", "references"]),
            "大纲存在": any((project / f).exists() for f in ["outline.md", "proposal.md"]),
            "引用/文献存在": any((project / d).exists() for d in ["references", "bib"]),
        }
    return {
        **base,
        "内容目录存在": any((project / d).exists() for d in ["docs", "materials", "notes", "content", "assets"]),
        "结构文件存在": any((project / f).exists() for f in ["outline.md", "index.md", "README.md"]),
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
    kind_line = f"    project_kind: {project_kind or 'generic'}   # software | writing | video | research | generic"
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
    project_language: {language}   # "en" = English output, "zh" = Chinese output

    ## Verification & Publish
    verification_command:   # empty = no auto-verification
    publish_command:        # optional: shell command after successful task

    ## Cron
    cron_schedule: "*/30 * * * *"
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
        "--model", model,
        "--timeout-seconds", str(DEFAULT_TIMEOUT_S),
        "--message", "Autonomous improvement loop triggered",
    ]
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


# ── Adopt: 接管已有项目 ─────────────────────────────────────────────────────────

def cmd_adopt(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    model: str = "MODEL",
    force_new_cron: bool = False,
) -> None:
    step("🔍 接管已有项目 — 初始化向导")

    # Detect / validate project
    if not project.exists():
        fail(f"项目路径不存在: {project}")
        sys.exit(1)

    repo = detect_github_repo(project)
    version_file = detect_version_file(project)
    docs_dir = project / "docs" / "agent"
    cli_name = detect_cli_name(project)
    readiness = check_project_readiness(project)

    # Show project info
    print(f"\n  {c('项目:', COLOR_BOLD)} {project.name}")
    print(f"  {c('路径:', COLOR_BOLD)} {project}")
    print(f"  {c('GitHub:', COLOR_BOLD)} {repo or c('未检测到（稍后需手动配置）', COLOR_YELLOW)}")
    print(f"  {c('CLI 名称:', COLOR_BOLD)} {cli_name}")
    print(f"  {c('语言:', COLOR_BOLD)} {'中文' if language == 'zh' else 'English'}")
    print(f"  {c('Agent ID:', COLOR_BOLD)} {agent_id or c('未检测到', COLOR_RED)}")

    # Show readiness
    step("📋 项目就绪状态检查")
    new_items = sum(1 for v in readiness.values() if not v)
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} {c('(缺失)', COLOR_YELLOW)}")
    print()

    if new_items > 3:
        warn(f"项目有 {new_items} 项未就绪。建议先修复再启动自主循环，或先接管再逐步完善。")
        print("  继续启动...（自主循环会在 Bootstrap 模式下等待）\n")

    # Existing cron?
    existing_cron = detect_existing_cron()
    if existing_cron and not force_new_cron:
        ok(f"已有 Cron Job: {existing_cron}")
        cron_job_id = existing_cron
        use_existing = ask(
            f"  {c('Cron 处理方式（s=继续使用, r=删除并重建）', COLOR_BOLD)}",
            "s",
        ).lower()
        if use_existing == "r":
            delete_cron(existing_cron)
            existing_cron = None
            print("  已删除旧 Cron，将创建新的。")
        else:
            print("  使用现有 Cron。")
    else:
        existing_cron = None

    # Create cron if needed
    if not existing_cron:
        if not agent_id:
            fail("无法创建 Cron：Agent ID 未设置。请先配置 openclaw agent。")
            sys.exit(1)
        if not chat_id:
            warn("Telegram Chat ID 未设置，Cron 不会发送通知。继续？[y/N]")
            if ask("  >", "n").lower() != "y":
                sys.exit(0)

        step("⏰ 创建 Cron Job")
        try:
            cron_job_id = create_cron(agent_id, model, chat_id)
            ok(f"Cron Job 创建成功: {cron_job_id}")
        except Exception as e:
            warn(f"创建 Cron 失败: {e}")
            warn("Cron 未创建，手动运行: openclaw cron add ...")
            cron_job_id = None
    else:
        cron_job_id = existing_cron

    # Write config
    step("📝 写入 config.md")
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
    )
    ok("config.md 已更新")

    # Queue handling for old managed projects
    mode = "bootstrap" if new_items > 3 else "normal"
    current_rows = pending_queue_rows()
    if current_rows:
        step("📦 检测到已有队列")
        deduped_rows, removed = dedupe_pending_rows(current_rows)
        default_action = "c" if removed else "k"
        action = ask("  队列处理方式（k=保留, c=去重保留, r=清空重建）", default_action).lower()
        if action == "r":
            init_queue_heartbeat(mode=mode, language=language)
            ok(f"HEARTBEAT.md 已重建（模式: {mode}）")
        elif action == "c":
            write_pending_queue(deduped_rows)
            update_run_status_mode(mode)
            ok(f"队列已去重，移除 {removed} 条重复项")
        else:
            update_run_status_mode(mode)
            ok("保留现有队列，仅更新运行模式")
    else:
        step("📋 初始化 HEARTBEAT.md")
        init_queue_heartbeat(mode=mode, language=language)
        ok(f"HEARTBEAT.md 已初始化（模式: {mode}）")

    step("🧠 生成初始队列")
    if len(pending_queue_rows()) < 5:
        seed_queue(project=project, mode=mode, language=language)
        ok("初始队列已生成/补足")
    else:
        ok("现有队列已足够，无需补足")

    # Done
    print(textwrap.dedent(f"""

    {c('✅ 接管完成!', COLOR_GREEN + COLOR_BOLD)}

    项目: {project.name}
    模式: {mode}
    语言: {'中文' if language == 'zh' else 'English'}
    Cron: {cron_job_id or '未创建'}

    {'首次运行将执行 Bootstrap（等待项目就绪）' if mode == 'bootstrap' else 'Cron 每 30 分钟自动执行'}

    查看队列:
      cat {HEARTBEAT}

    手动触发 Cron:
      openclaw cron run {cron_job_id}

    取消 Cron:
      openclaw cron delete {cron_job_id}
    """))


# ── Onboard: 从零初始化新项目 ──────────────────────────────────────────────────

_KNOWN_TYPES = {
    "software": "代码/CLI 项目（src/, tests/, 构建配置）",
    "writing": "写作项目（chapters/, outline.md, characters/）",
    "video": "视频/媒体项目（scripts/, scenes/, storyboard/）",
    "research": "学术/研究项目（papers/, references/, notes/）",
    "generic": "通用项目（docs/, materials/, README）",
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
        (project / "outline.md").write_text("# 大纲\n\n", encoding="utf-8")
        (project / "characters" / "README.md").write_text("# 角色设定\n\n", encoding="utf-8")
        (project / "chapters" / ".gitkeep").touch()
    elif kind == "video":
        (project / "scripts").mkdir(exist_ok=True)
        (project / "scenes").mkdir(exist_ok=True)
        (project / "storyboard").mkdir(exist_ok=True)
        (project / "assets").mkdir(exist_ok=True)
        (project / "scripts" / "outline.md").write_text("# 脚本大纲\n\n", encoding="utf-8")
        (project / "scenes" / ".gitkeep").touch()
    elif kind == "research":
        (project / "papers").mkdir(exist_ok=True)
        (project / "references").mkdir(exist_ok=True)
        (project / "notes").mkdir(exist_ok=True)
        (project / "outline.md").write_text("# 研究大纲\n\n", encoding="utf-8")
        (project / "references" / "README.md").write_text("# 参考文献\n\n", encoding="utf-8")
    else:
        (project / "docs").mkdir(exist_ok=True)
        (project / "materials").mkdir(exist_ok=True)
        (project / "docs" / "README.md").write_text("# 文档\n\n", encoding="utf-8")


def cmd_onboard(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    model: str = "MODEL",
) -> None:
    step("🆕 从零初始化新项目")

    if project.exists() and any(project.iterdir()):
        warn(f"目录 {project} 非空，视为已有项目。使用 adopt 模式更合适。")
        print(f"  python init.py adopt {project}")
        sys.exit(1)

    # Step 1: pick project kind
    step("📂 选择项目类型")
    for key, desc in _KNOWN_TYPES.items():
        print(f"  {c(key, COLOR_GREEN):12} {desc}")
    print()
    kind = ask("项目类型（software / writing / video / research / generic）", "generic").strip().lower()
    if kind not in _KNOWN_TYPES:
        warn(f"未知类型 '{kind}'，使用 generic。")
        kind = "generic"

    # Step 2: confirm
    print(textwrap.dedent(f"""
    此向导帮助创建一个 AI-ready 的新项目结构。

    完成后会：
    1. 创建基础目录结构（按 {kind} 类型）
    2. 初始化 Git 仓库
    3. 配置 Autonomous Improvement Loop
    4. 启动 Cron

    项目目录: {project}
    项目类型: {kind}
    语言: {'中文' if language == 'zh' else 'English'}
    """))

    if ask("\n  继续?", "n").lower() != "y":
        print("取消。")
        sys.exit(0)

    # Step 3: scaffold
    step("🏗  创建项目结构")
    _scaffold_project(project, kind)
    ok(f"目录结构已创建（{kind}）")

    # Step 4: git
    if not (project / ".git").exists():
        run(["git", "init"], cwd=project)
        ok("Git 仓库已初始化")

    # Step 5: GitHub repo (optional)
    gh_remote = ask("\n  GitHub repo URL（可选，直接回车跳过）")
    if gh_remote:
        run(["git", "remote", "add", "origin", gh_remote], cwd=project)
        ok(f"Git remote 已设置: {gh_remote}")

    # Step 6: write config
    step("📝 写入 config.md")
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
    ok("config.md 已写入")

    # Step 7: init heartbeat
    step("📋 初始化 HEARTBEAT.md")
    init_queue_heartbeat(mode="bootstrap", language=language)
    ok("HEARTBEAT.md 已初始化（模式: bootstrap）")

    print(textwrap.dedent(f"""
    {c('✅ 新项目初始化完成!', COLOR_GREEN + COLOR_BOLD)}

    项目: {project.name}
    类型: {kind}
    目录: {project}

    下一步:
      python init.py adopt {project}  # 完成接管，启动 Cron

    查看队列:
      cat {HEARTBEAT}
    """))


# ── Status: 查看项目状态 ────────────────────────────────────────────────────────

def cmd_status(project: Path) -> None:
    step("📋 项目就绪状态")

    if not project.exists():
        fail(f"项目路径不存在: {project}")
        sys.exit(1)

    readiness = check_project_readiness(project)
    new_items = sum(1 for v in readiness.values() if not v)
    mode = "bootstrap" if new_items > 3 else "normal"

    repo = detect_github_repo(project)
    config = read_current_config()

    print(f"\n  项目: {project.name}")
    print(f"  路径: {project}")
    print(f"  GitHub: {repo or c('未配置', COLOR_YELLOW)}")
    print(f"  语言: {'中文' if config.get('project_language', 'zh') == 'zh' else 'English'}")
    print(f"  运行模式: {c(mode, COLOR_GREEN if mode == 'normal' else COLOR_YELLOW)}")
    print()
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} (缺失)")
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

        print(f"  队列待处理任务: {len(pending_rows)} 项")
        for num, kind, score, desc in pending_rows[:10]:
            print(f"    #{num} [{kind}/{score}] {desc}")
        if len(pending_rows) > 10:
            print(f"    ... 其余 {len(pending_rows) - 10} 项省略")

    # Cron status
    cron_id = config.get("cron_job_id") or detect_existing_cron()
    if cron_id:
        r = run(["openclaw", "cron", "list"], timeout=10)
        status_text = "active"
        if r.returncode == 0 and cron_id in r.stdout:
            status_text = c("active", COLOR_GREEN)
        print(f"\n  Cron Job: {cron_id} ({status_text})")
    else:
        warn("  Cron Job: 未检测到")

    print()


# ── Main entry point ────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Autonomous Improvement Loop 初始化向导",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            用法示例:

              # 接管已有项目（最常用）
              python init.py adopt ~/Projects/YOUR_PROJECT

              # 从零初始化新项目
              python init.py onboard ~/Projects/MyProject

              # 查看项目就绪状态
              python init.py status ~/Projects/YOUR_PROJECT

              # 完全交互式（自动检测所有信息）
              python init.py adopt
            """),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    adopt_p = sub.add_parser("adopt", help="接管已有项目")
    adopt_p.add_argument("project", nargs="?", type=Path)
    adopt_p.add_argument("--agent", help="OpenClaw Agent ID")
    adopt_p.add_argument("--chat-id", help="Telegram Chat ID")
    adopt_p.add_argument("--language", "--lang", "-l", default=None,
                         choices=["en", "zh"],
                         help="项目输出语言")
    adopt_p.add_argument("--model", "-m", default="YOUR_MODEL",
                         help="LLM model for cron sessions")
    adopt_p.add_argument("--force-new-cron", action="store_true",
                         help="强制新建 Cron Job（替换已有的）")
    adopt_p.set_defaults(func=cmd_adopt)

    onboard_p = sub.add_parser("onboard", help="从零初始化新项目")
    onboard_p.add_argument("project", nargs="?", type=Path)
    onboard_p.add_argument("--agent", help="OpenClaw Agent ID")
    onboard_p.add_argument("--chat-id", help="Telegram Chat ID")
    onboard_p.add_argument("--language", "--lang", "-l", default=None,
                          choices=["en", "zh"],
                          help="项目输出语言")
    onboard_p.add_argument("--model", "-m", default="YOUR_MODEL",
                          help="LLM model for cron sessions")
    onboard_p.set_defaults(func=cmd_onboard)

    status_p = sub.add_parser("status", help="查看项目就绪状态")
    status_p.add_argument("project", nargs="?", type=Path,
                          default=detect_project_path())
    status_p.set_defaults(func=cmd_status)

    args = parser.parse_args()

    # Auto-detect project path if not given
    if hasattr(args, "project") and args.project is None:
        detected = detect_project_path()
        if detected:
            print(f"自动检测到项目: {detected}")
            args.project = detected
        else:
            print("错误: 无法自动检测项目路径，请指定 --project 或在项目目录下运行。")
            print("\n在以下目录中未找到 git 仓库:")
            print("  ~/Projects/")
            print("  ~/projects/")
            print("  ~/Code/")
            print("\n请手动指定: python init.py adopt ~/Projects/YourProject")
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
        if args.project and args.project.exists():
            args.language = detect_project_language(args.project)
        else:
            args.language = DEFAULT_LANGUAGE

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
    except KeyboardInterrupt:
        print("\n\n取消。")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
