"""Prompts for LLM-powered PM plan generation."""
from pathlib import Path

def build_plan_prompt(project: Path, language: str) -> str:
    roadmap_text = _read_if_exists(project / ".ail" / "ROADMAP.md")
    project_md = _read_if_exists(project / "PROJECT.md")
    recent_commits = _git_recent_commits(project)
    scripts_list = _list_scripts(project)
    done_log = _read_done_log(project)

    context = f"""## Project Context

### ROADMAP.md (current state)
{roadmap_text or '(no ROADMAP.md)'}

### PROJECT.md
{project_md or '(no PROJECT.md)'}

### Recent Git Commits
{recent_commits or '(no git history)'}

### scripts/ Directory
{scripts_list}

### Done Log (recent completed tasks)
{done_log}
"""
    return f"""{context}

## Your Task
Analyze the project above and generate ONE PM task plan in JSON format.

The task should be:
- Specific and actionable (not generic "improve code quality")
- Relevant to the project's current state and recent history
- Achievable in one work session

Output ONLY valid JSON (no markdown fences, no commentary), with this schema:
{{
  "title": "Short Chinese title for the task",
  "task_type": "improve",
  "effort": "short|medium|long",
  "background": "Why this task exists",
  "goal": "What completing this task achieves",
  "context": "What you know about the project",
  "scope": ["file1.py", "file2.py"],
  "non_goals": ["What this task does NOT cover"],
  "relevant_files": ["files to look at or modify"],
  "execution_plan": ["Step 1: ...", "Step 2: ..."],
  "acceptance_criteria": ["Criterion 1", "Criterion 2"],
  "why_now": "Why this task should be done now",
  "risks": "Potential risks or concerns",
  "rollback": "How to revert if needed",
  "verification": ["bash command to verify the task was done successfully (e.g. 'python3 -m pytest tests/ -q')"]
}}
"""

def build_bug_finding_prompt(project: Path, language: str, recent_diff: str = "") -> str:
    """Maintenance-mode bug finding: PM reads latest code and finds real bugs to fix."""
    roadmap_text = _read_if_exists(project / ".ail" / "ROADMAP.md")
    project_md = _read_if_exists(project / "PROJECT.md")
    recent_commits = _git_recent_commits(project)
    scripts_list = _list_scripts(project)
    done_log = _read_done_log(project)
    
    # Get recently changed files for focused analysis
    changed = _git_changed_files(project, days=3)
    changed_str = "\n".join(f"  - {f}" for f in changed) if changed else "(no recent changes)"
    
    diff_content = ""
    if recent_diff:
        diff_content = f"\n### Recent Code Changes (git diff)\n{recent_diff[:3000]}"
    elif changed:
        # Include actual diff for the most recently changed files
        import subprocess
        diff_lines = []
        for f in changed[:5]:
            r = subprocess.run(
                ["git", "diff", "--", f],
                cwd=project, capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip():
                diff_lines.append(f"## {f}\n{r.stdout[:800]}")
        diff_content = "\n\n".join(diff_lines) if diff_lines else ""

    context = f"""## Project: autonomous-improvement-loop

### ROADMAP.md
{roadmap_text[:4000] if roadmap_text else '(none)'}

### PROJECT.md
{project_md[:4000] if project_md else '(none)'}

### Recent Commits (last 10)
{recent_commits or '(none)'}

### Recently Changed Files (last 3 days)
{changed_str}
{diff_content}

### Done Log (recent completed tasks)
{done_log}

### scripts/ Summary
{scripts_list}
"""
    return f"""{context}

## Your Task: 维护模式 — 找 Bug、修 Bug、更新文档、提交

你是一个专业的代码审查者和维护者。进入维护模式后，你的核心职责是：

1. **自主分析代码** — 仔细阅读上面提供的项目最新状态
2. **找真实 Bug** — 根据代码逻辑、类型一致性、边界条件、错误处理缺失等方面发现实际问题
3. **修复并验证** — 实施修复并确保不破坏现有功能
4. **更新文档** — 如果修复影响了行为，更新相关文档
5. **提交** — git commit 你的改动

### 你的找 Bug 策略（不要随机找，要系统分析）：

**高优先级区域**：
- 异常处理缺失的函数（try/except、空值处理）
- 边界条件未处理（index out of range、division by zero）
- 类型不匹配（str/int 混用、None vs ""）
- 逻辑错误（条件判断反向、循环提前终止）
- 并发/资源泄漏（文件未关闭、subprocess 未 wait）
- 配置/环境相关（硬编码路径、缺失环境变量检查）

**你已经完成的维护任务**（避免重复找同样的问题）：
{done_log}

### 输出要求

输出有效的 JSON 格式任务计划，字段说明：

```json
{{
  "title": "修复 XX 模块的 YY 问题（具体描述）",
  "task_type": "maintenance",
  "effort": "short|medium|long",
  "maintenance_tag": "bug_fix",
  "background": "你发现了什么问题，为什么这个 bug 重要",
  "goal": "修复后达到什么效果",
  "context": "你如何分析代码找到这个 bug 的",
  "scope": ["涉及的源文件"],
  "non_goals": ["不做什么"],
  "relevant_files": ["需要查看/修改的文件"],
  "execution_plan": ["Step 1: read file X", "Step 2: identify root cause", "Step 3: apply fix", "Step 4: verify", "Step 5: update docs if needed", "Step 6: git commit"],
  "acceptance_criteria": ["修复后不破坏现有测试", "新测试覆盖此 bug"],
  "why_now": "为什么现在必须修这个 bug",
  "risks": "修复可能带来的风险",
  "rollback": "git revert 的步骤",
  "verification": ["python3 -m pytest tests/ -q", "python3 -m py_compile scripts/xxx.py"]
}}
```

### 关键原则

- **不要生成通用任务**（如"检查所有代码"），要生成**具体可执行的修复任务**
- **每次只做一个 bug 修复**，不要贪多
- **scope 要精确**，只包含真正需要修改的文件
- **execution_plan 要包含 git commit 步骤**
- **如果项目看起来已经很健康**，找到的 bug 很 minor，可以选择更新文档类的任务

Output ONLY valid JSON (no markdown fences, no commentary).
"""


def _read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")[:8000]
    except Exception:
        return ""

def _git_recent_commits(project: Path, n: int = 10) -> str:
    import subprocess
    r = subprocess.run(
        ["git", "log", "--oneline", f"-n{n}"],
        cwd=project, capture_output=True, text=True, timeout=10
    )
    return r.stdout.strip() if r.returncode == 0 else ""

def _git_changed_files(project: Path, days: int = 3) -> list[str]:
    """Return list of files changed in last N days."""
    import subprocess
    r = subprocess.run(
        ["git", "diff", "--name-only", f"HEAD~{days}", "HEAD", "--"],
        cwd=project, capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]

def _read_done_log(project: Path) -> str:
    """Read the Done Log section from ROADMAP.md."""
    roadmap_path = project / ".ail" / "ROADMAP.md"
    if not roadmap_path.exists():
        return ""
    content = roadmap_path.read_text(encoding="utf-8")
    marker = "## Done Log"
    idx = content.find(marker)
    if idx == -1:
        return ""
    return content[idx:idx+2000]

def _list_scripts(project: Path) -> str:
    scripts_dir = project / "scripts"
    if not scripts_dir.exists():
        return "(no scripts/ directory)"
    lines = []
    for p in sorted(scripts_dir.glob("*.py")):
        lines.append(f"{p.name} ({p.stat().st_size // 1024}kb)")
    return "\n".join(lines) if lines else "(no .py files)"
