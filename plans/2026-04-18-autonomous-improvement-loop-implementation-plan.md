# Autonomous Improvement Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 autonomous-improvement-loop skill 改造成一个完整的自主研发守护系统，包含 AI 优先级队列、cron 锁文件串行化、LLM 评分、自动提交 GitHub。

**Architecture:** 单 agent × 单项目，队列存储在 skill 目录内（不污染项目）。cron 在 isolated session 运行，与用户共享队列。优先级由 agent 自己的 LLM 直接计算。

**Tech Stack:** Python 3.13 + subprocess + LLM（agent 自己的 Minimax M2.7）+ Git + GitHub CLI

---

## Task 1: 创建 `config.md`（项目配置文件）

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/config.md`

- [ ] **Step 1: 写入 config.md**

```markdown
# Autonomous Improvement Loop — 项目配置

> 安装 skill 后填写此文件，即完成项目绑定。

## 项目路径
project_path: ~/Projects/YOUR_PROJECT

## GitHub 仓库（用于 gh release 和 issue 链接）
repo: https://github.com/OWNER/REPO

## 版本文件（项目根目录）
version_file: ~/Projects/YOUR_PROJECT/VERSION

## 文档目录（项目内的 agent 文档）
docs_agent_dir: ~/Projects/YOUR_PROJECT/docs/agent

## OpenClaw Agent ID
agent_id: YOUR_AGENT_ID

## Telegram Chat ID（用于 announce）
chat_id: YOUR_CHAT_ID

## CLI 名称
cli_name: health

## Cron 调度
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
```

- [ ] **Step 2: Commit**

```bash
git add skills/autonomous-improvement-loop/config.md
git commit -m "feat(autonomous-improvement-loop): add config.md"
```

---

## Task 2: 重写 `HEARTBEAT.md`（新队列格式 + Run Status）

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/HEARTBEAT.md`

- [ ] **Step 1: 写入 HEARTBEAT.md（初始状态）**

```markdown
# Autonomous Improvement Loop — 队列状态

> Skill: autonomous-improvement-loop | 单 agent × 单项目
> 配置: config.md

---

## Run Status

| 字段 | 值 |
|------|----|
| last_run_time | never |
| last_run_commit | `none` |
| last_run_result | unknown |
| last_run_task | none |
| cron_lock | false |
| rollback_on_fail | true |

---

## Queue

> score 由 agent LLM 计算，用户请求自动 score=100（插队）
> 格式：| # | 类型 | score | 内容 | 来源 | 状态 | 创建时间 |

| # | 类型 | score | 内容 | 来源 | 状态 | 创建时间 |
|---|------|-------|------|------|------|----------|
| 1 | improve | 65 | [[Improve]] 补齐 skill 初始队列 | system | pending | 2026-04-18 |

---

## 每个任务完成后的标准动作

### ① cron_lock = true
`python scripts/run_status.py --heartbeat HEARTBEAT.md write --cron-lock true`

### ② Run Status = starting
`python scripts/run_status.py --heartbeat HEARTBEAT.md write --result starting --task "<task>"`

### ③ 读取队列 + AI 重排序
读取 Queue 表，按 score 降序取顶部任务

### ④ 实现 + pytest
- pytest 失败 → #bug，优先修
- pytest 通过 → 实现 feature/improve

### ⑤ commit + push + rollback_if_unstable
```bash
git add . && git commit -m "feat(#N): 简短描述" && git push
python scripts/verify_and_revert.py --project . --heartbeat HEARTBEAT.md --task "<task>"
```

### ⑥ 文档同步
```bash
python scripts/verify_cli_docs.py --project . --cli-name MYAPP
# 若不一致，修复 README 后重新 commit + push
```

### ⑦ Release
```bash
VERSION=$(cat VERSION)
git tag -a v${VERSION} -m "Release v${VERSION}"
git push origin v${VERSION}
gh release create "v${VERSION}" --generate-notes
next=$((VERSION + 1))
echo ${next} > VERSION
git add VERSION && git commit -m "chore: bump version" && git push
```

### ⑧ Run Status 更新
```bash
HASH=$(git rev-parse HEAD)
python scripts/run_status.py --heartbeat HEARTBEAT.md write --commit $HASH --result pass --task "<task>" --cron-lock false
```

### ⑨ announce 汇报给 Telegram

### ⑩ project_insights.py 追加 1 个候选

---

## Queue 管理规则

- 用户请求 → score=100 → 立即插队到 #1
- cron 正在运行时（cron_lock=true）→ 用户请求仍入队，但 agent 拒绝直接修改文件
- 每次添加条目后，按 score 降序重排序
- score 相等时，在队列时间更早的优先
```

