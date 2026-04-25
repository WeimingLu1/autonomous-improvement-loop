from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
import re

from .state import load_config


@dataclass
class PlannedTask:
    task_type: str
    source: str
    title: str
    context: str
    why_now: str
    scope: list[str]
    non_goals: list[str]
    relevant_files: list[str]
    execution_plan: list[str]
    acceptance_criteria: list[str]
    verification: list[str]
    risks: list[str]
    maintenance_tag: str = ""
    background: str = ""
    rollback: str = ""
    effort: str = "medium"


# Plugin registry for custom candidate generators
_PLUGIN_REGISTRY: list[callable] = []


def register_candidate_plugin(plugin_fn: callable) -> None:
    """Register a plugin function that yields candidate dicts.
    
    Plugin signature:  def my_plugin(project: Path, ctx: dict) -> list[dict]
    Each dict follows the same shape as _IMPROVE_CANDIDATES items.
    """
    _PLUGIN_REGISTRY.append(plugin_fn)


def _discover_and_load_dir_plugins(project: Path, ctx: dict) -> list[dict]:
    """Auto-discover and invoke plugins from .ail/plugins/ directory.
    
    Each .py file (except __init__.py) is loaded as a module.
    If it exports a `candidates(project, ctx) -> list[dict]` function,
    that function is called and its results returned.
    
    Loaded modules are NOT cached in sys.modules to allow re-loading
    from different project paths (multi-project support).
    """
    import importlib.util

    plugins_dir = project / ".ail" / "plugins"
    if not plugins_dir.is_dir():
        return []

    all_candidates = []
    for plugin_file in sorted(plugins_dir.glob("*.py")):
        if plugin_file.name == "__init__.py":
            continue
        module_name = f"_ail_plugin_{plugin_file.stem}_{project.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "candidates") and callable(module.candidates):
                result = module.candidates(project, ctx)
                if result:
                    all_candidates.extend(result)
        except Exception:
            # Fail silently — plugin loading errors should not crash the planner
            pass
    return all_candidates


def _load_plugins(project: Path, ctx: dict) -> list[dict]:
    """Load candidates from auto-discovered directory plugins and registered plugins."""
    # Auto-discover plugins from .ail/plugins/ directory (no caching)
    dir_candidates = _discover_and_load_dir_plugins(project, ctx)

    # Also call programmatically registered plugins
    reg_candidates = []
    for plugin_fn in _PLUGIN_REGISTRY:
        try:
            result = plugin_fn(project, ctx)
            if result:
                reg_candidates.extend(result)
        except Exception:
            pass  # Fail silently

    return dir_candidates + reg_candidates


def _count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return 0


def _get_quality_scores(project: Path) -> dict[str, int]:
    """Get quality scores for all scripts/ modules. Returns dict of module_name -> score."""
    try:
        from scripts.task_quality import score_all_modules
        return {r["module"]: r["score"] for r in score_all_modules(project)}
    except Exception:
        return {}


