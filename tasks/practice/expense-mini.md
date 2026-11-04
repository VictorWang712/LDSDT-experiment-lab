---
id: expense-mini
title: 个人记账工具
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: expense
  data_file: expense.json
---

# 背景

一个记录日常开销的命令行工具。用户记录每笔支出的金额、类别、日期和备注，可以按月份或类别查看明细，并为类别设置月度预算。数据保存在当前目录的 `expense.json`。

# 功能需求

- **FR-001** 记账：`expense add <金额> <类别> --date YYYY-MM-DD [--note <备注>]`，成功时输出 `Added #<编号>`。编号从 1 开始递增，删除后不复用。金额必须大于 0 且最多两位小数；日期必须是真实日期。
- **FR-002** 金额计算必须精确，不能出现浮点误差（例如 0.1 与 0.2 之和是 0.30）。所有输出中的金额固定保留两位小数。
- **FR-003** 明细：`expense list [--month YYYY-MM] [--category <类别>]` 每行输出 `#<编号> <日期> <类别> <金额>`，有备注时在行末追加 ` - <备注>`。按日期升序、同日期按编号升序。两个过滤条件可以同时使用。没有符合条件的记录时输出 `No expenses`。
- **FR-004** 删除：`expense delete <编号>`，成功时输出 `Deleted #<编号>`。
- **FR-005** 预算：`expense budget <类别> <金额>` 设置（或覆盖）该类别的月度预算，成功时输出 `Budget set for <类别>`。
- **FR-006** 月度汇总：`expense summary --month YYYY-MM` 按该月各类别的合计金额降序（相同时按类别名升序）每行输出 `<类别>: <合计>`；设有预算的类别输出为 `<类别>: <合计> / <预算>`，合计超过预算时在行末追加 ` OVER`。最后一行输出 `Total: <该月合计>`。该月没有记录时只输出 `Total: 0.00`。
- **FR-007** 类别名区分大小写，不能包含空格。

# 非功能需求

- **NFR-001** 所有错误信息输出到 stderr，退出码为 1，且不修改已保存的数据。对不存在的编号执行 `delete` 属于错误。
- **NFR-002** `expense --help` 输出用法说明，退出码为 0。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-003]
  steps:
    - run: [add, "12.5", food, --date, "2026-11-03", --note, "午饭"]
      expect: {exit: 0, stdout_contains: ["Added #1"]}
    - run: [add, "30", transport, --date, "2026-11-01"]
      expect: {exit: 0, stdout_contains: ["Added #2"]}
    - run: [list]
      expect: {exit: 0, stdout_regex: "\\A#2 2026-11-01 transport 30\\.00\\n#1 2026-11-03 food 12\\.50 - 午饭\\n?\\Z"}
- id: AS-002
  covers: [FR-002, FR-006]
  steps:
    - run: [add, "0.1", food, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [add, "0.2", food, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [summary, --month, "2026-11"]
      expect: {exit: 0, stdout_regex: "\\Afood: 0\\.30\\nTotal: 0\\.30\\n?\\Z"}
- id: AS-003
  covers: [FR-003, FR-007]
  steps:
    - run: [add, "10", food, --date, "2026-10-31"]
      expect: {exit: 0}
    - run: [add, "20", food, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [add, "5", Food, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [list, --month, "2026-11", --category, food]
      expect: {exit: 0, stdout_regex: "\\A#2 2026-11-01 food 20\\.00\\n?\\Z"}
    - run: [list, --month, "2026-12"]
      expect: {exit: 0, stdout_contains: ["No expenses"]}
- id: AS-004
  covers: [FR-005, FR-006]
  steps:
    - run: [add, "80", food, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [add, "40", food, --date, "2026-11-05"]
      expect: {exit: 0}
    - run: [add, "200", rent, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [add, "15", book, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [budget, food, "100"]
      expect: {exit: 0, stdout_contains: ["Budget set for food"]}
    - run: [budget, rent, "200"]
      expect: {exit: 0}
    - run: [summary, --month, "2026-11"]
      expect: {exit: 0, stdout_regex: "\\Arent: 200\\.00 / 200\\.00\\nfood: 120\\.00 / 100\\.00 OVER\\nbook: 15\\.00\\nTotal: 335\\.00\\n?\\Z"}
- id: AS-005
  covers: [FR-006]
  steps:
    - run: [summary, --month, "2026-01"]
      expect: {exit: 0, stdout_regex: "\\ATotal: 0\\.00\\n?\\Z"}
- id: AS-006
  covers: [FR-001, FR-004]
  steps:
    - run: [add, "0", food, --date, "2026-11-01"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [add, "1.234", food, --date, "2026-11-01"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [add, "5", food, --date, "2026-11-31"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [add, "5", food, --date, "2026-11-30"]
      expect: {exit: 0, stdout_contains: ["Added #1"]}
    - run: [delete, "1"]
      expect: {exit: 0, stdout_contains: ["Deleted #1"]}
    - run: [delete, "1"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [add, "6", food, --date, "2026-11-30"]
      expect: {exit: 0, stdout_contains: ["Added #2"]}
```
