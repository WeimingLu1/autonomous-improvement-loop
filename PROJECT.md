# HealthAgent — 项目概览

> 持续自主改进项目 | 由 autonomous-improvement-loop 驱动

---

## 基本信息

| 字段 | 内容 |
|------|------|
| 名称 | HealthAgent |
| 类型 | software |
| 版本 | 0.3.6 |
| 仓库 | https://github.com/WeimingLu1/HealthAgent |
| 定位 | 个人健康 CLI + OpenClaw Agent Skill |
| 技术栈 | Python + Typer + SQLAlchemy + SQLite + Minimax LLM |

---

## 项目定位

HealthAgent 是一款面向个人健康管理的 CLI 工具，同时也是 OpenClaw Agent 的健康顾问 Skill。它帮助用户通过结构化日志（饮食、睡眠、运动、用药、测量）记录日常健康数据，结合 AI（Minimax LLM）为用户提供个性化健康建议、趋势分析与360度健康报告。

---

## 核心功能

| 模块 | 说明 |
|------|------|
| 健康日志 | 记录饮食、睡眠、运动、用药、测量等日常健康事件 |
| 健康顾问 | AI 驱动的个性化健康建议与问答 |
| 健康报告 | 生成结构化健康摘要与趋势分析 |
| CLI 工具 | Typer 构建的命令行界面，支持交互式输入 |
| OpenClaw Skill | 作为 Agent Skill 接入 OpenClaw，支持自然语言交互 |
| 配置管理 | 支持 `~/.healthagent.yaml` 用户配置 |
| 数据导出 | 输出结构化数据（JSON/CSV） |
| Shell 补全 | 支持 bash/zsh/fish 自动补全 |

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           OpenClaw Agent                │
│    (Skill: health-agent / a-* 命令)     │
└──────────────┬──────────────────────────┘
               │ Telegram / CLI
┌──────────────▼──────────────────────────┐
│         HealthAgent CLI (Typer)          │
│  health, meal, sleep, exercise, drug,   │
│  measure, report, advise, config ...      │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         Domain Layer (SQLAlchemy)         │
│   MealLog, SleepLog, ExerciseLog,       │
│   DrugLog, MeasureLog, HealthProfile     │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         Data Layer (SQLite)              │
│         ~/.healthagent.db                 │
└─────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         AI Layer (Minimax LLM)           │
│   健康建议 / 报告生成 / 问答              │
└─────────────────────────────────────────┘
```

---

## 近期动态

| 时间 | Commit | 内容 | 结果 |
|------|--------|------|------|
| 2026-04-19T08:50:00Z | a5c9ba2 | 增加用户配置文件支持（~/.healthagent.yaml）及 config 子命令 | pass |
| 2026-04-19T07:20:00Z | ca1f8da | 修复 ruff E501/B904/E712/F841 风格问题（共93处） | pass |
| 2026-04-19T06:50:00Z | 92d1f9b | ruff auto-fix 清理：datetime.UTC 别名/unused imports/f-string 修正 | pass |
| 2026-04-19T06:20:00Z | 5c452e6 | 为根包、domain 和 services 的 __init__.py 补充模块 docstring | pass |
| 2026-04-19T05:20:00Z | c7b47f7 | 实现360度健康建议专家：综合档案建设→定制方案→动态反馈飞轮 | pass |

---

## 开放方向（软件类创意问题）

以下为待探索的软件增强方向，按优先级或价值排列：

1. **多用户/家庭档案支持** — 支持管理多位家庭成员的健康档案，切换 profile 即可查看各自数据
2. **健康数据可视化** — 增加图表命令（趋势图、柱状图），基于 ASCII 或输出图片
3. **外部 API 集成** — 接入食物营养库 API、运动 API（如 Strava/Apple Health），减少手动输入
4. **数据导入/同步** — 支持从 CSV/JSON 批量导入历史数据，或与 Apple Health / Google Fit 同步
5. **增强隐私保护** — 增加本地数据加密、敏感字段脱敏导出功能

---

*最后更新：2026-04-19*
