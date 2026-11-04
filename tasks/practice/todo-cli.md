---
id: todo-cli
title: 待办事项命令行工具
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: todo
  data_file: todo.json
---

# 背景

一个给个人使用的待办事项工具。用户在终端里添加、查看、完成和删除待办，数据保存在当前目录的 `todo.json` 中，下次运行时仍然存在。

# 功能需求

- **FR-001** 添加待办：`todo add <标题> [--due YYYY-MM-DD]`。成功时输出 `Added #<编号>`。编号从 1 开始递增，删除后的编号不再复用。
- **FR-002** 列出待办：`todo list`。按编号升序每行输出一条，格式为 `#<编号> [ ] <标题>`，已完成的为 `#<编号> [x] <标题>`；有截止日期时在行末追加 ` (due YYYY-MM-DD)`。没有任何待办时输出 `No tasks`。
- **FR-003** 完成待办：`todo done <编号>`。成功时输出 `Completed #<编号>`。
- **FR-004** 删除待办：`todo remove <编号>`。成功时输出 `Removed #<编号>`。
- **FR-005** 只看未完成：`todo list --pending` 只列出未完成的待办，格式同 FR-002；没有未完成的待办时输出 `No tasks`。
- **FR-006** 日期校验：`--due` 的值必须是真实存在的日期且格式为 `YYYY-MM-DD`，否则不添加待办，并按 NFR-001 报错。
- **FR-007** 持久化：所有数据保存在当前工作目录下的 `todo.json`；文件不存在时视为没有待办。

# 非功能需求

- **NFR-001** 所有错误信息输出到 stderr，退出码为 1。对不存在的编号执行 `done` 或 `remove` 属于错误。
- **NFR-002** `todo --help` 输出用法说明，退出码为 0。
- **NFR-003** 标题可以包含中文和空格（作为一个参数传入）。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-002, FR-007]
  steps:
    - run: [add, "买牛奶", --due, "2026-12-01"]
      expect: {exit: 0, stdout_contains: ["Added #1"]}
    - run: [add, "写周报"]
      expect: {exit: 0, stdout_contains: ["Added #2"]}
    - run: [list]
      expect: {exit: 0, stdout_contains: ["#1 [ ] 买牛奶 (due 2026-12-01)", "#2 [ ] 写周报"]}
- id: AS-002
  covers: [FR-002]
  steps:
    - run: [list]
      expect: {exit: 0, stdout_contains: ["No tasks"]}
- id: AS-003
  covers: [FR-003, FR-005]
  steps:
    - run: [add, "a"]
      expect: {exit: 0}
    - run: [add, "b"]
      expect: {exit: 0}
    - run: [done, "1"]
      expect: {exit: 0, stdout_contains: ["Completed #1"]}
    - run: [list]
      expect: {exit: 0, stdout_contains: ["#1 [x] a", "#2 [ ] b"]}
    - run: [list, --pending]
      expect: {exit: 0, stdout_contains: ["#2 [ ] b"], stdout_not_contains: ["#1"]}
- id: AS-004
  covers: [FR-004, FR-001]
  steps:
    - run: [add, "a"]
      expect: {exit: 0}
    - run: [add, "b"]
      expect: {exit: 0}
    - run: [remove, "2"]
      expect: {exit: 0, stdout_contains: ["Removed #2"]}
    - run: [add, "c"]
      expect: {exit: 0, stdout_contains: ["Added #3"]}
    - run: [list]
      expect: {exit: 0, stdout_contains: ["#1 [ ] a", "#3 [ ] c"], stdout_not_contains: ["#2"]}
- id: AS-005
  covers: [FR-006]
  steps:
    - run: [add, "x", --due, "2026-02-30"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [add, "y", --due, "2026/03/01"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [list]
      expect: {exit: 0, stdout_contains: ["No tasks"]}
- id: AS-006
  covers: [FR-003, FR-004]
  steps:
    - run: [done, "9"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [remove, "9"]
      expect: {exit: 1, stderr_nonempty: true}
- id: AS-007
  covers: [FR-005]
  steps:
    - run: [add, "a"]
      expect: {exit: 0}
    - run: [done, "1"]
      expect: {exit: 0}
    - run: [list, --pending]
      expect: {exit: 0, stdout_contains: ["No tasks"]}
```
