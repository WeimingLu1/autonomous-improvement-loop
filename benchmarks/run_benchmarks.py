#!/usr/bin/env python3
"""
Performance benchmark for Autonomous Improvement Loop commands.
Tracks response times for a-plan, a-current, a-status, and a-trigger commands.

Usage:
    python benchmarks/run_benchmarks.py
    python benchmarks/run_benchmarks.py --iterations 3
    python benchmarks/run_benchmarks.py --output benchmarks/results.jsonl
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Project root (directory containing this file's parent)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
INIT_PY = PROJECT_ROOT / "scripts" / "init.py"


def run_command(cmd: list[str], iterations: int = 3) -> dict:
    """Run a command multiple times and collect timing statistics."""
    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            elapsed = time.perf_counter() - start
            timings.append({
                "elapsed_ms": round(elapsed * 1000, 2),
                "returncode": result.returncode,
                "success": result.returncode == 0,
            })
        except subprocess.TimeoutExpired:
            timings.append({
                "elapsed_ms": 30000,
                "returncode": -1,
                "success": False,
                "error": "timeout",
            })
        except Exception as e:
            timings.append({
                "elapsed_ms": 0,
                "returncode": -1,
                "success": False,
                "error": str(e),
            })

    elapsed_ms_list = [t["elapsed_ms"] for t in timings]
    return {
        "command": " ".join(cmd),
        "iterations": iterations,
        "min_ms": min(elapsed_ms_list),
        "max_ms": max(elapsed_ms_list),
        "mean_ms": round(sum(elapsed_ms_list) / len(elapsed_ms_list), 2),
        "all_timings_ms": elapsed_ms_list,
        "all_success": all(t["success"] for t in timings),
        "first_error": next((t for t in timings if not t["success"]), None),
    }


def benchmark_command(name: str, cmd: list[str], iterations: int = 3) -> dict:
    """Benchmark a single command and return structured result."""
    start_ts = datetime.now(timezone.utc).isoformat()
    result = run_command(cmd, iterations=iterations)
    result["benchmark_name"] = name
    result["timestamp"] = start_ts
    result["project"] = str(PROJECT_ROOT)
    return result


def run_all_benchmarks(iterations: int = 3) -> list[dict]:
    """Run benchmarks for all tracked commands."""
    benchmarks = [
        ("a-status", [sys.executable, str(INIT_PY), "a-status", str(PROJECT_ROOT)]),
        ("a-current", [sys.executable, str(INIT_PY), "a-current", str(PROJECT_ROOT)]),
        ("a-plan", [sys.executable, str(INIT_PY), "a-plan", str(PROJECT_ROOT)]),
        ("a-log", [sys.executable, str(INIT_PY), "a-log", "-n", "5", str(PROJECT_ROOT)]),
    ]
    results = []
    for name, cmd in benchmarks:
        print(f"  Benchmarking {name}...", end=" ", flush=True)
        r = benchmark_command(name, cmd, iterations=iterations)
        print(f"mean={r['mean_ms']:.1f}ms, success={r['all_success']}")
        results.append(r)
    return results


def write_results(results: list[dict], output_path: Path):
    """Append benchmark results to a JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Results written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Run AIL command benchmarks")
    parser.add_argument("--iterations", type=int, default=3, help="Iterations per command (default: 3)")
    parser.add_argument("--output", type=str, default="benchmarks/results.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    print(f"Running AIL benchmarks ({args.iterations} iterations each)...")
    results = run_all_benchmarks(iterations=args.iterations)
    output_path = PROJECT_ROOT / args.output
    write_results(results, output_path)

    # Summary
    print("\n=== Benchmark Summary ===")
    for r in results:
        status = "✓" if r["all_success"] else "✗"
        print(f"  {status} {r['benchmark_name']:20s} mean={r['mean_ms']:7.2f}ms  min={r['min_ms']:7.2f}ms  max={r['max_ms']:7.2f}ms")


if __name__ == "__main__":
    main()