---

## Task 3: 重写 `DEVLOG.md`

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/DEVLOG.md`

- [ ] **Step 1: 写入 DEVLOG.md（初始状态）**

```markdown
# Autonomous Improvement Loop — 开发日志

> 此文件记录 skill 对应项目的所有已完成改进，按完成时间倒序排列。
> skill = agent × 项目，1:1 绑定。

---

## 2026-04-18

### ✅ 完成项

| # | 任务 | Commit | Release | 备注 |
|---|------|--------|---------|------|
| 1 | skill 初始构建 | — | — | autonomous-improvement-loop 基础版本 |

---

*正在记录中...*
```

---

## Task 4: 写 `scripts/priority_scorer.py`（LLM 优先级评分）

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/scripts/priority_scorer.py`

> **重要设计决策**：脚本**不直接调 LLM API**，而是输出一个结构化的评分 prompt，让调用者（agent）用自己的 LLM 计算后传回分数。这样 skill 不需要知道具体 API key 或 base URL，实现真正的项目无关性。

- [ ] **Step 1: 写入 priority_scorer.py**

```python
#!/usr/bin/env python3
"""AI priority scorer — generates a scoring prompt for the agent's LLM.

Usage:
    python priority_scorer.py --task "补齐 auth.py 的单元测试" --type improve

Output: a structured JSON with score and reason, OR a prompt string for agent to evaluate.

This script does NOT call the LLM directly — it generates the input for the agent's LLM.
The agent (or caller) is responsible for evaluation using its own LLM.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent

PROMPT_TEMPLATE = """\
请为以下任务计算优先级分数（0-100）。

任务类型：{task_type}
任务描述：{task_description}

评分标准：
- 用户请求 = 100（强制插队）
- 破坏核心功能的 bug：90-100
- 破坏非核心功能：70-89
- 重要功能增强：65-79
- 一般功能：50-64
- 内部改进（测试/文档）：30-49

只输出 JSON：{{"score": <数字>, "reason": "<一句话理由>"}}
"""


def generate_prompt(task_type: str, task_description: str) -> str:
    """Generate the LLM scoring prompt."""
    if task_type == "user_request":
        return json.dumps({"score": 100, "reason": "用户请求，强制插队"}, ensure_ascii=False)
    return PROMPT_TEMPLATE.format(task_type=task_type, task_description=task_description)


def parse_llm_response(raw: str) -> dict:
    """Parse JSON from LLM response text."""
    json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return {"score": 50, "reason": "默认分（解析失败）"}


def main() -> int:
    parser = argparse.ArgumentParser(description="AI priority scorer — generate LLM scoring prompt")
    parser.add_argument("--task", required=True, help="任务描述")
    parser.add_argument("--type", required=True, choices=["bug", "feature", "improve", "user_request"])
    parser.add_argument("--evaluate", help="agent LLM 的原始输出，将自动解析 score")
    args = parser.parse_args()

    if args.evaluate:
        result = parse_llm_response(args.evaluate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        prompt = generate_prompt(args.type, args.task)
        # Output the prompt for the agent to send to its own LLM
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Agent 调用模式**（在 SKILL.md 中说明）：
```bash
# 1. 生成 prompt
PROMPT=$(python priority_scorer.py --task "补齐 auth.py 测试" --type improve)

# 2. Agent 把自己 LLM 的响应传入
python priority_scorer.py --task "..." --type improve --evaluate "$(agent_llm_call $PROMPT)"
```

**简化实现（第一版）**：先用规则评分，后续 agent 自行用 LLM 改写 `score_task()` 函数。

```python
def score_task(task_type: str, task_description: str) -> dict:
    """Rule-based fallback scoring."""
    if task_type == "user_request":
        return {"score": 100, "reason": "用户请求，强制插队"}
    if task_type == "bug":
        if any(k in task_description for k in ["崩溃", "crash", "无法", "失败"]):
            return {"score": 88, "reason": "疑似核心功能 bug"}
        return {"score": 72, "reason": "普通 bug"}
    if task_type == "feature":
        return {"score": 65, "reason": "功能需求"}
    if task_type == "improve":
        return {"score": 50, "reason": "改进建议"}
    return {"score": 50, "reason": "默认"}
