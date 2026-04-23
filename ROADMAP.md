# Roadmap

## Current Task

| task_id | type | source | title | priority | status | created |
|--------|------|--------|-------|----------|--------|---------|
| TASK-192 | idea | pm | 为 a-plan 增加多任务规划模式，一次生成 N 个任务并排入队列 | P1 | pending | 2026-04-23 |

## Rhythm State

| field | value |
|------|-------|
| next_default_type | improve |
| improves_since_last_idea | 3 |
| post_feature_maintenance_remaining | 0 |
| maintenance_anchor_title |  |
| current_plan_path | plans/TASK-192.md |
| reserved_user_task_id |  |

## PM Notes

- Roadmap initialized.

## Done Log

| time | task_id | type | source | title | result | commit |
|------|---------|------|--------|-------|--------|--------|
| 2026-04-23T16:00:00Z | TASK-157 | improve | pm | 为 project_md.py 增加对 scripts/ 下各模块的 docstring 解析，生成核心模块说明 | pass | e90342d |
| 2026-04-23T18:00:00Z | TASK-169 | improve | pm | 为 file_lock.py 增加锁超时机制，防止进程崩溃后锁无法释放 | pass | bab14c2 |
| 2026-04-23T21:05:05Z | TASK-186 | idea | pm | 为 ROADMAP.md 增加任务优先级标注，支持 P0/P1/P2 三级优先级 | pass |  |
| 2026-04-24T04:36:00Z | TASK-177 | idea | pm | 为 ail 增加插件机制，允许注册自定义任务候选生成器 | 插件机制已在 task_planner.py 中实现：_PLUGIN_REGISTRY 全局列表存储已注册插件函数，register_candidate_plugin() 用于注册，_load_plugins() 在 choose_next_task 前被调用。所有验证通过：(1) 已注册插件函数被 choose_next_task 调用；(2) 默认情况下 .ail/plugins/ 目录存在但空 __init__.py 不影响正常运行；(3) 测试全部通过（14 passed）。 | auto-complete-TASK-177 |
