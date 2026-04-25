# Maintenance Mode 任务去重重新设计

**日期：** 2026-04-25
**状态：** 设计完成，待实现

---

## 问题陈述

当前 maintenance 模式的任务去重基于 **title 字符串匹配**：
- Done Log 中出现过的 title 会被 `done_titles` 追踪
- title 出现 ≥3 次 → sticky（永久屏蔽）
- retry 时 even 出现 ≥2 次就 block

**结果：** 「进行安全漏洞审计」在 Done Log 里出现 3 次后，永远不会再被选中。维护模式退化为「跑完就死」的单次行为，不适合周期性巡检场景。

---

## 设计目标

1. **自由轮转** — `a-maintenance on` 开启后，只要 maintenance_mode=True，每次 cron 触发都生成 maintenance 任务，不限数量，不自动退出
2. **tag 版本去重** — 去重 key 从 title 字符串改为 `maintenance_tag`
3. **版本命名** — 同一 tag 的任务再次出现时，标题加 v2/v3（例：`进行安全漏洞审计` → `进行安全漏洞审计 v2`）
4. **内容差异化** — 同一 tag 的不同版本，scope/execution_plan 根据项目当前代码状态动态生成，聚焦不同模块
5. **手动关闭** — `a-maintenance off` 恢复 normal 模式

---

## 设计细节

### 1. Done Log Schema 变更

现有 Done Log 格式：
```
| time | task_id | type | source | title | result | commit |
```

新增 `tag` 列（仅 maintenance 任务有值）：
```
| time | task_id | type | source | tag | title | result | commit |
```

- `tag` 字段：来自 `_MAINTENANCE_CANDIDATES` 中的 `maintenance_tag`（如 `security`、`testing`、`docs`）
- 非 maintenance 任务（idea/feature/improve）的 tag 留空
- post-feature maintenance 的动态任务（`回归验证`、`补测试与文档`）也需要 tag，见后文

### 2. tag 版本计数

在 `choose_next_task` 中，维护 `tag→version` 映射：

```python
def _maintenance_tag_versions(done_log_entries: list[dict]) -> dict[str, int]:
    """Parse Done Log and return {tag: version_count} mapping.
    
    version = count of times this tag appears in Done Log.
    So if 'security' appears 2 times, next security task → v3.
    """
    counts: dict[str, int] = {}
    for entry in done_log_entries:
        tag = entry.get("tag", "")
        if tag:
            counts[tag] = counts.get(tag, 0) + 1
    return counts  # {'security': 2, 'testing': 1, ...}
```

版本号规则：`version = count + 1`（出现 2 次 → 下次是 v3）。

### 3. 标题生成

```python
def _maintenance_title(candidate: dict, version: int) -> str:
    if version == 1:
        return candidate["title"]  # 原标题
    return f"{candidate['title']} v{version}"  # e.g., "进行安全漏洞审计 v2"
```

### 4. 内容差异化（scope 动态化）

`_read_project_context` 已实现：
- 最近 N 个 commit 的变更文件列表
- 每个变更文件的行数
- 关键模块列表

在 `_make_task` 生成 maintenance 候选时：
1. 取当前项目的变更文件列表（来自 `_read_project_context`）
2. 按 `maintenance_tag` 分配关注维度：
   - `security` → 聚焦最近变更的文件 + 第三方依赖
   - `testing` → 聚焦新增/修改的模块对应的测试文件
   - `docs` → 聚焦最近变更的模块对应的文档
   - `performance` → 聚焦变更最频繁的模块
   - `cleanup` → 聚焦代码行数增长最快的模块
3. 生成差异化的 scope 和 execution_plan

具体做法：在 `_MAINTENANCE_CANDIDATES` 的 `scope` 和 `execution_plan` 字段中，用占位符标记 `{{RECENT_CHANGED_FILES}}`，在 `_make_task` 时替换为实际的变更文件列表。

### 5. post-feature maintenance 动态任务的 tag

`_build_maintenance_candidates` 生成的动态任务：
- `回归验证并修复：{anchor}` → tag = `regression`
- `补测试与文档：{anchor}` → tag = `testing`

这两个已有 `maintenance_tag` 语义，直接映射即可。

### 6. sticky 逻辑调整

**maintenance 任务不再使用 title-based sticky 屏蔽。**

maintenance mode 下的去重完全依赖 `tag_version` 机制：
- 同一 tag v2 被选走后，v2 不再出现（Done Log 已有记录）
- 但 v3 可以出现（版本号不同，title 不同）
- 不存在「永久屏蔽」的问题

**post-feature maintenance 的逻辑保持不变：**
- `maintenance_remaining` 计数器驱动
- `maintenance_anchor_title` 作为任务标题前缀
- 这是针对单个 feature 完成后的短期维护轮，与 maintenance mode 无关

### 7. Rhythm 计数器处理

当 `maintenance_mode=True` 时：
- `improves_since_last_idea` **不累加**
- 避免 maintenance 任务做多了意外触发 idea 生成
- 计数器的状态保留，`a-maintenance off` 后继续

### 8. CLI 影响

- `a-maintenance on` → 写入 `maintenance_mode=True` 到 RoadmapState
- `a-maintenance off` → 写入 `maintenance_mode=False`，恢复 normal 行为
- `a-status` → 显示 `maintenance_mode: on/off` 状态

---

## 实现计划

### Phase 1: Done Log Schema + tag 解析
- 修改 `roadmap.py` 的 `append_done_log` 支持新增 `tag` 列
- 新增 `_parse_done_log_with_tags` 函数，返回带 tag 的 entries
- 兼容旧格式（无 tag 列的 Done Log）—— 缺失 tag 视为空

### Phase 2: tag 版本计数 + 标题生成
- 在 `task_planner.py` 新增 `_maintenance_tag_versions()`
- 修改 `choose_next_task` 中 maintenance pool 的候选生成逻辑
- 实现 `_maintenance_title()` 标题生成函数

### Phase 3: 内容差异化
- 修改 `_read_project_context` 保留变更文件列表
- 在 `_make_task` 时注入差异化的 scope/execution_plan

### Phase 4: post-feature maintenance tag 映射 + Rhythm 调整
- `_build_maintenance_candidates` 生成的动态任务加上 tag
- `choose_next_task` 中 maintenance_mode=True 时跳过 `improves_since_last_idea` 计数

### Phase 5: 测试
- 验证 maintenance mode 下自由轮转（≥15 个任务全部能依次出现）
- 验证同一 tag 重复出现时标题带版本号
- 验证 `a-maintenance off` 恢复 normal 模式

---

## 兼容性

- 旧 Done Log（无 tag 列）向前兼容，缺失 tag 视为空
- `a-maintenance on` 前已存在的 maintenance 历史记录，tag 信息缺失，但这批任务本来就不适合继续轮转，无需迁移