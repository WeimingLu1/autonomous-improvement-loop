"""
Code quality scoring for Autonomous Improvement Loop.

Provides module-level quality metrics to guide the PM task planner
in prioritizing refactoring of high-complexity modules.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def score_module(module_name: str, project: Path | None = None) -> dict:
    """
    Score a module's quality based on multiple heuristics.

    Returns a dict with:
      - lines: total lines of code
      - complexity: estimated cyclomatic complexity
      - long_functions: count of functions > 30 lines
      - score: overall quality score (0-100, higher = more urgent to refactor)
    """
    if project is None:
        project = Path(__file__).resolve().parent.parent

    module_path = project / "scripts" / module_name
    if not module_path.exists():
        module_path = project / module_name

    if not module_path.exists():
        return {"module": module_name, "error": "not_found", "score": 0}

    try:
        source = module_path.read_text(encoding="utf-8")
    except Exception:
        return {"module": module_name, "error": "read_error", "score": 0}

    lines = len(source.splitlines())

    # Parse AST for complexity analysis
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"module": module_name, "error": "parse_error", "score": 0}

    complexity = _estimate_complexity(tree)
    long_functions = _count_long_functions(tree, source)

    # Score: 0-100, higher = more urgent
    # Factors: line count (weight 0.3), complexity (weight 0.5), long functions (weight 0.2)
    line_score = min(lines / 100 * 30, 30)  # 100 lines = 30 pts
    complexity_score = min(complexity / 20 * 50, 50)  # 20 complexity = 50 pts
    function_score = min(long_functions * 10, 20)  # each long fn = 10 pts, max 20

    score = int(line_score + complexity_score + function_score)

    return {
        "module": module_name,
        "lines": lines,
        "complexity": complexity,
        "long_functions": long_functions,
        "score": score,
    }


def _estimate_complexity(tree: ast.AST) -> int:
    """Estimate cyclomatic complexity from an AST."""
    complexity = 1  # base complexity
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1  # and/or add branches
        elif isinstance(node, ast.comprehension):
            complexity += 1  # each comprehension branch
    return complexity


def _count_long_functions(tree: ast.AST, source: str) -> int:
    """Count functions with more than 30 lines."""
    lines = source.splitlines()
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, "end_lineno") and node.end_lineno and node.lineno:
                fn_lines = node.end_lineno - node.lineno + 1
                if fn_lines > 30:
                    count += 1
    return count


def score_all_modules(project: Path | None = None) -> list[dict]:
    """Score all modules in the scripts/ directory."""
    if project is None:
        project = Path(__file__).resolve().parent.parent

    scripts_dir = project / "scripts"
    if not scripts_dir.exists():
        return []

    results = []
    for module_path in sorted(scripts_dir.glob("*.py")):
        if module_path.name.startswith("_"):
            continue
        result = score_module(module_path.name, project)
        results.append(result)

    return sorted(results, key=lambda r: r.get("score", 0), reverse=True)


def get_high_complexity_modules(project: Path | None = None, threshold: int = 50) -> list[str]:
    """Return module names with quality score >= threshold."""
    all_scores = score_all_modules(project)
    return [r["module"] for r in all_scores if r.get("score", 0) >= threshold]


if __name__ == "__main__":
    import sys

    project = Path.cwd() if len(sys.argv) < 2 else Path(sys.argv[1])
    module = sys.argv[2] if len(sys.argv) > 2 else None

    if module:
        result = score_module(module, project)
        print(f"{module}: score={result['score']}, lines={result.get('lines', '?')}, "
              f"complexity={result.get('complexity', '?')}, "
              f"long_functions={result.get('long_functions', '?')}")
    else:
        print("Module quality scores (higher = more urgent to refactor):")
        for r in score_all_modules(project):
            print(f"  {r['module']:25s} score={r.get('score', 0):3d}  "
                  f"lines={r.get('lines', 0):4d}  complexity={r.get('complexity', 0):3d}")
