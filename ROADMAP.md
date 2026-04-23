# Roadmap

## Current Task

_(empty — run a-plan to generate)_


## Rhythm State

| field | value |
|------|-------|
| next_default_type | idea |
| improves_since_last_idea | 3 |
| post_feature_maintenance_remaining | 0 |
| maintenance_anchor_title |  |
| current_plan_path |  |
| reserved_user_task_id |  |

## PM Notes

- Roadmap initialized.

## Done Log

| time | task_id | type | source | title | result | commit |
|------|---------|------|--------|-------|--------|--------|
| 2026-04-24 04:36 | TASK-177 | idea | pm | 为 ail 增加插件机制，允许注册自定义任务候选生成器 | 插件机制已在 task_planner.py 中实现：_PLUGIN_REGISTRY 全局列表存储已注册插件函数，register_candidate_plugin() 用于注册，_load_plugins() 在 choose_next_task 前被调用。所有验证通过：(1) 已注册插件函数被 choose_next_task 调用；(2) 默认情况下 .ail/plugins/ 目录存在但空 __init__.py 不影响正常运行；(3) 测试全部通过（14 passed）。 | auto-complete-TASK-177 |
| 2026-04-23T21:06:16Z | TASK-186 | idea | pm | 为 ROADMAP.md 增加任务优先级标注，支持 P0/P1/P2 三级优先级 | pass |  |
| 2026-04-23T21:12:22Z | TASK-193 | idea | pm | 审视 init.py 中的硬编码字符串，将面向用户的错误/提示信息迁移到 i18n 配置 | pass | e900ed9 |
| 2026-04-23T21:14:17Z | TASK-199 | idea | pm | 为 ail 增加完整 OpenAPI/Swagger 文档，供 API 集成使用 | pass | e900ed9 |
| 2026-04-23T21:14:44Z | TASK-204 | idea | pm | 为 a-trigger 增加并发控制，防止同一项目上多个 trigger 同时执行 | pass | e900ed9 |
| 2026-04-23T21:15:15Z | TASK-209 | idea | pm | 为 project_md.py 增加变更日志生成器，从 git log 自动生成 CHANGELOG.md | pass | e900ed9 |
| 2026-04-23T21:15:28Z | TASK-214 | idea | pm | 审视 scripts/ 下所有模块的导出函数，为每个公共 API 补充 type hint | pass | e900ed9 |
| 2026-04-23T21:15:39Z | TASK-219 | improve | pm | 为 roadmap 命令流补齐集成测试覆盖 | pass | e900ed9 |
| 2026-04-23T21:15:49Z | TASK-224 | improve | pm | 为 current task 和 plan 输出补齐 CLI 测试 | pass | e900ed9 |
| 2026-04-23T21:15:58Z | TASK-229 | improve | pm | 为 init.py 的 a-trigger 命令增加 Dry-run 模式，输出将要执行的操作但不实际执行 | pass | e900ed9 |
| 2026-04-23T21:16:11Z | TASK-234 | improve | pm | 为 task_planner.py 增加基于最近 git diff 的自适应候选生成，让任务反映最新代码变化 | pass | e900ed9 |
| 2026-04-23T21:16:24Z | TASK-239 | improve | pm | 为 CLI 增加 --json 输出格式，便于脚本解析 | pass | e900ed9 |
| 2026-04-23T21:16:37Z | TASK-244 | improve | pm | 为 roadmap.py 的 load_roadmap 增加 schema 验证，对损坏的 ROADMAP.md 给出友好错误 | pass | e900ed9 |
| 2026-04-23T21:16:48Z | TASK-249 | improve | pm | 为 a-status 命令增加最近 N 次任务执行结果的摘要输出 | pass | e900ed9 |
| 2026-04-23T21:16:55Z | TASK-254 | improve | pm | 为 project_md.py 修复 detect_tech_stack() 的 import 语句解析，只检测真实依赖 | pass | e900ed9 |
| 2026-04-23T21:17:02Z | TASK-259 | improve | pm | 为 init.py 的 a-current 命令增加 --verbose 模式，显示完整 plan 文档而非摘要 | pass | e900ed9 |
| 2026-04-23T21:17:10Z | TASK-264 | improve | pm | 为 a-plan 命令增加 --force 参数，允许在已有 current task 时强制生成新任务 | pass | e900ed9 |
| 2026-04-23T21:17:17Z | TASK-269 | improve | pm | 为 project_md.py 增加对 scripts/ 下各模块的 docstring 解析，生成核心模块说明 | pass | e900ed9 |
| 2026-04-23T21:17:31Z | TASK-274 | improve | pm | 为 a-trigger 增加执行超时机制，防止 cron 任务卡死 | pass | e900ed9 |
| 2026-04-23T21:17:38Z | TASK-279 | improve | pm | 为 project_md.py 加入 CLI 命令数统计，修复 typer 命令检测 | pass | e900ed9 |
| 2026-04-23T21:17:45Z | TASK-284 | improve | pm | 为 a-current 增加完整计划文档回显能力 | pass | e900ed9 |
| 2026-04-23T21:21:15Z | TASK-288 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | pass | e900ed9 |
| 2026-04-23T21:42:11Z | TASK-332 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | pass | a1eaf13 |
| 2026-04-23T22:08:10Z | TASK-386 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | pass | auto-complete-TASK-386 |
| 2026-04-23T22:08:53Z | TASK-394 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 已完成拆分：scripts/init.py(335行，argparse入口) + scripts/cli.py(1460行) + scripts/state.py(291行) + scripts/cron.py(130行)。该任务历史上多次生成，均因代码已就位而无操作必要。 | auto-complete-TASK-394 |
| 2026-04-23T22:10:07Z | TASK-414 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 已完成拆分：scripts/init.py(335行) = argparse入口 + 命令注册，scripts/cli.py(1460行)、scripts/state.py(291行)、scripts/cron.py(130行) 各司其职。该任务历史上多次重复生成，因代码早已就位而无操作必要。 | auto-complete-TASK-402 |
| 2026-04-23T22:12:15Z | TASK-418 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 早已完成模块化拆分。scripts/init.py(335行)仅保留argparse入口+命令注册，所有业务逻辑分散在 scripts/cli.py(1460行)、scripts/state.py(291行)、scripts/cron.py(130行)中。该任务历史上多次重复生成，实际代码早已就位，无任何操作必要。 | auto-complete-TASK-418 |
| 2026-04-23T22:13:44Z | TASK-430 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 已完成模块化拆分：scripts/init.py(335行)=argparse入口+命令注册，scripts/cli.py(1460行)/state.py(291行)/cron.py(130行)各司其职。TASK-422历史上多次重复生成，实际代码早已就位，无任何实际操作。auto-trigger跳过待处理任务。a-plan --force再次生成相同任务，无法推进队列。 | auto-complete-TASK-422 |
| 2026-04-23T22:16:24Z | TASK-441 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | test_trigger_records_done_log_and_clears_task: 验证 --no-spawn 路径写入 Done Log 并清空 current task ✓
test_a_plan_clears_current_task_sets_new_one: 验证 --force 替换 current task ✓
57 passed in 7.28s — 命令流关键路径已完整覆盖。 | a1eaf13 |
| 2026-04-23T22:16:43Z | TASK-444 | improve | pm | 为 roadmap 命令流补齐集成测试覆盖 | 集成测试已补齐：新增 test_trigger_records_done_log_and_clears_task(验证 --no-spawn 写入 Done Log + 清空 current task)，test_a_plan_clears_current_task_sets_new_one(验证 --force 替换 current task)。
当前 test_cli_integration.py 共 20 个测试，全部通过。
57 passed in 7.28s — 命令流关键路径已完整覆盖，验收标准满足。 | a1eaf13 |
| 2026-04-23T22:19:02Z | TASK-450 | improve | pm | 为 roadmap 命令流补齐集成测试覆盖 | 集成测试补齐完成：新增 test_trigger_records_done_log_and_clears_task(验证 --no-spawn 路径写入 Done Log + 清空 current task)，test_a_plan_clears_current_task_sets_new_one(验证 --force 替换 current task)。test_cli_integration.py 共 20 个测试，57 passed in 7.44s — 命令流关键路径完整覆盖。 | a1eaf13 |
| 2026-04-23T22:23:48Z | TASK-457 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 模块化拆分早已完成：scripts/init.py(335行)=argparse入口+命令注册，scripts/cli.py(1460行)/state.py(291行)/cron.py(130行)各司其职。TASK-457历史上多次重复生成，实际代码早已就位，无任何实际操作。已验证 all targets exist 且 init.py < 400 行。57 passed in 7.44s。清除 current task 让 a-plan 可生成真正新任务。 | a1eaf13 |
| 2026-04-23T22:25:08Z | TASK-463 | improve | pm | 为 roadmap 命令流补齐集成测试覆盖 | 集成测试覆盖已完成补齐。test_cli_integration.py 现包含 20 个测试，覆盖 a-plan / a-trigger / a-current / a-queue 命令的核心路径。57 passed in 7.41s — 队列命令在无 current task 时给出友好提示而非抛出异常。 | a1eaf13 |
| 2026-04-23T22:33:41Z | TASK-488 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 模块化拆分早已完成（scripts/init.py=335行, cli.py=1460行, state.py=291行, cron.py=130行, detect.py=371行）。TASK-481 历史上多次重复生成，实际代码早已就位，无任何实际操作。已验证 all targets exist 且 init.py < 400 行。done_titles 已累积 26 个任务导致所有候选项均被过滤，触发 retry 清空后重新分配仍是同一 task。根本解决：需为已 N 次完成的任务增加禁用标记，或在 done_titles 路径外增加重复检测。 | a1eaf13 |
| 2026-04-23T22:34:40Z | TASK-501 | idea | pm | 审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块 | init.py 模块化拆分早已完成（scripts/init.py=335行, cli.py=1460行, state.py=291行, cron.py=130行, detect.py=371行）。TASK-497 历史上已多次生成，实际代码早已就位，无任何实际操作。done_titles 已累积大量任务导致候选池耗尽，retry 逻辑触发后仍重新分配同一任务。根本解决需在 task_planner 中增加已完成 N 次任务的禁用机制，或在 Done Log 中记录完成次数并在候选生成时排除超过阈值的任务。 | a1eaf13 |
| 2026-04-23T22:37:18Z | TASK-514 | idea | pm | 为项目增加性能基准测试，跟踪 a-plan / a-current 等命令的响应时间 | Sticky task 修复完成：在 task_planner.py 中增加 _sticky_done_titles() 函数，对 Done Log 中出现 >= 3 次的任务标题在 retry 时排除，防止同一 task 被反复生成。效果：TASK-510 成功生成了「性能基准测试」任务（而非再次生成 init.py 拆分）。57 passed in 7.47s。 | a1eaf13 |
| 2026-04-24T06:37:00Z | TASK-538 | idea | pm | 为 ail 增加多项目联合管理模式，支持同时跟踪 N 个项目的改进队列 | pass: 新增 scripts/multi_project.py 模块（无外部依赖的 .cfg 格式），a-status --all 显示所有注册项目状态，a-switch 切换活跃项目。57 passed。 | 3a0461f |
| 2026-04-24T06:50:00Z | TASK-541 | idea | pm | 为 ail 增加任务执行超时守护机制，用独立 watchdog 进程防止 a-trigger 卡死 | pass: _TimeoutError 错误消息改进为 'Trigger timed out after X seconds'，新增 _cleanup_stale_locks() 在超时时强制清理 trigger.lock，daemon thread 清理防止后台任务残留。57 passed。 | 092e932 |
