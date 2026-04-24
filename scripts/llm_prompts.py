"""Prompts for LLM-powered PM plan generation."""
from pathlib import Path

def build_plan_prompt(project: Path, language: str) -> str:
    roadmap_text = _read_if_exists(project / ".ail" / "ROADMAP.md")
    project_md = _read_if_exists(project / "PROJECT.md")
    recent_commits = _git_recent_commits(project)
    scripts_list = _list_scripts(project)

    context = f"""## Project Context

### ROADMAP.md (current state)
{roadmap_text or '(no ROADMAP.md)'}

### PROJECT.md
{project_md or '(no PROJECT.md)'}

### Recent Git Commits
{recent_commits or '(no git history)'}

### scripts/ Directory
{scripts_list}
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
  "rollback": "How to revert if needed"
}}
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

def _list_scripts(project: Path) -> str:
    scripts_dir = project / "scripts"
    if not scripts_dir.exists():
        return "(no scripts/ directory)"
    lines = []
    for p in sorted(scripts_dir.glob("*.py")):
        lines.append(f"{p.name} ({p.stat().st_size // 1024}kb)")
    return "\n".join(lines) if lines else "(no .py files)"
