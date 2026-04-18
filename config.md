# config.md — Autonomous Improvement Loop

> 项目级配置。Skill 在工作区根目录读取此文件（不在 skill 目录内）。
> 字段说明：删除线 = 已废弃字段（为兼容仍读取，但不再推荐使用）。

---

## 项目基本信息

```yaml:config
project_path: .
project_kind: generic        # 软件|写作|视频|研究|通用
                             # software | writing | video | research | generic
                             # 留空则由 project_insights.py 自动检测
project_language: zh        # 报告语言: zh = 中文, en = English
```

---

## Git

```yaml:config
github_repo: https://github.com/OWNER/REPO
```

---

## 改进循环

```yaml:config
cron_schedule: "every 30 minutes"   # 调度周期（ISO 8601 duration 或 cron expr）
cron_enabled: true                   # 是否启用定时调度
```

---

## 验证与回滚

```yaml:config
# 验证命令（类型agnostic）
# — 空 → 无自动验证，仅记录结果
# — software 示例: pytest tests/ -q
# — writing 示例: python -m spellcheck .
# — video 示例: ffprobe -v error -show_entries format=duration -i footage.mov
# — research 示例: python -m cite_check .
verification_command:
publish_command:                  # 发布命令（如有），完成后执行
```

---

## 发布（软件项目）

> ⚠️ 以下字段已废弃，仅为向后兼容保留。发布配置请改用 `publish_command`。

```yaml:config
# version_file: VERSION          # [已废弃] 版本号文件路径
# cli_name: MYAPP                # [已废弃] CLI 入口名字（无 CLI 项目可删）
# docs_dir: docs/agent           # [已废弃] agent 文档目录
```

---

## OpenClaw 绑定（可选）

```yaml:config:openclaw
# agent_id: YOUR_AGENT_ID
# chat_id: YOUR_CHAT_ID
```
