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
- [ ] README.md 中命令示例与实际 CLI 输出一致
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