def _project_summary(project: Path) -> str:
    project_md = project / "PROJECT.md"
    if not project_md.exists():
        return f"Project: {project.name}"
    text = project_md.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def _changed_files_from_git(project: Path, since_days: int = 7) -> list[str]:
    """Return list of files changed in last N days via git diff --name-only."""
    try:
        since = f"--since='{since_days} days ago'"
        result = subprocess.run(
            ["git", "diff", "--name-only", since, "--", "."],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


def _read_project_context(project: Path) -> dict:
    """Read real project info for task planning."""
    scripts_dir = project / "scripts"
    tests_dir = project / "tests"

    # File names and line counts from scripts/
    script_files = {}
    if scripts_dir.exists():
        for f in sorted(scripts_dir.glob("*.py")):
            if f.name == "__init__.py":
                continue
            script_files[f.name] = _count_lines(f)

    # Last 5 git commit messages
    commits = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-10", "--no-decorate"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            commits = result.stdout.strip().split("\n")
    except Exception:
        commits = []

    # Test file names
    test_files = []
    if tests_dir.exists():
        for f in sorted(tests_dir.glob("test_*.py")):
            test_files.append(f.name)

    # Find function names in init.py for specific scope refs
    init_path = scripts_dir / "init.py"
    init_funcs = []
    if init_path.exists():
        text = init_path.read_text(encoding="utf-8", errors="ignore")
        # Match def cmd_<name> or def _cmd_<name>
        init_funcs = re.findall(r"^def (cmd_\w+)\(", text, re.MULTILINE)

    return {
        "project_summary": _project_summary(project),
        "script_files": script_files,
        "commits": commits,
        "test_files": test_files,
        "init_funcs": init_funcs,
        "quality_scores": _get_quality_scores(project),
        "changed_files": _changed_files_from_git(project),
    }


# ---------------------------------------------------------------------------
# Candidate pools — 15+ improve + 10+ idea, each highly differentiated
# ---------------------------------------------------------------------------

_IMPROVE_CANDIDATES: list[dict] = [
    {
        "title": "为 roadmap 命令流补齐集成测试覆盖",
        "background": "最近 commit 313d9dc 修复了 5 个 cron bug，包括 generate-next-task 和 git-log dedupe，说明命令流的核心逻辑已趋稳定，应该有完整测试覆盖来保证后续迭代不破坏已有行为。",
        "why_now": "test_cli_integration.py 存在但 coverage 不完整，关键路径 (a-plan -> a-trigger -> Done Log) 缺乏自动化验证。",
        "scope": ["tests/test_cli_integration.py", "scripts/init.py", "scripts/roadmap.py"],
        "rollback": "git revert tests/test_cli_integration.py",
        "effort": "medium",
        "non_goals": ["不覆盖所有边界条件", "不重写已有测试"],
        "relevant_files": ["tests/test_cli_integration.py"],
        "execution_plan": [
            "Step 1: 列出当前测试未覆盖的命令路径",
            "Step 2: 补充 a-plan 完整流程测试（生成 plan -> 写入 ROADMAP）",
            "Step 3: 补充 a-trigger 的 Done Log 写入测试",
            "Step 4: 补充 done_titles 去重行为的测试",
        ],
        "acceptance_criteria": [
            "test_cli_integration.py 中 a-plan 路径有测试覆盖",
            "test_cli_integration.py 中 a-trigger Done Log 写入有测试覆盖",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -m pytest tests/test_cli_integration.py -q"],
        "risks": ["测试依赖临时目录和 mock"],
    },
    {
        "title": "为 current task 和 plan 输出补齐 CLI 测试",
        "background": "最近 commit e537431 修复了完整 plan 文档输出，但 current task 与 plan 的 CLI 回显仍缺少聚焦测试。输出格式一旦回归，用户会第一时间受影响。",
        "why_now": "a-current 和 a-plan 是最常用命令，且刚经历输出层改动，需要尽快补上回归保护。",
        "scope": ["tests/test_cli_integration.py", "scripts/init.py:cmd_current", "scripts/init.py:cmd_plan"],
        "rollback": "git revert tests/test_cli_integration.py",
        "effort": "short",
        "non_goals": ["不扩展到 trigger 全链路", "不修改命令核心逻辑"],
        "relevant_files": ["tests/test_cli_integration.py", "scripts/init.py"],
        "execution_plan": [
            "Step 1: 为 a-plan 输出完整 plan doc 添加断言",
            "Step 2: 为 a-current 回显当前任务与完整 plan 添加断言",
            "Step 3: 校验输出包含 Goal / Execution Plan / Acceptance Criteria 等关键 section",
        ],
        "acceptance_criteria": [
            "a-plan 的 CLI 集成测试覆盖完整 plan 文档输出",
            "a-current 的 CLI 集成测试覆盖当前任务和完整 plan 输出",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -m pytest tests/test_cli_integration.py -q -k 'a_plan or a_current'"],
        "risks": ["输出带颜色时断言需避免过度依赖精确格式"],
    },
    {
        "title": "为 init.py 的 a-trigger 命令增加 Dry-run 模式，输出将要执行的操作但不实际执行",
        "background": "当前 a-trigger 一旦执行就会写 Done Log，没有预览机制，迭代风险高。最近 commit e537431 修改了 _print_plan_doc，但 trigger 本身的执行仍是直接写状态。",
        "why_now": "commit e537431 修复了 plan doc 截断问题，说明迭代在加速；此时若不加 dry-run，后续连续 trigger 改动会缺少安全网。",
        "scope": ["scripts/init.py:cmd_trigger", "scripts/init.py:cmd_stop"],
        "rollback": "git revert <commit> && python3 init.py a-plan --force",
        "effort": "short",
        "non_goals": ["不改变 Done Log 写入逻辑", "不新增 alias"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 在 cmd_trigger 函数签名中添加 dry_run: bool = False 参数",
            "Step 2: 在函数入口处 if dry_run: 输出待执行操作并 return",
            "Step 3: 在 a-trigger 命令解析部分加入 --dry-run / -n 选项",
            "Step 4: 测试: a-trigger --dry-run 应只输出不写 Done Log",
        ],
        "acceptance_criteria": [
            "a-trigger --dry-run 输出计划内容且不写入 Done Log",
            "a-trigger 不带参数行为与之前完全一致",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -c \"from scripts.init import cmd_trigger; print('import ok')\""],
        "risks": ["不影响现有 cron trigger 行为"],
    },
    {
        "title": "为 task_planner.py 增加基于最近 git diff 的自适应候选生成，让任务反映最新代码变化",
        "background": "当前 task_planner.py 只有静态候选池，无法感知代码最近改动。commit bd01227 引入了 done log dedupe 逻辑，但 task_planner 不知道这个变化。",
        "why_now": "每次迭代后代码状态在变，静态候选池会逐渐与实际项目脱节；已有 _read_project_context 但候选池未使用它。",
        "scope": ["scripts/task_planner.py:_read_project_context", "scripts/task_planner.py:_build_candidates"],
        "rollback": "git checkout scripts/task_planner.py.bak (如果备份过) 或 git revert",
        "effort": "medium",
        "non_goals": ["不完全替换静态候选池", "不修改 choose_next_task 接口"],
        "relevant_files": ["scripts/task_planner.py"],
        "execution_plan": [
            "Step 1: 扩展 _read_project_context 解析 git diff --stat 获取变更文件",
            "Step 2: 基于变更文件列表，在候选池前动态插入 1-2 条针对最新改动的 fixup 任务",
            "Step 3: 保持原有静态候选池作为 fallback",
        ],
        "acceptance_criteria": [
            "choose_next_task 能读取最近 3 个 commit 的变更文件",
            "动态生成的候选 title 不为空",
        ],
        "verification": ["python3 -c \"from scripts.task_planner import _read_project_context, choose_next_task; from scripts.roadmap import load_roadmap; from pathlib import Path; ctx = _read_project_context(Path('.')); print(list(ctx['script_files'].keys())[:3])\""],
        "risks": ["git diff 可能为空（全新仓库）"],
    },
    {
        "title": "为 CLI 增加 --json 输出格式，便于脚本解析",
        "background": "当前 a-current / a-plan / a-status 输出都是纯文本格式，外部脚本难以解析。ail 作为工具被其他自动化流程调用时需要结构化输出。",
        "why_now": "随着 ail 被集成到更大自动化系统中，纯文本输出已成为集成瓶颈，需要提供 --json 选项。",
        "scope": ["scripts/init.py:cmd_current", "scripts/init.py:cmd_plan", "scripts/init.py:add_cli_commands"],
        "rollback": "git revert 并删除 --json 相关分支",
        "effort": "medium",
        "non_goals": ["不改默认输出格式", "不重写整个 CLI 层"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 在 cmd_current 和 cmd_plan 中加入 --json flag",
            "Step 2: 使用内置 json 模块序列化关键字段输出",
            "Step 3: 测试: cmd_current --json 输出合法 JSON",
        ],
        "acceptance_criteria": [
            "a-current --json 输出合法 JSON 且包含 title/context/status",
            "a-plan --json 输出合法 JSON 且包含 execution_plan",
        ],
        "verification": ["python3 scripts/init.py a-current --json | python3 -c \"import sys,json; json.load(sys.stdin); print('valid json')\""],
        "risks": ["中文内容 JSON 序列化需要 ensure_ascii=False"],
    },
    {
        "title": "为 roadmap.py 的 load_roadmap 增加 schema 验证，对损坏的 ROADMAP.md 给出友好错误",
        "background": "当前 load_roadmap 对损坏的 ROADMAP.md 直接返回默认状态，不报告问题。如果 ROADMAP.md 被意外截断或格式破坏，用户不知道问题在哪。",
        "why_now": "ROADMAP.md 是 ail 的核心状态文件，一旦损坏整个循环都会受影响；需要早发现早修复。",
        "scope": ["scripts/roadmap.py:load_roadmap", "scripts/roadmap.py:_extract_current_task"],
        "rollback": "git revert scripts/roadmap.py",
        "effort": "short",
        "non_goals": ["不修复已损坏的 ROADMAP.md", "不改变状态数据结构"],
        "relevant_files": ["scripts/roadmap.py"],
        "execution_plan": [
            "Step 1: 在 load_roadmap 入口检查文件是否存在且非空",
            "Step 2: 检查必需表头行是否存在 (## Current Task, ## Rhythm State)",
            "Step 3: 检查 Rhythm State 的关键字段是否存在",
            "Step 4: 格式化错误信息并 raise ValueError",
        ],
        "acceptance_criteria": [
            "load_roadmap 对空文件 raise ValueError 并提示原因",
            "load_roadmap 对缺少表头的文件 raise ValueError 并提示缺少哪个表头",
        ],
        "verification": ["python3 -c \"from scripts.roadmap import load_roadmap; from pathlib import Path; import tempfile; p=Path(tempfile.mktemp()); p.write_text(''); load_roadmap(p)\" 2>&1 | grep -i error"],
        "risks": ["向后兼容：合法文件不应受影响"],
    },
    {
        "title": "为 a-status 命令增加最近 N 次任务执行结果的摘要输出",
        "background": "当前 a-status 只显示当前任务状态，不显示历史。最近 commit 313d9dc 引入了 done log dedupe，说明 history 日志已经存在但未被充分使用。",
        "why_now": "用户运行 a-status 时经常需要回顾最近做了什么，当前只能查看 ROADMAP.md 尾部或查看 git log。",
        "scope": ["scripts/init.py:cmd_status", "scripts/roadmap.py:append_done_log", "scripts/roadmap.py:_extract_done_log_block"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不修改 Done Log 格式", "不增加新的持久化结构"],
        "relevant_files": ["scripts/init.py", "scripts/roadmap.py"],
        "execution_plan": [
            "Step 1: 读取 ROADMAP.md 的 Done Log block",
            "Step 2: 解析最近 5 行历史记录",
            "Step 3: 在 cmd_status 输出中加入 最近任务摘要 小节",
        ],
        "acceptance_criteria": [
            "a-status 输出包含最近 5 个任务的 title 和 result",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-status 2>&1 | grep -c '最近'"],
        "risks": ["不破坏现有 status 格式"],
    },
    {
        "title": "为 project_md.py 修复 detect_tech_stack() 的 import 语句解析，只检测真实依赖",
        "background": "当前 detect_tech_stack() 用字符串包含检测，把注释里的 sqlalchemy/sqlite 也当成真实依赖。最近 commit e537431 说明文档工作在推进，项目理解需要准确。",
        "why_now": "PROJECT.md 的 tech_stack 部分显示错误依赖，影响外部对项目真实技术栈的理解。",
        "scope": ["scripts/project_md.py:detect_tech_stack"],
        "rollback": "git revert scripts/project_md.py",
        "effort": "short",
        "non_goals": ["不改变 project_md.py 其他函数", "不重写整个文件"],
        "relevant_files": ["scripts/project_md.py"],
        "execution_plan": [
            "Step 1: 用 ast.parse 解析每个 .py 文件的 import 语句",
            "Step 2: 构建真实 import 集合（排除 comment-only 的 import）",
            "Step 3: 对比当前 detect_tech_stack 的关键词列表，只保留真实导入的库",
        ],
        "acceptance_criteria": [
            "detect_tech_stack 不再把注释中的 sqlalchemy/sqlite 当依赖",
            "scripts/init.py 的 typer 依赖被正确识别",
        ],
        "verification": ["python3 -c \"from scripts.project_md import detect_tech_stack; from pathlib import Path; print(detect_tech_stack(Path('.'), 'software'))\""],
        "risks": ["ast.parse 可能对语法不完整的文件失败，需要 try/except"],
    },
    {
        "title": "为 init.py 的 a-current 命令增加 --verbose 模式，显示完整 plan 文档而非摘要",
        "background": "commit e537431 修复了 _print_plan_doc 的 300 字符截断，但 a-current 默认仍是简短输出。用户需要快速看当前任务详情的场景经常出现。",
        "why_now": "a-current 是用户最常用的命令之一，默认摘要长度经常不够用，但没有提供查看完整内容的选项。",
        "scope": ["scripts/init.py:cmd_current"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不改变默认输出格式", "不新增文件操作"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 在 cmd_current 添加 --verbose / -v flag",
            "Step 2: 当 -v 时读取并输出完整 plan_path 内容",
            "Step 3: 当无 -v 时保持现有摘要行为",
        ],
        "acceptance_criteria": [
            "a-current --verbose 输出 plan 完整内容（>300 字符时内容完整）",
            "a-current 不带参数行为不变",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-current --verbose 2>&1 | wc -c"],
        "risks": ["plan 文件不存在时 --verbose 应给出友好提示"],
    },
    {
        "title": "为 a-plan 命令增加 --force 参数，允许在已有 current task 时强制生成新任务",
        "background": "当前 a-plan 在已有 current task 时拒绝生成新任务，要求先完成或放弃当前任务。在快速探索场景下这限制了效率。",
        "why_now": "ail 被用于多任务探索时，用户经常需要先看看新 plan 长什么样再决定是否切换，这是一种合理的预览需求。",
        "scope": ["scripts/init.py:cmd_plan"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不改变默认安全行为", "不自动覆盖当前任务"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 在 cmd_plan 添加 --force flag",
            "Step 2: 当 --force 时跳过 current_task != None 的检查",
            "Step 3: 新 plan 仍然记录到 plans/ 但不更新 current task",
        ],
        "acceptance_criteria": [
            "a-plan --force 在有 current task 时仍能生成新 plan",
            "生成的 plan 写入 plans/ 目录",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-plan --force 2>&1 | head -5"],
        "risks": ["--force 生成的 plan 不会被执行链路自动消耗"],
    },
    {
        "title": "为 project_md.py 增加对 scripts/ 下各模块的 docstring 解析，生成核心模块说明",
        "background": "PROJECT.md 目前只列出技术栈，没有说明各模块职责划分。随着 init.py 超过 2000 行，新贡献者需要模块级别的理解。",
        "why_now": "ail 正准备被更广泛使用，项目自述文档需要包含架构概览，而不是只有依赖列表。",
        "scope": ["scripts/project_md.py:_read_modules", "scripts/project_md.py:render_project_md"],
        "rollback": "git revert scripts/project_md.py",
        "effort": "medium",
        "non_goals": ["不重写 PROJECT.md 格式", "不改变 project_md.py 导出函数签名"],
        "relevant_files": ["scripts/project_md.py", "scripts/init.py", "scripts/roadmap.py"],
        "execution_plan": [
            "Step 1: 遍历 scripts/ 下每个 .py 文件",
            "Step 2: 读取每个文件开头的 docstring 或前 3 行注释",
            "Step 3: 在 render_project_md 中加入 核心模块说明 小节",
        ],
        "acceptance_criteria": [
            "生成的 PROJECT.md 包含每个主要脚本的功能描述",
            "描述来自代码而非人工维护",
        ],
        "verification": ["python3 scripts/project_md.py --project . --output /tmp/pm.md && grep -c 'init.py' /tmp/pm.md"],
        "risks": ["没有 docstring 的文件此项留空"],
    },
    {
        "title": "为 init.py 的所有 CLI 命令补齐 --help 文档，确保每个命令都有清晰说明",
        "background": "当前 a-trigger / a-plan / a-current 等命令的 --help 输出信息不足或格式不一致。作为工具被集成时，--help 是第一手文档。",
        "why_now": "随着 ail 被集成到更自动化工作流中，--help 是脚本化调用时的唯一文档。",
        "scope": ["scripts/init.py:cmd_trigger", "scripts/init.py:cmd_plan", "scripts/init.py:cmd_current", "scripts/init.py:cmd_status"],
        "rollback": "git revert scripts/init.py",
        "effort": "medium",
        "non_goals": ["不改变命令行为", "不新增参数"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 遍历所有 cmd_* 函数",
            "Step 2: 补充每个 typer command 的 help= 参数",
            "Step 3: 确保示例用法 (epilog) 给出常见调用场景",
        ],
        "acceptance_criteria": [
            "每个命令 --help 输出包含: 功能说明、参数说明、示例",
            "帮助文本语言与当前语言一致 (zh)",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-plan --help | grep -c 'Plan'"],
        "risks": ["修改 help 文本不影响运行时行为"],
    },
    {
        "title": "为 a-trigger 增加执行超时机制，防止 cron 任务卡死",
        "background": "当前 a-trigger 没有超时控制，如果被 trigger 的命令（如 git push）卡住，整个 cron 流程都会被阻塞。",
        "why_now": "ail 在 VPS 上定时运行，如果某次任务执行卡死，会导致后续 cron 也无法触发，影响整个循环的可用性。",
        "scope": ["scripts/init.py:cmd_trigger"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不改变命令输出", "不为每个子命令设置不同超时"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 在 cmd_trigger 入口处设置默认超时 (如 300 秒)",
            "Step 2: 使用 signal.alarm 或 threading 机制实现超时中断",
            "Step 3: 超时时输出超时提示并以非零退出码结束",
        ],
        "acceptance_criteria": [
            "a-trigger 默认超时为 300 秒",
            "超时时输出 'Execution timed out'",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && timeout 1 python3 scripts/init.py a-trigger 2>&1 | tail -3"],
        "risks": ["超时机制在某些平台可能不生效 (Windows)"],
    },
    {
        "title": "为 project_md.py 加入 CLI 命令数统计，修复 typer 命令检测",
        "background": "当前 CLI 命令数检测用 @app.command( 但 typer 的装饰器是 @app.command()，导致命令数始终为 0。",
        "why_now": "PROJECT.md 显示 'CLI 命令数: 0' 是明显的错误，影响项目自述的准确性。",
        "scope": ["scripts/project_md.py:count_cli_commands"],
        "rollback": "git revert scripts/project_md.py",
        "effort": "short",
        "non_goals": ["不改变 project_md.py 其他部分", "不重写整个检测逻辑"],
        "relevant_files": ["scripts/project_md.py"],
        "execution_plan": [
            "Step 1: 同时检测 @app.command( 和 @app.command()",
            "Step 2: 对 init.py 内容进行两次正则匹配",
            "Step 3: 验证命令数 >= 10",
        ],
        "acceptance_criteria": [
            "count_cli_commands 对 init.py 返回 >= 10",
            "已知命令 (a-plan, a-trigger, a-current, a-status) 都被计入",
        ],
        "verification": ["python3 -c \"from scripts.project_md import count_cli_commands; from pathlib import Path; print(count_cli_commands(Path('.')))\""],
        "risks": ["正则可能匹配到注释中的 @app.command"],
    },
    {
        "title": "为 a-current 增加完整计划文档回显能力",
        "background": "commit e537431 修复了 plan doc 的 300 字符截断，但 a-current 默认仍输出摘要。用户需要快速查看完整当前任务内容。",
        "why_now": "当前任务的内容（scope、execution_plan、acceptance_criteria）需要完整展示而不是被截断。",
        "scope": ["scripts/init.py:cmd_current", "scripts/init.py:_print_plan_doc"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不改变 a-plan 的输出", "不新增文件操作"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 修改 _print_plan_doc 移除 300 字符截断",
            "Step 2: 确保 plan 文件不存在时输出友好提示",
            "Step 3: 验证 a-current 输出完整 plan 内容",
        ],
        "acceptance_criteria": [
            "a-current 输出当前任务的完整 plan 内容",
            "超过 300 字符的内容不被截断",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-current 2>&1 | wc -c"],
        "risks": ["长内容输出可能需要分页"],
    },
    {
        "title": "为 file_lock.py 增加锁超时机制，防止进程崩溃后锁无法释放",
        "background": "当前 file_lock.py 的锁没有超时机制，如果持锁进程被 kill -9，锁文件会残留导致后续所有操作失败。",
        "why_now": "ail 在 cron 环境下运行，如果某次执行被系统 kill，残留锁会导致整个 cron 循环永久卡死。",
        "scope": ["scripts/file_lock.py:FileLock", "scripts/file_lock.py:acquire"],
        "rollback": "git revert scripts/file_lock.py",
        "effort": "short",
        "non_goals": ["不改变锁的公平性", "不重写整个锁机制"],
        "relevant_files": ["scripts/file_lock.py"],
        "execution_plan": [
            "Step 1: 在 FileLock.__init__ 中加入 timeout 参数",
            "Step 2: 在 acquire 中记录加锁时间戳",
            "Step 3: 在 acquire 中检查锁文件时间戳，若超过 timeout 则强制删除并重新获取",
        ],
        "acceptance_criteria": [
            "持锁进程被 kill -9 后，另一进程在 timeout 后能获取锁",
            "正常释放锁的行为不受影响",
        ],
        "verification": ["python3 -c \"from scripts.file_lock import FileLock; from pathlib import Path; import tempfile; with tempfile.TemporaryDirectory() as d: lock = FileLock(Path(d)/'test.lock', timeout=1); print('timeout param accepted')\""],
        "risks": ["强制删除他人持有的锁可能造成竞态"],
    },

    {
        "title": "为 scripts/ 下所有 subprocess.run 调用增加超时控制和异常处理",
        "background": "当前代码中多处使用 subprocess.run 但 timeout 参数不一致，部分调用缺少超时保护。进程挂起会导致 a-plan / a-trigger 等命令无响应。",
        "why_now": "ail 作为长期运行的 cron 服务，需要保证每个命令都在确定时间内完成，不能因为 git subprocess 挂起而卡死。",
        "scope": ["scripts/init.py", "scripts/cli.py", "scripts/task_planner.py", "scripts/plan_writer.py"],
        "rollback": "git revert",
        "effort": "small",
        "non_goals": ["不改变命令的输出行为", "不引入新的外部依赖"],
        "relevant_files": ["scripts/init.py", "scripts/cli.py", "scripts/task_planner.py"],
        "execution_plan": [
            "Step 1: 审计所有 subprocess.run 调用，记录当前的 timeout 设置",
            "Step 2: 统一将 timeout=10 作为默认值，关键调用设 timeout=30",
            "Step 3: 对 subprocess 调用包裹 try/except，处理 TimeoutExpired 和 OSError",
            "Step 4: 验证: 超时场景下命令返回友好错误而非挂起",
        ],
        "acceptance_criteria": [
            "所有 subprocess.run 调用都有 timeout 参数",
            "超时时返回 'Command timed out' 而非挂起",
            "测试覆盖超时路径",
        ],
        "verification": ["grep -n 'subprocess.run' scripts/*.py | grep -v timeout || echo 'all have timeout'"],
        "risks": ["增加 timeout 可能导致某些慢操作提前失败"],
    },
    {
        "title": "为 ail 增加 YAML 配置文件支持，替换散布在代码中的硬编码常量",
        "background": "当前 ail 的各种阈值（timeout=10, STICKY_THRESHOLD=3, git_since='90 days ago' 等）散布在多个文件中，修改需要改代码。",
        "why_now": "随着 ail 部署到不同环境，需要能不修改代码就调整参数。配置文件是最自然的方案。",
        "scope": ["scripts/state.py", ".ail/config.yaml (新增)", "scripts/init.py"],
        "rollback": "删除 config.yaml，代码回退",
        "effort": "medium",
        "non_goals": ["不改变现有命令的默认行为", "不引入新的 CLI 参数"],
        "relevant_files": ["scripts/state.py", "scripts/init.py", "scripts/task_planner.py"],
        "execution_plan": [
            "Step 1: 确定需要配置化的常量列表（timeout, thresholds, paths）",
            "Step 2: 创建 .ail/config.yaml 并用 PyYAML 读取",
            "Step 3: state.py 提供 Config dataclass，从 YAML 加载",
            "Step 4: 各模块使用 config.get() 而非硬编码值",
        ],
        "acceptance_criteria": [
            "config.yaml 存在时使用配置文件中的值",
            "config.yaml 不存在时使用硬编码默认值（向后兼容）",
            "python3 scripts/init.py a-status 显示当前配置来源",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -c 'from scripts.state import load_config; print(load_config())'"],
        "risks": ["YAML 格式错误可能导致启动失败"],
    },
    {
        "title": "为 a-plan 和 a-trigger 的 --dry-run 模式建立统一的标准化实现框架",
        "background": "a-trigger 已支持 --dry-run，但 a-plan 和其他命令没有。现有 dry-run 实现分散，没有统一框架。",
        "why_now": "用户需要在不实际执行的情况下预览 ail 的行为，dry-run 是提升用户体验的重要功能。",
        "scope": ["scripts/init.py", "scripts/cli.py", "scripts/cron.py"],
        "rollback": "git revert",
        "effort": "small",
        "non_goals": ["不改变实际执行路径的行为", "不为每个命令都强制加 dry-run"],
        "relevant_files": ["scripts/init.py", "scripts/cli.py"],
        "execution_plan": [
            "Step 1: 定义 DryRunMode 枚举（FULL / PLAN_ONLY / OFF）",
            "Step 2: 各命令的 cmd_* 函数接收 dry_run 参数",
            "Step 3: dry_run 模式下只打印将要执行的操作，不写文件/不触发 git",
            "Step 4: 验证: a-trigger --dry-run 输出符合预期",
        ],
        "acceptance_criteria": [
            "a-trigger --dry-run 不写 ROADMAP.md 或 git commit",
            "a-plan --dry-run 显示将要生成的任务但不写入 ROADMAP.md",
            "统一使用 DRY_RUN 环境变量也可启用 dry-run 模式",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-trigger --dry-run 2>&1 | head -5"],
        "risks": ["多个命令的 dry-run 行为需要保持一致"],
    },

]


_IDEA_CANDIDATES: list[dict] = [
    {
        "title": "审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块",
        "background": "init.py 当前 2024 行，已超过单文件可维护阈值。代码中 cmd_* 函数、_state_* 函数、cron 逻辑混杂在一起，难以定位和修改。",
        "why_now": "随着功能持续增加，每次改动都需要在 2024 行文件中找位置，效率低下且引入 bug 风险高。",
        "scope": ["scripts/init.py", "scripts/cli.py", "scripts/state.py", "scripts/cron.py"],
        "rollback": "git revert 并手动合并",
        "effort": "long",
        "non_goals": ["不改变任何命令的对外行为", "不修改 plan_writer / roadmap 等独立模块"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 创建 scripts/cli.py / scripts/state.py / scripts/cron.py 空文件",
            "Step 2: 将 cmd_* 相关函数移入 scripts/cli.py",
            "Step 3: 将 _state_* 和状态持久化相关移入 scripts/state.py",
            "Step 4: 将 cron trigger 逻辑移入 scripts/cron.py",
            "Step 5: init.py 只保留 typer app 创建和命令注册",
            "Step 6: 运行全部测试验证行为不变",
        ],
        "acceptance_criteria": [
            "python3 scripts/init.py a-plan 行为与拆分前完全一致",
            "python3 scripts/init.py a-trigger 行为与拆分前完全一致",
            "全部测试通过",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -m pytest tests/ -q"],
        "risks": ["拆分过程中可能引入 import 错误，需要逐阶段测试"],
    },
    {
        "title": "为项目增加性能基准测试，跟踪 a-plan / a-current 等命令的响应时间",
        "background": "ail 目前没有性能回归检测，每次 commit 不知道是否让常用命令变慢了。当 init.py 超过 2000 行后，性能更值得关注。",
        "why_now": "随着代码量增长，a-plan 需要读取 git log 和 ROADMAP，这些操作在 large repo 上可能变慢。",
        "scope": ["scripts/init.py:cmd_plan", "scripts/init.py:cmd_current", "scripts/init.py:cmd_status"],
        "rollback": "删除基准测试文件",
        "effort": "medium",
        "non_goals": ["不优化实际执行逻辑", "只做测量和记录"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 创建 benchmarks/ 目录",
            "Step 2: 编写 benchmark_a_plan.py / benchmark_a_current.py",
            "Step 3: 使用 time 模块或 subprocess 测量响应时间",
            "Step 4: 将基准写入 benchmarks/results.jsonl",
        ],
        "acceptance_criteria": [
            "benchmark 脚本能在 CI 或 cron 中独立运行",
            "结果格式为 JSONL，便于后续分析",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 benchmarks/benchmark_a_current.py 2>&1 | grep real"],
        "risks": ["性能测量结果受系统负载影响，需要多次取平均"],
    },
    {
        "title": "为 ail 增加插件机制，允许注册自定义任务候选生成器",
        "background": "当前 task_planner.py 的候选池是硬编码的，外部无法扩展。随着 ail 被不同团队使用，任务类型和优先级可能不同。",
        "why_now": "想让 ail 适配不同工作流（不只是软件项目改进），需要可插拔的任务候选架构。",
        "scope": ["scripts/task_planner.py:choose_next_task", "scripts/task_planner.py:_read_project_context"],
        "rollback": "git revert scripts/task_planner.py",
        "effort": "long",
        "non_goals": ["不改变默认候选池行为", "不重写 PlannedTask dataclass"],
        "relevant_files": ["scripts/task_planner.py"],
        "execution_plan": [
            "Step 1: 定义 PluginRegistry 类，支持注册候选生成函数",
            "Step 2: 在 choose_next_task 中，先调用内置候选池，再用插件扩展",
            "Step 3: 提供默认空插件目录 .ail/plugins/ 作为约定优于配置",
        ],
        "acceptance_criteria": [
            "已注册的插件函数能被 choose_next_task 调用",
            "默认情况下插件目录不存在不影响正常运行",
        ],
        "verification": ["python3 -c \"from scripts.task_planner import choose_next_task; from scripts.roadmap import load_roadmap; from pathlib import Path; print('import ok')\""],
        "risks": ["插件接口不稳定可能导致后续 breaking change"],
    },
    {
        "title": "为 ROADMAP.md 增加任务优先级标注，支持 P0/P1/P2 三级优先级",
        "background": "当前 ROADMAP.md 只有 current task 和 done log，没有优先级概念。所有任务平等，容易被低价值任务占满队列。",
        "why_now": "随着候选池扩大（20+ 条），需要一个机制来确保最高价值任务优先被执行。",
        "scope": ["scripts/roadmap.py:RoadmapState", "scripts/roadmap.py:CurrentTask", "scripts/roadmap.py:load_roadmap"],
        "rollback": "git revert scripts/roadmap.py",
        "effort": "medium",
        "non_goals": ["不改变 ROADMAP.md 基础格式", "不重写 load_roadmap/set_current_task 接口"],
        "relevant_files": ["scripts/roadmap.py"],
        "execution_plan": [
            "Step 1: 在 CurrentTask dataclass 中增加 priority: str = 'P1' 字段",
            "Step 2: 修改 ROADMAP.md 格式，在任务行增加 priority 列",
            "Step 3: 修改 load_roadmap 解析 priority 列",
            "Step 4: 修改 set_current_task 写入 priority",
        ],
        "acceptance_criteria": [
            "load_roadmap 能正确解析 ROADMAP.md 中的 P0/P1/P2 标注",
            "set_current_task 能将 priority 写入 ROADMAP.md",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -c \"from scripts.roadmap import load_roadmap, init_roadmap, set_current_task, CurrentTask; from pathlib import Path; import tempfile; p=Path(tempfile.mktemp(suffix='.md')); init_roadmap(p); set_current_task(p, CurrentTask('TASK-001','idea','pm','test','pending','2026-01-01',priority='P0'), '', 'idea', 0); print('priority support ok')\""],
        "risks": ["改变 ROADMAP.md 格式可能影响旧版本的 load_roadmap 兼容性"],
    },
    {
        "title": "为 a-plan 增加多任务规划模式，一次生成 N 个任务并排入队列",
        "background": "当前 a-plan 一次只生成一个任务。如果想一次性规划一整轮迭代（如 5 个任务），需要多次运行 a-plan。",
        "why_now": "在大型功能开发前，通常需要一口气规划多个任务，形成完整的开发路线图，而不是一个个单独触发。",
        "scope": ["scripts/init.py:cmd_plan", "scripts/task_planner.py:choose_next_task"],
        "rollback": "git revert scripts/init.py 和 scripts/task_planner.py",
        "effort": "medium",
        "non_goals": ["不改变单任务模式的默认行为", "不重写 choose_next_task 接口"],
        "relevant_files": ["scripts/init.py", "scripts/task_planner.py"],
        "execution_plan": [
            "Step 1: 在 cmd_plan 添加 --count / -n 参数",
            "Step 2: 循环调用 choose_next_task 并收集结果",
            "Step 3: 将 N 个 plan 写入 plans/ 目录，命名 TASK-NNN-1, TASK-NNN-2 ...",
            "Step 4: 只将第一个设为 current task，其余写入 queue 文件",
        ],
        "acceptance_criteria": [
            "a-plan --count 3 一次生成 3 个不同的 plan",
            "生成的 3 个 plan 写入 plans/ 且 title 各不相同",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-plan --count 2 2>&1 | head -10"],
        "risks": ["多任务模式下 done_titles 追踪需要更复杂的状态管理"],
    },
    {
        "title": "审视 init.py 中的硬编码字符串，将面向用户的错误/提示信息迁移到 i18n 配置",
        "background": "当前 ail 的用户面向文本（中文）硬编码在 init.py 中。如果要支持英文或其他语言，需要重写所有 print/ok/error 调用。",
        "why_now": "ail 正在被更广泛使用，部分用户可能需要英文界面。当前硬编码阻碍了多语言支持。",
        "scope": ["scripts/init.py", "scripts/i18n.py (新建)"],
        "rollback": "git revert 并删除 i18n.py",
        "effort": "long",
        "non_goals": ["不改变命令行为", "不迁移所有代码注释"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 创建 scripts/i18n.py，定义 messages 字典 (zh/en)",
            "Step 2: 将 init.py 中的 ok()/error()/echo() 消息参数化",
            "Step 3: 根据语言参数选择对应 messages",
        ],
        "acceptance_criteria": [
            "python3 scripts/init.py a-status (默认语言) 输出中文",
            "python3 scripts/init.py a-status --lang en 输出英文",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-status 2>&1 | grep -E '(当前|任务)'"],
        "risks": ["改动量大，可能影响现有测试中的输出匹配"],
    },
    {
        "title": "为 ail 增加完整 OpenAPI/Swagger 文档，供 API 集成使用",
        "background": "ail 的命令目前没有机器可读的 API 规范。当需要通过 HTTP API（而非 CLI）驱动 ail 时，需要 OpenAPI 规范。",
        "why_now": "ail 正在被集成到更大自动化平台，有些平台只接受 HTTP API 调用而非 CLI subprocess。",
        "scope": ["scripts/init.py (CLI 定义)", "docs/openapi.yaml (新建)"],
        "rollback": "删除 docs/openapi.yaml",
        "effort": "long",
        "non_goals": ["不实现 HTTP 服务器", "不改变 CLI 行为"],
        "relevant_files": ["scripts/init.py"],
        "execution_plan": [
            "Step 1: 分析 CLI 命令的参数和输出类型",
            "Step 2: 编写 docs/openapi.yaml，描述每个端点（对应每个 CLI 命令）",
            "Step 3: 使用 swagger-cli 验证规范正确性",
        ],
        "acceptance_criteria": [
            "openapi.yaml 通过 swagger-cli validate",
            "每个 CLI 命令都有对应的 OpenAPI path 定义",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && swagger-cli validate docs/openapi.yaml 2>&1 || echo 'swagger-cli not installed'"],
        "risks": ["CLI 参数和 OpenAPI path 语义不完全对应，需要设计映射层"],
    },
    {
        "title": "为 a-trigger 增加并发控制，防止同一项目上多个 trigger 同时执行",
        "background": "如果 cron 配置不当或外部系统同时调用 a-trigger，可能出现两个 trigger 进程同时运行，破坏 ROADMAP.md 状态一致性。",
        "why_now": "ail 在多节点环境下被使用时（如同一个项目在多台机器的 cron 中），需要 mutex 机制保证串行执行。",
        "scope": ["scripts/init.py:cmd_trigger", "scripts/file_lock.py:FileLock"],
        "rollback": "git revert scripts/init.py",
        "effort": "short",
        "non_goals": ["不改变 file_lock.py 的公开接口", "不引入数据库依赖"],
        "relevant_files": ["scripts/init.py", "scripts/file_lock.py"],
        "execution_plan": [
            "Step 1: 在 cmd_trigger 入口处用 FileLock 保护",
            "Step 2: 锁文件放在 .ail/ 目录下，命名 trigger.lock",
            "Step 3: 如果锁被持有，输出提示并以非零码退出",
        ],
        "acceptance_criteria": [
            "两个同时运行的 a-trigger 只有一个能执行，另一个被拒绝",
            "正常执行完成后锁自动释放",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && (python3 scripts/init.py a-trigger &); sleep 0.1; python3 scripts/init.py a-trigger 2>&1 | grep -i 'lock\\|busy\\|held'"],
        "risks": ["进程被 kill 时锁可能无法释放（可结合 file_lock.py 超时改进）"],
    },
    {
        "title": "为 project_md.py 增加变更日志生成器，从 git log 自动生成 CHANGELOG.md",
        "background": "当前项目没有 CHANGELOG，每次 release 需要人工整理 commit 历史。ail 自身就在做 git commit，应该能自我记录。",
        "why_now": "随着 ail 版本增多（当前 8.13.31），需要自动化变更日志来替代人工维护。",
        "scope": ["scripts/project_md.py", "CHANGELOG.md (生成)"],
        "rollback": "删除 CHANGELOG.md，git revert scripts/project_md.py",
        "effort": "medium",
        "non_goals": ["不改变 VERSION 文件格式", "不实现 semver 校验"],
        "relevant_files": ["scripts/project_md.py", "VERSION"],
        "execution_plan": [
            "Step 1: 读取 VERSION 文件获取当前版本",
            "Step 2: 解析 git log，从最新 tag 开始收集 commit",
            "Step 3: 按 commit message prefix (feat/fix/chore/docs) 分组",
            "Step 4: 输出 Markdown 格式到 CHANGELOG.md",
        ],
        "acceptance_criteria": [
            "生成的 CHANGELOG.md 包含最近 10 个 commit",
            "每个 commit 按 type 分组（Features / Bug Fixes / Chores）",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/project_md.py --project . --output /tmp/cl.md && grep -c 'fix\\|feat\\|chore' /tmp/cl.md"],
        "risks": ["commit message 格式不规范会导致分组不准确"],
    },
    {
        "title": "审视 scripts/ 下所有模块的导出函数，为每个公共 API 补充 type hint",
        "background": "当前 scripts/ 下模块大量使用动态类型，没有 type hint。roadmap.py 和 task_planner.py 在重构时容易因类型错误导致 bug。",
        "why_now": "随着 ail 团队扩大或外部贡献者参与，动态类型会成为代码审查和重构的障碍。",
        "scope": ["scripts/roadmap.py", "scripts/task_planner.py", "scripts/init.py", "scripts/plan_writer.py"],
        "rollback": "git revert 各自文件",
        "effort": "long",
        "non_goals": ["不改变函数实现逻辑", "不引入 mypy 严格模式检查"],
        "relevant_files": ["scripts/roadmap.py", "scripts/task_planner.py", "scripts/init.py", "scripts/plan_writer.py"],
        "execution_plan": [
            "Step 1: 在 roadmap.py 的所有函数和返回值上加 type hint",
            "Step 2: 在 task_planner.py 的 PlannedTask dataclass 和函数上加 type hint",
            "Step 3: 在 init.py 的 cmd_* 函数上加 typer 兼容的 type hint",
            "Step 4: 验证: mypy scripts/*.py --ignore-missing-imports 错误数不增加",
        ],
        "acceptance_criteria": [
            "所有函数签名有 type hint",
            "mypy 检查错误数不超过 baseline",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && pip install mypy > /dev/null 2>&1; python3 -m mypy scripts/roadmap.py --ignore-missing-imports 2>&1 | tail -3"],
        "risks": ["typer 装饰器与 type hint 可能存在兼容性问题"],
    },

    {
        "title": "为 ail 增加多项目联合管理模式，支持同时跟踪 N 个项目的改进队列",
        "background": "当前 ail 每次只能管理一个项目，用户有多个项目时需要启动多个 ail 实例或手动切换。",
        "why_now": "用户的 workspace 有多个 ail 管理的项目（ail 自身、量化策略项目等），需要统一视图。",
        "scope": ["scripts/init.py", "scripts/state.py", "scripts/multi_project.py (新增)"],
        "rollback": "git revert multi_project.py",
        "effort": "long",
        "non_goals": ["不改变单项目模式的任何行为", "不引入数据库依赖"],
        "relevant_files": ["scripts/init.py", "scripts/state.py"],
        "execution_plan": [
            "Step 1: 设计 multi_project.yaml 配置格式（项目路径 + 别名列表）",
            "Step 2: 新增 scripts/multi_project.py 处理项目注册和切换",
            "Step 3: a-status --all 显示所有注册项目的当前状态摘要",
            "Step 4: a-switch <alias> 切换当前活跃项目",
        ],
        "acceptance_criteria": [
            "单项目模式（无 multi_project.yaml）行为与当前完全一致",
            "a-status --all 列出所有项目及其当前任务",
            "a-switch 正确切换 .ail 目录引用",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 scripts/init.py a-status --all 2>&1 | head -10"],
        "risks": ["多项目状态隔离需要充分测试，防止状态泄露"],
    },
    {
        "title": "为 ail 增加任务执行超时守护机制，用独立 watchdog 进程防止 a-trigger 卡死",
        "background": "a-trigger 依赖 subprocess 执行任意代码，如果子进程陷入死循环，a-trigger 会永久挂起。",
        "why_now": "ail 作为 cron 服务必须保证每次触发都在有限时间内完成，不能因为任务代码 bug 而卡死整个循环。",
        "scope": ["scripts/cron.py", "scripts/trigger_guard.py (新增)", ".ail/trigger.lock"],
        "rollback": "git revert",
        "effort": "medium",
        "non_goals": ["不改变 a-trigger 的正常执行流程", "不引入额外守护进程的开机自启配置"],
        "relevant_files": ["scripts/cron.py", "scripts/file_lock.py"],
        "execution_plan": [
            "Step 1: 在 cron.py 中为 a-trigger subprocess 设置 timeout 参数",
            "Step 2: 增加 watchdog 逻辑：trigger 开始后计时，超时则 kill subprocess 并记录错误",
            "Step 3: 超时后自动在 PM Notes 中记录 'trigger timeout at HH:MM'",
            "Step 4: 验证: 用一个故意死循环的任务测试超时处理",
        ],
        "acceptance_criteria": [
            "a-trigger 执行超时时返回 'Trigger timed out after X seconds'",
            "超时后 trigger.lock 锁文件被正确清理",
            "超时不影响后续 cron 触发（下次仍可正常执行）",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && timeout 2 python3 scripts/init.py a-trigger --no-spawn 2>&1"],
        "risks": [" watchdog 进程本身不能卡死"],
    },
    {
        "title": "为 task_planner.py 增加基于代码质量评分的自适应候选生成器",
        "background": "当前候选池是静态的，无法根据项目当前状态（代码复杂度、测试覆盖率、技术债）动态调整优先级。",
        "why_now": "随着项目增长，某些模块的质量问题会变得突出，静态候选池无法及时响应这些变化。",
        "scope": ["scripts/task_planner.py", "scripts/task_quality.py (新增)"],
        "rollback": "git revert",
        "effort": "medium",
        "non_goals": ["不改变候选池的基本结构", "不引入大型静态分析工具"],
        "relevant_files": ["scripts/task_planner.py", "scripts/task_quality.py"],
        "execution_plan": [
            "Step 1: 新增 scripts/task_quality.py，分析各模块的 cyclomatic complexity 和行数",
            "Step 2: 在 _read_project_context 中增加 quality_score 字段",
            "Step 3: 在 _pick_from_pool 时参考 quality_score 优先选择高复杂度模块相关的任务",
            "Step 4: 验证: 拆分大模块后，拆分任务不再被优先推荐",
        ],
        "acceptance_criteria": [
            "task_quality.py 能对 scripts/ 下各模块评分",
            "高复杂度模块（大文件、长函数）的相关任务优先级提升",
            "所有现有测试继续通过",
        ],
	        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -c \"from scripts.task_quality import score_module; print(score_module('cli.py'))\""],
        "risks": ["质量评分算法需要调优，初始实现可能不准确"],
    },

]


# ---------------------------------------------------------------------------
# Maintenance pool — activated after a PM idea/feature task completes
# ---------------------------------------------------------------------------

_MAINTENANCE_CANDIDATES: list[dict] = [
    {
        "title": "补充单元测试覆盖，提升关键函数的测试用例数量",
        "task_type": "maintenance",
        "maintenance_tag": "testing",
        "why_now": "测试覆盖率是软件质量的基础保障",
        "scope": ["tests/", "scripts/"],
    },
    {
        "title": "补充集成测试覆盖，验证模块间交互",
        "task_type": "maintenance",
        "maintenance_tag": "testing",
        "why_now": "单元测试覆盖之外，关键路径需要集成测试验证",
        "scope": ["tests/", "scripts/"],
    },
    {
        "title": "更新项目依赖版本，检查安全更新",
        "task_type": "maintenance",
        "maintenance_tag": "deps",
        "why_now": "依赖老化是安全漏洞的主要来源之一",
        "scope": ["requirements.txt", "pyproject.toml", "scripts/"],
    },
    {
        "title": "进行安全漏洞审计，检查常见安全风险",
        "task_type": "maintenance",
        "maintenance_tag": "security",
        "why_now": "在上线前发现安全问题比事后修复代价低得多",
        "scope": ["scripts/", "tests/"],
    },
    {
        "title": "提升代码可读性，重命名不清晰的变量和函数",
        "task_type": "maintenance",
        "maintenance_tag": "readability",
        "why_now": "代码可读性直接影响后续维护效率",
        "scope": ["scripts/"],
    },
    {
        "title": "完善错误处理，为核心函数添加异常处理",
        "task_type": "maintenance",
        "maintenance_tag": "error-handling",
        "why_now": "缺少错误处理的生产环境会难以调试",
        "scope": ["scripts/", "tests/"],
    },
    {
        "title": "完善日志语句，提升可调试性",
        "task_type": "maintenance",
        "maintenance_tag": "logging",
        "why_now": "可调试性差的系统在出问题的时候难以定位根因",
        "scope": ["scripts/"],
    },
    {
        "title": "进行性能 profiling，识别并优化性能瓶颈",
        "task_type": "maintenance",
        "maintenance_tag": "performance",
        "why_now": "性能瓶颈影响用户体验和资源成本",
        "scope": ["scripts/", "tests/"],
    },
    {
        "title": "更新项目文档，确保 README 和 CHANGELOG 最新",
        "task_type": "maintenance",
        "maintenance_tag": "docs",
        "why_now": "文档过时会导致贡献者门槛变高",
        "scope": ["README.md", "docs/"],
    },
    {
        "title": "清理无用代码和文件，减少技术债务",
        "task_type": "maintenance",
        "maintenance_tag": "cleanup",
        "why_now": "无用代码会累积技术债务，拖慢后续开发",
        "scope": ["scripts/", "tests/"],
    },
    {
        "title": "修复已知的边界 case，提升鲁棒性",
        "task_type": "maintenance",
        "maintenance_tag": "bug",
        "why_now": "已知的边界 case 不修复会影响系统稳定性",
        "scope": ["scripts/", "tests/"],
    },
    {
        "title": "提升配置灵活性，减少硬编码",
        "task_type": "maintenance",
        "maintenance_tag": "config",
        "why_now": "硬编码会降低系统的灵活性",
        "scope": ["scripts/", ".ail/config.md"],
    },
    {
        "title": "代码重复检测和消除，提升复用性",
        "task_type": "maintenance",
        "maintenance_tag": "refactor",
        "why_now": "重复代码增加维护成本，容易在修改时遗漏",
        "scope": ["scripts/"],
    },
    {
        "title": "完善项目可复现性验证，确保构建步骤可重复",
        "task_type": "maintenance",
        "maintenance_tag": "reproducibility",
        "why_now": "构建步骤不可复现会影响团队协作效率",
        "scope": ["scripts/", "tests/", "README.md"],
    },
    {
        "title": "补充横向移动工具脚本，提升日常开发效率",
        "task_type": "maintenance",
        "maintenance_tag": "tooling",
        "why_now": "好的工具可以显著减少日常重复劳动",
        "scope": ["scripts/"],
    },
]

def _build_maintenance_candidates(anchor_title: str, remaining: int) -> list[dict]:
    """Build maintenance tasks dynamically so title-based dedupe does not disable them forever."""
    anchor = anchor_title.strip() or "最近完成的 feature"
    regression = {
        "title": f"回归验证并修复：{anchor}",
        "maintenance_tag": "regression",
        "background": f"刚完成 feature：{anchor}，需要立即验证没有引入回归。",
        "why_now": "feature task 完成后必须确认代码仍然健康，这是交付标准的一部分。",
        "scope": ["scripts/", "tests/"],
        "non_goals": ["不进行大规模重构", "不扩展功能范围"],
        "relevant_files": ["tests/", "scripts/"],
        "execution_plan": [
            "Step 1: 运行全量测试 python3 -m pytest tests/ -q",
            "Step 2: 如有失败，在当前 task 内定位并修复",
            "Step 3: 修复后再次运行测试确认全部通过",
            "Step 4: 如有 bug 修复，另起 commit 记录",
        ],
        "acceptance_criteria": [
            "全量测试通过",
            f"围绕『{anchor}』未引入新的回归",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -m pytest tests/ -q 2>&1 | tail -3"],
        "risks": ["如测试本身就有 bug，修复优先级最高"],
    }
    docs = {
        "title": f"补测试与文档：{anchor}",
        "maintenance_tag": "testing",
        "background": f"刚完成 feature：{anchor}，需要补上相应的测试和文档。",
        "why_now": "没有测试覆盖的 feature 等同于不存在；文档缺失会拖累后续维护。",
        "scope": ["tests/", "docs/", "README.md"],
        "non_goals": ["不重写已有测试", "不做大范围文档重构"],
        "relevant_files": ["tests/test_cli_integration.py", "docs/superpowers/"],
        "execution_plan": [
            "Step 1: 找出上一个 feature 新增/修改的文件",
            "Step 2: 为每个新文件或关键函数补充至少 1 个测试用例",
            "Step 3: 检查 docs/ 目录是否有对应文档更新需求",
            "Step 4: 如有新增测试，运行确认通过",
        ],
        "acceptance_criteria": [
            f"围绕『{anchor}』新增了可持续的测试/文档资产",
            "全量测试仍然通过",
        ],
        "verification": ["cd /Users/weiminglu/Projects/autonomous-improvement-loop && python3 -m pytest tests/ -q 2>&1 | tail -3"],
        "risks": ["测试桩不好写时优先写集成测试而非单元测试"],
    }
    return [regression] if remaining >= 2 else [docs]


# ---------------------------------------------------------------------------
# Selection state
# ---------------------------------------------------------------------------

_SELECTION_STATE: dict[str, int] = {}


def _selection_key(project: Path, roadmap, done_titles: set[str]) -> str:
    next_type = getattr(roadmap, "next_default_type", "idea")
    improves_since = getattr(roadmap, "improves_since_last_idea", 0)
    # done_titles is used for filtering only; the hash omits it to keep
    # the selection state stable across iterations within a planning batch.
    payload = "|".join(
        [
            str(project.resolve()),
            next_type,
            str(improves_since),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _pick_from_pool(pool: list[PlannedTask], key: str, quality_scores: dict[str, int] | None = None) -> PlannedTask | None:
    if not pool:
        return None
    # Sort by quality score priority (higher = more urgent) when available
    if quality_scores:
        def quality_priority(t: PlannedTask) -> int:
            score = 0
            # Check scope files for module references
            for ref in getattr(t, "relevant_files", []):
                for fname, qs in quality_scores.items():
                    if fname in ref:
                        score = max(score, qs)
            # Also check scope strings directly
            for ref in getattr(t, "scope", []):
                for fname, qs in quality_scores.items():
                    if fname in str(ref):
                        score = max(score, qs)
            return score
        pool = sorted(pool, key=quality_priority, reverse=True)
    offset = _SELECTION_STATE.get(key, 0) % len(pool)
    _SELECTION_STATE[key] = offset + 1
    return pool[offset]


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def get_seed_task(project: Path, mode: str, language: str) -> PlannedTask:
    """Return the initial task used by onboard/adopt seed_queue.

    Historically seed_queue delegated to cmd_plan(force=True), which selected
    the next PM task from the default rhythm state. During module split, the
    call site was converted to import get_seed_task(), but that helper was not
    migrated, breaking onboard/adopt with ImportError.

    mode is currently informational only; the initial task follows the same
    planner selection as the first PM planning cycle.
    """
    from scripts.roadmap import RoadmapState

    roadmap = RoadmapState(
        current_task=None,
        next_default_type="idea",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )
    task, _ = choose_next_task(project, roadmap, set(), language, forbidden_titles=set())
    return task


def _done_log_title_counts(project: Path) -> dict[str, int]:
    """Return title -> count for all entries in Done Log."""
    roadmap_path = project / ".ail" / "ROADMAP.md"
    if not roadmap_path.exists():
        return {}
    text = roadmap_path.read_text(encoding="utf-8")
    done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", text, re.IGNORECASE)
    if not done_log_match:
        return {}
    counts: dict[str, int] = {}
    for line in done_log_match.group(1).splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 7 and cells[1].startswith("TASK-"):
            title = cells[4]
            counts[title] = counts.get(title, 0) + 1
    return counts


def _sticky_done_titles(project: Path, threshold: int = 3) -> set[str]:
    """Return titles from Done Log that appeared >= threshold times (stuck tasks)."""
    return {title for title, count in _done_log_title_counts(project).items() if count >= threshold}


def _maintenance_tag_versions(done_log_entries: list[dict]) -> dict[str, int]:
    """Parse Done Log entries and return {tag: version_count} mapping.

    version = number of times this tag has appeared in Done Log.
    So if 'security' appears 2 times, the next security task gets v3.
    """
    counts: dict[str, int] = {}
    for entry in done_log_entries:
        tag = entry.get("tag", "")
        if tag:
            counts[tag] = counts.get(tag, 0) + 1
    return counts  # {'security': 2, 'testing': 1}


def _maintenance_candidate_title(candidate: dict, version: int) -> str:
    """Generate maintenance task title with version suffix.

    version=1 → original title (no suffix)
    version>=2 → title + " v{version}"
    e.g. "进行安全漏洞审计" → "进行安全漏洞审计 v2"
    """
    if version <= 1:
        return candidate["title"]
    return f"{candidate['title']} v{version}"


def _dynamic_scope_for_candidate(candidate: dict, changed_files: list[str]) -> list[str]:
    """Generate dynamic scope based on changed files and maintenance_tag.

    Returns a focused list of files relevant to the candidate's maintenance_tag,
    or a fallback if no changed files are available.
    """
    tag = candidate.get("maintenance_tag", "")
    if not changed_files:
        return candidate.get("scope", ["scripts/"])

    # Filter to relevant changed files based on tag
    if tag == "security":
        relevant = [f for f in changed_files if f.startswith(("scripts/", "tests/"))]
    elif tag == "testing":
        relevant = [f for f in changed_files if "test" in f or f.startswith("tests/")]
    elif tag == "docs":
        relevant = [f for f in changed_files if f.endswith(".md") or "docs" in f]
    elif tag == "performance":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    elif tag == "cleanup":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    elif tag == "readability":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    elif tag == "error-handling":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    elif tag == "logging":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    elif tag == "deps":
        relevant = [f for f in changed_files if any(f.endswith(ext) for ext in (".txt", ".toml", ".cfg", "pyproject.toml", "requirements.txt"))]
    elif tag == "bug":
        relevant = [f for f in changed_files if f.startswith(("scripts/", "tests/"))]
    elif tag == "regression":
        relevant = [f for f in changed_files if f.startswith(("scripts/", "tests/"))]
    elif tag == "testing-docs":
        relevant = changed_files[:5]
    else:
        relevant = changed_files[:5]  # fallback: first 5 changed files

    return relevant[:5] if relevant else candidate.get("scope", ["scripts/"])


def _plan_to_planned_task(plan) -> PlannedTask:
    """Convert an LLM-generated PMPlan to a PlannedTask.
    
    PMPlan fields map to PlannedTask fields as follows:
    - goal: appended to context since both PMPlan.context and PlannedTask.context exist
    - maintenance_tag: PMPlan-specific, dropped (PlannedTask has no equivalent)
    - source: hardcoded to 'llm'
    - verification: mapped from plan.verification
    """
    extra_context = f"\n\nGoal: {plan.goal}" if plan.goal else ""
    context = (plan.context or "") + extra_context
    return PlannedTask(
        title=plan.title,
        task_type=plan.task_type,
        source="llm",
        effort=plan.effort,
        context=context,
        why_now=plan.why_now,
        scope=plan.scope if plan.scope else [],
        non_goals=plan.non_goals if plan.non_goals else [],
        relevant_files=plan.relevant_files if plan.relevant_files else [],
        execution_plan=plan.execution_plan if plan.execution_plan else [],
        acceptance_criteria=plan.acceptance_criteria if plan.acceptance_criteria else [],
        verification=plan.verification if plan.verification else [],
        risks=plan.risks,
        maintenance_tag="",
        background=plan.background,
        rollback=plan.rollback,
    )


def choose_next_task(
    project: Path,
    roadmap,
    done_titles: set[str],
    language: str,
    forbidden_titles: set[str] | None = None,
    use_llm: bool | None = None,
) -> tuple[PlannedTask, bool]:
    """Choose the next task based on roadmap rhythm and done titles.
    
    Returns (planned_task, consumed_maintenance_slot).
    consumed_maintenance_slot is True when a maintenance task was chosen
    (post_feature_maintenance_remaining was > 0 and we drew from that pool).
    
    When use_llm is True (or auto-detected from MINIMAX_API_KEY), the LLM
    is consulted first to generate a contextualised plan before falling
    back to the static candidate pool.
    """
    from scripts.config import load_config

    # Maintenance mode: skip LLM, use pool-based candidates
    maintenance_mode = getattr(roadmap, "maintenance_mode", False)

    # Auto-detect LLM availability (skip if maintenance mode is on)
    if use_llm is None:
        use_llm = bool(os.environ.get("MINIMAX_API_KEY", "").strip())
    if maintenance_mode:
        use_llm = False

    if use_llm:
        from scripts.llm_client import generate_pm_plan as llm_generate
        try:
            raw_plan = llm_generate(project, language)
            return _plan_to_planned_task(raw_plan), False
        except Exception:
            # Fallback to pool on LLM failure
            pass

    cfg = load_config()
    ctx = _read_project_context(project)

    # Build full candidate list
    improve_pool = [_make_task("improve", c, ctx) for c in _IMPROVE_CANDIDATES]
    idea_pool = [_make_task("idea", c, ctx) for c in _IDEA_CANDIDATES]


    # Extend from plugins
    plugin_improve = []
    plugin_idea = []
    for c in _load_plugins(project, ctx):
        task_type = c.get("task_type", "improve")
        if task_type == "idea":
            plugin_idea.append(c)
        else:
            plugin_improve.append(c)
    improve_pool.extend(_make_task("improve", c, ctx) for c in plugin_improve)
    idea_pool.extend(_make_task("idea", c, ctx) for c in plugin_idea)



    # Decide which pool to draw from based on rhythm state
    next_type = getattr(roadmap, "next_default_type", "idea")
    improves_since = getattr(roadmap, "improves_since_last_idea", 0)
    maintenance_remaining = getattr(roadmap, "post_feature_maintenance_remaining", 0)
    maintenance_anchor_title = getattr(roadmap, "maintenance_anchor_title", "")

    if maintenance_mode:
        # Build maintenance pool with versioned titles based on tag history.
        # Import needed functions from roadmap (lazy import to avoid circular dependency).
        from scripts.roadmap import _extract_done_log_block, _parse_done_log_entries

        # Read Done Log entries to get tag version counts
        # Build path from project since roadmap is RoadmapState object (not text)
        roadmap_path = project / ".ail" / "ROADMAP.md"
        done_log_block = _extract_done_log_block(roadmap_path.read_text(encoding="utf-8"))
        done_entries = _parse_done_log_entries(done_log_block)
        tag_versions = _maintenance_tag_versions(done_entries)

        changed_files = ctx.get("changed_files", [])
        maintenance_pool = []
        for c in _MAINTENANCE_CANDIDATES:
            task = _make_task("maintenance", c, ctx)
            tag = c.get("maintenance_tag", "")
            version = tag_versions.get(tag, 0) + 1  # next version number
            task.title = _maintenance_candidate_title(c, version)
            # Inject dynamic scope based on changed files
            task.scope = _dynamic_scope_for_candidate(c, changed_files)
            maintenance_pool.append(task)

        primary_pool = maintenance_pool
        fallback_pool = improve_pool
    elif maintenance_remaining > 0:
        # Force maintenance pool using titles anchored to the triggering feature.
        primary_pool = [_make_task("improve", c, ctx) for c in _build_maintenance_candidates(maintenance_anchor_title, maintenance_remaining)]
        fallback_pool = improve_pool
    elif next_type == "idea" or improves_since >= 3:
        primary_pool = idea_pool
        fallback_pool = improve_pool
    else:
        primary_pool = improve_pool
        fallback_pool = idea_pool

    forbidden_titles = forbidden_titles or set()
    primary_available = [candidate for candidate in primary_pool if candidate.title not in done_titles and candidate.title not in forbidden_titles]
    fallback_available = [candidate for candidate in fallback_pool if candidate.title not in done_titles and candidate.title not in forbidden_titles]

    selection_key = _selection_key(project, roadmap, done_titles)
    consumed = maintenance_remaining > 0
    quality_scores = ctx.get("quality_scores") or {}
    candidate = _pick_from_pool(primary_available, selection_key, quality_scores)
    if candidate is not None:
        return candidate, consumed

    candidate = _pick_from_pool(fallback_available, f"{selection_key}:fallback", quality_scores)
    if candidate is not None:
        return candidate, consumed

    # All candidates exhausted in both pools — clear done_titles and retry.
    # Titles appearing >= STICKY_THRESHOLD times in Done Log are excluded from retry
    # to prevent a repeated task from being selected again.
    # Additionally, any title appearing >= 2 times in Done Log (even if just marked
    # as "pass" without real code) is permanently excluded — a second Done Log
    # entry strongly indicates the work was either done elsewhere or skipped.
    # NOTE: forbidden_titles is NOT applied during retry because done_titles
    # already contains the genuinely done titles; clearing done_titles entries
    # that are candidates allows the system to cycle through tasks.
    STICKY_THRESHOLD = cfg['sticky_threshold']
    sticky_titles: set[str] = _sticky_done_titles(project, STICKY_THRESHOLD)
    # Super-sticky: titles appearing >= 2 times in Done Log are blocked on retry.
    # These are tasks that were marked done more than once, indicating either
    # duplicate passes or skipped executions — not actual completions.
    all_done_counts = _done_log_title_counts(project)
    super_sticky_titles: set[str] = {t for t, c in all_done_counts.items() if c >= 2}
    primary_titles = {c.title for c in primary_pool}
    fallback_titles = {c.title for c in fallback_pool}
    all_pool_titles = primary_titles | fallback_titles
    cleared_titles = done_titles & all_pool_titles
    if cleared_titles:
        for title in cleared_titles:
            done_titles.discard(title)
        # Apply BOTH sticky_titles (>= threshold) AND super_sticky_titles (>= 2)
        blocked_titles = sticky_titles | super_sticky_titles
        primary_available = [c for c in primary_pool if c.title not in done_titles and c.title not in blocked_titles]
        fallback_available = [c for c in fallback_pool if c.title not in done_titles and c.title not in blocked_titles]
        candidate = _pick_from_pool(primary_available, selection_key, quality_scores)
        if candidate is not None:
            return candidate, consumed
        candidate = _pick_from_pool(fallback_available, f"{selection_key}:fallback", quality_scores)
        if candidate is not None:
            return candidate, consumed

    raise ValueError("No unique task title available")


def _make_task(task_type: str, candidate: dict, ctx: dict) -> PlannedTask:
    """Build a PlannedTask from a candidate dict, injecting real project context."""
    commits = ctx["commits"]
    recent = commits[:3] if commits else []
    recent_str = "\n".join(recent) if recent else "(无最近 commit)"

    # Inject real context into the candidate
    file_list = ", ".join(
        f"{name}({lines}行)" for name, lines in sorted(ctx["script_files"].items())
    ) if ctx["script_files"] else "(无文件)"

    enriched_context = (
        f"项目摘要: {ctx['project_summary']}\n\n"
        f"最近提交:\n{recent_str}\n\n"
        f"当前 scripts/ 目录:\n{file_list}\n\n"
        f"已有测试文件: {', '.join(ctx['test_files'])}"
    )

    return PlannedTask(
        task_type=task_type,
        source="pm",
        title=candidate["title"],
        context=enriched_context,
        why_now=candidate["why_now"],
        scope=candidate["scope"],
        non_goals=candidate.get("non_goals", []),
        relevant_files=candidate.get("relevant_files", []),
        execution_plan=candidate.get("execution_plan", []),
        acceptance_criteria=candidate.get("acceptance_criteria", []),
        verification=candidate.get("verification", []),
        risks=candidate.get("risks", []),
        maintenance_tag=candidate.get("maintenance_tag", ""),
        background=candidate.get("background", ""),
        rollback=candidate.get("rollback", ""),
        effort=candidate.get("effort", "medium"),
    )