```

后续 agent 可用 LLM 改进此函数。

---

## Task 5: 更新 `scripts/run_status.py`（加入 cron_lock 支持）

**Files:**
- Modify: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/scripts/run_status.py`

- [ ] **Step 1: 添加 --cron-lock 参数**

在 `build_parser()` 中 `write` 子命令加入：
```python
write_parser.add_argument("--cron-lock", required=False, choices=["true", "false"])
```

- [ ] **Step 2: 更新 `render_block`**

在表格中加入一行：
```python
f"| cron_lock | {cron_lock} |\n"
```

- [ ] **Step 3: 更新 `extract_status`**

加入提取 `cron_lock` 的正则：
```python
"cron_lock": r"\| cron_lock \|\s*(.+?)\s*\|",
```

- [ ] **Step 4: 更新 `write_status` 函数签名**

```python
def write_status(heartbeat: Path, commit: str, result: str, task: str, cron_lock: str = "unchanged"):
```

如果 `cron_lock != "unchanged"`，更新该字段。

- [ ] **Step 5: 更新 `main()` 中的 write 调用**

```python
write_status(args.heartbeat, args.commit, args.result, args.task, getattr(args, "cron_lock", "unchanged"))
```

- [ ] **Step 6: Commit**

```bash
git add skills/autonomous-improvement-loop/scripts/run_status.py
git commit -m "feat(autonomous-improvement-loop): add cron_lock to run_status"
```

---

## Task 6: 更新 `scripts/project_insights.py`（接入 priority_scorer）

**Files:**
- Modify: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/scripts/project_insights.py`

- [ ] **Step 1: 在 `append_candidate` 中调用 priority_scorer**

在追加到 HEARTBEAT.md 之前，先调用 `priority_scorer.py` 获取 score：

```python
def append_candidate(heartbeat: Path, repo: str, finding: str) -> bool:
    # ...
    # 调用 priority_scorer 获取 score
    try:
        scorer = Path(__file__).parent / "priority_scorer.py"
        result = subprocess.run(
            [sys.executable, str(scorer), "--task", finding, "--type", "improve"],
            capture_output=True, text=True, timeout=30,
        )
        import json
        score_data = json.loads(result.stdout)
        score = score_data.get("score", 50)
    except Exception:
        score = 50  # fallback

    new_line = f"{next_num}. [[Improve]] score={score} | {finding} | scanner | pending | {now_shanghai()}"
    # ...
```

- [ ] **Step 2: Commit**

```bash
git add skills/autonomous-improvement-loop/scripts/project_insights.py
git commit -m "feat(autonomous-improvement-loop): integrate priority_scorer into queue_scanner"
```

---

## Task 7: 写 `prompts/QUEUE_SYSTEM_PROMPT.md`（队列系统行为规范）

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/prompts/QUEUE_SYSTEM_PROMPT.md`

- [ ] **Step 1: 写入 QUEUE_SYSTEM_PROMPT.md**

```markdown
# Queue System — Agent Behavior Prompt

你正在以 Autonomous Improvement Loop 模式运行。

## 核心约束

1. **单项目制**：你只维护 `config.md` 中 `project_path` 指定的唯一项目
2. **队列串行化**：你和 cron 共享同一个队列，不存在并发修改冲突
3. **用户请求强制插队**：用户发来的任何任务（bug 或 feature）立即获得 score=100，插入队列 #1
4. **cron_lock 保护**：当 `Run Status.cron_lock == true` 时，**拒绝**任何直接文件修改，只能操作队列

## 队列操作规则

### 读取队列
读取 `config.md` 中指定的 `project_path`，结合 skill 目录的 `HEARTBEAT.md`。

### 添加用户任务到队列
```
任务类型: user_request → score=100
内容: 用户原始描述（保持用户语言）
来源: user
状态: pending
```

### AI 评分（自动）
对 scanner 和 system 来源的条目，调用 `scripts/priority_scorer.py` 计算 score。

### 排序
每次添加条目后，按 score 降序重排序，写回 HEARTBEAT.md。

## cron 执行期间
- `cron_lock = true`
- 你收到用户消息时，只能操作队列（添加/查看），不能修改项目文件
- 回复示例：`✅ 已收到！当前 cron 正在运行，已将任务插队至 #1（score=100）`

## cron 执行完成后
- `cron_lock = false`
- 正常响应用户请求

## 提交格式
```
feat(#<队列编号>): <用户可见的简短描述>
```
```

---

## Task 8: 写 `prompts/CLEANUP_CHECKLIST.md`（提交前自查）

**Files:**
- Create: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/prompts/CLEANUP_CHECKLIST.md`

- [ ] **Step 1: 写入 CLEANUP_CHECKLIST.md**

```markdown
# 提交前自查清单

每次 commit 前逐项检查：

## 代码质量
- [ ] 没有打印调试语句（print/debug/log）
- [ ] 没有 TODO/FIXME 未完成（除非已在队列中记录）
- [ ] 变量/函数命名清晰，符合项目风格
- [ ] 没有巨大的函数（>50行考虑拆分）

## 功能
- [ ] pytest 全部通过（`pytest -q`）
- [ ] 新功能有对应的测试
- [ ] CLI 命令 `--help` 输出正确

## 文档
- [ ] README.md 中命令示例与实际 CLI输出一致
- [ ] 新增命令已写入 Quick Start 或对应章节
- [ ] HEARTBEAT.md 中队列已更新（完成项归档）

## Git
- [ ] commit message 格式：`feat(#N):` 或 `fix(#N):`
- [ ] 同一个改动没有分成多个 commit
- [ ] 没有提交不该进仓库的文件（.env、__pycache__、.venv）

## 发布
- [ ] VERSION 文件已更新
- [ ] git tag 已创建
- [ ] gh release 已生成
```

---

## Task 9: 重写 `SKILL.md`（整合新设计）

**Files:**
- Rewrite: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/SKILL.md`

**覆盖所有新组件：**
- config.md 用法（安装时填写）
- HEARTBEAT.md 新格式（Queue 表 + Run Status + cron_lock）
- DEVLOG.md 用途
- 每个脚本的用途和调用方式
- Queue System Prompt（prompts/ 目录）
- CLEANUP_CHECKLIST.md
- 完整的 8 步 cron 执行流程

- [ ] **Step 1: 重写 SKILL.md**

（内容覆盖上述所有组件后 commit）

```bash
git add skills/autonomous-improvement-loop/SKILL.md
git commit -m "docs(autonomous-improvement-loop): rewrite SKILL.md with new queue system"
```

---

## Task 10: 更新 `references/file-templates.md`

**Files:**
- Modify: `~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/references/file-templates.md`

- [ ] 更新 HEARTBEAT.md 模板（Queue 表格式 + cron_lock）
- [ ] 更新 Devlog、Report 模板
- [ ] 加入 config.md 模板

```bash
git add skills/autonomous-improvement-loop/references/file-templates.md
git commit -m "docs(autonomous-improvement-loop): update file templates for new queue format"
```

---

## Task 11: 验证脚本语法

- [ ] `python3 -m py_compile skills/autonomous-improvement-loop/scripts/*.py`（全部无错误）
- [ ] `python3 skills/autonomous-improvement-loop/scripts/run_status.py --help`
- [ ] `python3 skills/autonomous-improvement-loop/scripts/priority_scorer.py --help`
- [ ] `python3 skills/autonomous-improvement-loop/scripts/project_insights.py --help`
- [ ] `python3 skills/autonomous-improvement-loop/scripts/verify_cli_docs.py --help`
- [ ] `python3 skills/autonomous-improvement-loop/scripts/verify_and_revert.py --help`

## Task 12: 最终检查

- [ ] 无残留 hardcoded YOUR_PROJECT 路径（所有路径均通过 config.md 注入）
- [ ] `config.md` 存在且可填写
- [ ] `prompts/QUEUE_SYSTEM_PROMPT.md` 内容覆盖 cron_lock 行为
- [ ] 更新 SPEC.md 状态为"已确认并开始实现"

```bash
git add skills/autonomous-improvement-loop/
git commit -m "feat(autonomous-improvement-loop): add automation scripts"
```

---

## Task 12: 最终检查 + 更新 SPEC.md 为已确认状态

- [ ] 将 `specs/autonomous-improvement-loop-design.md` 的状态改为"已确认"
- [ ] 所有文件路径正确，无残留 hardcoded YOUR_PROJECT 路径
- [ ] `config.md` 中所有字段已填写（当前开发阶段可先用 placeholder）

```bash
git add specs/
git commit -m "docs(autonomous-improvement-loop): mark spec as confirmed"
```
