---
id: timesheet
title: 工时统计
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: ts
  data_dir: .timesheet
---

# 背景

一家小型设计工作室按小时向客户收费，也按小时给员工发工资。项目经理需要一个命令行工具：登记员工和项目，记录每段工作的起止时间（可以跨午夜），按周统计工时与加班，计算周薪，查看项目预算的使用情况，并能从考勤系统导出的 CSV 批量导入记录。

所有数据保存在当前工作目录下的 `.timesheet/` 目录中，目录或文件不存在时视为没有任何数据。

# 规则

- **R-001** 日期写作 `YYYY-MM-DD`，必须是真实存在的日期，否则报错 `error: invalid date <原值>`（退出码 2）。
- **R-002** 时刻写作 `HH:MM`（两位小时、两位分钟，00:00 到 23:59），否则报错 `error: invalid time <原值>`（退出码 2）。
- **R-003** 工号是大写字母 `E` 加 3 位数字（如 `E001`），否则报错 `error: invalid id <原值>`；项目代码是 3 到 6 个大写英文字母（如 `ABC`），否则报错 `error: invalid project code <原值>`。两者退出码都是 2。姓名与项目名称先去掉首尾空白，为空时报错 `error: empty name`（退出码 2）。
- **R-004** 一条工时记录有开始时刻与结束时刻。结束时刻早于开始时刻表示跨过午夜、在第二天结束；两者相同报错 `error: zero duration`（退出码 2）。一条记录属于它的开始日期。
- **R-005** 每条记录的时长先按 15 分钟取整再参与任何统计：时长除以 15 分钟的余数小于 8 分钟时舍去，否则进到下一个 15 分钟（例如 2 小时 37 分记为 2:30，2 小时 38 分记为 2:45，7 分钟记为 0:00）。以下所说「工时」都指取整后的时长。
- **R-006** 时长一律显示为 `<小时>:<两位分钟>`，小时不补零（如 `0:15`、`8:00`、`41:30`）。
- **R-007** 金额（时薪、工资）是正数，最多两位小数；输出保留两位小数，计算时使用十进制精确运算，需要舍入时四舍五入到分。
- **R-008** 一周从周一开始到周日结束。
- **R-009** 错误信息一律输出到 stderr，格式为 `error: <说明>`，stdout 不输出任何内容。退出码：2 表示参数错误（包括命令行用法错误），3 表示员工、项目、记录或文件不存在，4 表示违反业务规则。一条命令有多个错误时，先按参数在命令中出现的顺序检查参数格式（R-001 至 R-004），再检查员工、项目是否存在，最后按各 FR 中列出的顺序检查业务规则，只报告第一个。员工不存在：`error: employee <工号> not found`；项目不存在：`error: project <代码> not found`。
- **R-010** 列表输出时各列之间用两个空格分隔；数量为 1 时用单数（`1 entry`），否则用复数（`3 entries`）。
- **R-011** 命令行中的整数参数（如编号、数量、上限）按十进制解析，允许前导零，例如 `ts delete 01` 等同于 `ts delete 1`。

# 功能需求

## 员工与项目

- **FR-001** `ts employee add <工号> <姓名> --rate <时薪>` 登记员工，`--rate` 必填，不符合 R-007 时报错 `error: invalid rate <原值>`（退出码 2）。成功时输出 `Employee <工号> added`；工号已存在时报错 `error: employee <工号> already exists`（退出码 4）。
- **FR-002** `ts employee list` 每行输出 `<工号>  <姓名>  <时薪>`，按工号升序；没有员工时输出 `No employees`。
- **FR-003** `ts project add <代码> <名称> [--budget <小时数>]` 登记项目，预算是正整数小时，否则报错 `error: invalid budget <原值>`（退出码 2）。成功时输出 `Project <代码> added`；代码已存在时报错 `error: project <代码> already exists`（退出码 4）。
- **FR-004** `ts project close <代码>` 关闭项目，输出 `Project <代码> closed`。项目已关闭时报错 `error: project <代码> already closed`（退出码 4）。已关闭的项目不能再记录工时，但已有记录照常参与统计。
- **FR-005** `ts project list` 每行输出 `<代码>  <名称>  <open|closed>  <该项目全部工时>`，按代码升序；没有项目时输出 `No projects`。

## 工时记录

- **FR-006** `ts log <工号> <项目代码> <日期> <开始> <结束> [--note <备注>]` 记录一段工作，成功时输出 `Logged #<编号> (<取整后时长>)`。编号从 1 开始递增，删除后不复用。业务规则按以下顺序检查，均为退出码 4：
  1. 项目已关闭：`error: project <代码> is closed`
  2. 未取整的时长超过 12 小时（恰好 12 小时可以）：`error: entry longer than 12 hours`
  3. 与同一员工的另一条记录（任何项目）在实际时间上重叠：`error: overlaps entry #<编号>`（有多条时报编号最小的）。一条的结束时刻恰好等于另一条的开始时刻不算重叠。
- **FR-007** `ts delete <编号>` 删除记录，输出 `Deleted #<编号>`。编号不是正整数时报错 `error: invalid entry <原值>`（退出码 2）；记录不存在时报错 `error: entry <编号> not found`（退出码 3）。
- **FR-008** `ts entries <工号> [--from <日期>] [--to <日期>]` 列出员工开始日期在范围内（含两端，省略表示不限）的记录，每行 `#<编号>  <开始日期>  <开始>-<结束>  <项目代码>  <取整后时长>`，跨午夜的记录结束时刻后加 `+1`（如 `22:00-01:30+1`）。按开始的日期时刻升序，相同时按编号升序。`--from` 晚于 `--to` 时报错 `error: invalid range`（退出码 2）。没有记录时输出 `No entries`。
- **FR-009** `ts import <文件>` 从 UTF-8 编码的 CSV 文件导入记录。第一行必须恰好是 `employee,project,date,start,end,note`，否则报错 `error: bad header`（退出码 2）；文件不存在时报错 `error: file not found: <文件>`（退出码 3）。之后每个非空行是一条记录（字段可以用双引号包住以包含逗号），按文件顺序依次编号。有问题的行跳过，并在 stderr 输出 `line <行号>: <原因>`（行号为文件中的物理行号，表头是第 1 行），原因按以下顺序检查：`wrong number of fields`、`unknown employee`、`unknown project`、`invalid date`、`invalid time`、`zero duration`、`project closed`、`longer than 12 hours`、`overlaps entry #<编号>`（与已有记录或本文件前面已导入的行重叠）。最后输出 `Imported <K> entries, skipped <M>`（K 为 1 时为 `1 entry`），退出码 0。
- **FR-010** `ts export <文件> [--from <日期>] [--to <日期>]` 把范围内（规则同 FR-008）的全部记录写入 CSV 文件（覆盖已有文件），表头 `id,employee,project,date,start,end,minutes`，minutes 为取整后的分钟数，按开始的日期时刻升序、相同时按编号升序。输出 `Exported <N> entries`（N 为 1 时为 `1 entry`）。

## 统计

- **FR-011** `ts week <工号> <日期>` 输出该日期所在周（R-008）的工时：先是 7 行，每行 `<星期>  <日期>  <当天工时>`，星期依次为 `Mon`、`Tue`、`Wed`、`Thu`、`Fri`、`Sat`、`Sun`，没有记录的日子为 `0:00`；然后是 `Total  <本周工时>` 与 `Overtime  <加班工时>` 两行。
- **FR-012** 加班的计算：周六、周日的工时全部算加班；周一至周五的工时合计超过 40:00 的部分也算加班。其余为正常工时。
- **FR-013** `ts pay <工号> <日期>` 计算该日期所在周的工资，输出三行：`Regular  <正常工时>  <正常工资>`、`Overtime  <加班工时>  <加班工资>`、`Total  <合计>`。正常工资 = 正常工时（小时）× 时薪，加班工资 = 加班工时（小时）× 时薪 × 1.5，两者各自四舍五入到分，合计为两者之和。
- **FR-014** `ts project report <代码>` 按员工汇总该项目的全部工时，每行 `<工号>  <姓名>  <工时>`，按工时降序、相同时按工号升序；然后是 `Total  <合计>`；项目有预算时再输出 `Budget  <预算工时>  used <百分比>%`，百分比 = 合计 ÷ 预算 × 100，保留一位小数并四舍五入，超过 100% 时在行末再加两个空格和 `OVER`。项目没有任何记录时只输出 `No entries`。
- **FR-015** `ts summary --from <日期> --to <日期>` 按项目代码升序列出范围内（按开始日期，含两端）工时大于 0 的项目，每行 `<代码>  <工时>`，最后一行 `Total  <合计>`。`--from` 晚于 `--to` 时报错 `error: invalid range`（退出码 2）；范围内没有工时时输出 `No entries`。

# 非功能需求

- **NFR-001** `ts --help` 输出用法说明，退出码 0。
- **NFR-002** 命令成功时退出码为 0。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-002, R-007]
  steps:
    - run: [employee, list]
      expect: {exit: 0, stdout_contains: ["No employees"]}
    - run: [employee, add, E002, 李四, --rate, "75.5"]
      expect: {exit: 0, stdout_contains: ["Employee E002 added"]}
    - run: [employee, add, E001, " 张三 ", --rate, "80"]
      expect: {exit: 0}
    - run: [employee, list]
      expect: {exit: 0, stdout_regex: "^E001  张三  80.00\\nE002  李四  75.50$"}
- id: AS-002
  covers: [FR-001, R-003, R-007, R-009]
  steps:
    - run: [employee, add, e001, 张三, --rate, "80"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [employee, add, E001, 张三, --rate, "0"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [employee, add, E001, 张三, --rate, "12.345"]
      expect: {exit: 2}
    - run: [employee, add, E001, 张三]
      expect: {exit: 2}
    - run: [employee, add, E001, "  ", --rate, "10"]
      expect: {exit: 2}
    - run: [employee, add, E001, 张三, --rate, "10"]
      expect: {exit: 0}
    - run: [employee, add, E001, 王五, --rate, "10"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [employee, add, E001, 王五, --rate, "10"]
      expect: {stdout_not_contains: ["added"]}
- id: AS-003
  covers: [FR-003, FR-005, R-003]
  steps:
    - run: [project, list]
      expect: {exit: 0, stdout_contains: ["No projects"]}
    - run: [project, add, ABC, 官网改版, --budget, "30"]
      expect: {exit: 0, stdout_contains: ["Project ABC added"]}
    - run: [project, add, XY, 太短]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [project, add, ABCDEFG, 太长]
      expect: {exit: 2}
    - run: [project, add, abc, 小写]
      expect: {exit: 2}
    - run: [project, add, GHI, 预算, --budget, "0"]
      expect: {exit: 2}
    - run: [project, add, GHI, 预算, --budget, "1.5"]
      expect: {exit: 2}
    - run: [project, add, DEF, 内部]
      expect: {exit: 0}
    - run: [project, add, ABC, 重复]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [project, list]
      expect: {exit: 0, stdout_regex: "^ABC  官网改版  open  0:00\\nDEF  内部  open  0:00$"}
- id: AS-004
  covers: [FR-004, FR-005, FR-006]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [project, close, ABC]
      expect: {exit: 0, stdout_contains: ["Project ABC closed"]}
    - run: [project, close, ABC]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [project, close, ZZZ]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [log, E001, ABC, "2026-11-03", "09:00", "10:00"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [project, list]
      expect: {exit: 0, stdout_contains: ["ABC  官网  closed  1:00"]}
- id: AS-005
  covers: [FR-006, FR-005, R-005, R-006]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "11:37", --note, 首页]
      expect: {exit: 0, stdout_contains: ["Logged #1 (2:30)"]}
    - run: [log, E001, ABC, "2026-11-02", "13:00", "15:38"]
      expect: {exit: 0, stdout_contains: ["Logged #2 (2:45)"]}
    - run: [log, E001, ABC, "2026-11-02", "16:00", "16:07"]
      expect: {exit: 0, stdout_contains: ["Logged #3 (0:00)"]}
    - run: [log, E001, ABC, "2026-11-02", "17:00", "17:08"]
      expect: {exit: 0, stdout_contains: ["Logged #4 (0:15)"]}
    - run: [project, list]
      expect: {exit: 0, stdout_contains: ["ABC  官网  open  5:30"]}
- id: AS-006
  covers: [FR-006, R-001, R-002, R-004, R-009]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-31", "09:00", "10:00"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [log, E001, ABC, "2026-11-02", "9:00", "10:00"]
      expect: {exit: 2}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "24:00"]
      expect: {exit: 2}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "09:00"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [log, E009, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [log, E001, ZZZ, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 3}
    - run: [log, E009, ZZZ, "2026-11-02", "09:00", "09:00"]
      expect: {exit: 2}
    - run: [entries, E001]
      expect: {exit: 0, stdout_contains: ["No entries"]}
- id: AS-007
  covers: [FR-006, FR-008, R-004]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "22:00", "01:30"]
      expect: {exit: 0, stdout_contains: ["Logged #1 (3:30)"]}
    - run: [log, E001, ABC, "2026-11-03", "01:00", "02:00"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [log, E001, ABC, "2026-11-03", "01:30", "02:00"]
      expect: {exit: 0, stdout_contains: ["Logged #2 (0:30)"]}
    - run: [entries, E001]
      expect: {exit: 0, stdout_regex: "^#1  2026-11-02  22:00-01:30\\+1  ABC  3:30\\n#2  2026-11-03  01:30-02:00  ABC  0:30$"}
- id: AS-008
  covers: [FR-006]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [employee, add, E002, 李四, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [project, add, DEF, 内部]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E001, DEF, "2026-11-02", "11:59", "13:00"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [log, E001, DEF, "2026-11-02", "08:00", "09:00"]
      expect: {exit: 0, stdout_contains: ["Logged #2"]}
    - run: [log, E002, DEF, "2026-11-02", "11:00", "13:00"]
      expect: {exit: 0, stdout_contains: ["Logged #3"]}
    - run: [log, E001, DEF, "2026-11-01", "20:00", "09:30"]
      expect: {exit: 4}
- id: AS-009
  covers: [FR-006]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "08:00", "20:00"]
      expect: {exit: 0, stdout_contains: ["Logged #1 (12:00)"]}
    - run: [log, E001, ABC, "2026-11-03", "08:00", "20:01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [log, E001, ABC, "2026-11-04", "20:00", "08:01"]
      expect: {exit: 4}
    - run: [log, E001, ABC, "2026-11-04", "20:00", "08:00"]
      expect: {exit: 0, stdout_contains: ["Logged #2 (12:00)"]}
- id: AS-010
  covers: [FR-007, FR-006]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "10:00", "11:00"]
      expect: {exit: 0}
    - run: [delete, "1"]
      expect: {exit: 0, stdout_contains: ["Deleted #1"]}
    - run: [delete, "1"]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [delete, abc]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 0, stdout_contains: ["Logged #3 (1:00)"]}
    - run: [entries, E001]
      expect: {exit: 0, stdout_regex: "^#3  2026-11-02  09:00-10:00  ABC  1:00\\n#2  2026-11-02  10:00-11:00  ABC  1:00$"}
- id: AS-011
  covers: [FR-008]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [employee, add, E002, 李四, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-03", "10:00", "11:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "14:00", "15:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-05", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [entries, E001, --from, "2026-11-02", --to, "2026-11-03"]
      expect: {exit: 0, stdout_regex: "^#3  2026-11-02  09:00-10:00  ABC  1:00\\n#2  2026-11-02  14:00-15:00  ABC  1:00\\n#1  2026-11-03  10:00-11:00  ABC  1:00$"}
    - run: [entries, E001, --from, "2026-11-04"]
      expect: {exit: 0, stdout_contains: ["#4  2026-11-05"], stdout_not_contains: ["#1", "#2", "#3"]}
    - run: [entries, E001, --from, "2026-11-04", --to, "2026-11-03"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [entries, E002]
      expect: {exit: 0, stdout_contains: ["No entries"]}
    - run: [entries, E404]
      expect: {exit: 3}
- id: AS-012
  covers: [FR-011, FR-012, R-008]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "17:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-03", "09:00", "19:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-04", "09:00", "21:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-05", "09:00", "19:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-06", "09:00", "11:22"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-07", "10:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-08", "22:00", "00:30"]
      expect: {exit: 0}
    - run: [week, E001, "2026-11-05"]
      expect: {exit: 0, stdout_regex: "^Mon  2026-11-02  8:00\\nTue  2026-11-03  10:00\\nWed  2026-11-04  12:00\\nThu  2026-11-05  10:00\\nFri  2026-11-06  2:15\\nSat  2026-11-07  2:00\\nSun  2026-11-08  2:30\\nTotal  46:45\\nOvertime  6:45$"}
    - run: [week, E001, "2026-11-09"]
      expect: {exit: 0, stdout_contains: ["Mon  2026-11-09  0:00", "Sun  2026-11-15  0:00", "Total  0:00", "Overtime  0:00"]}
- id: AS-013
  covers: [FR-011, FR-012]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-07", "09:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "11:00"]
      expect: {exit: 0}
    - run: [week, E001, "2026-11-08"]
      expect: {exit: 0, stdout_contains: ["Mon  2026-11-02  2:00", "Sat  2026-11-07  3:00", "Total  5:00", "Overtime  3:00"]}
- id: AS-014
  covers: [FR-013, FR-012, R-007]
  steps:
    - run: [employee, add, E002, 李四, --rate, "75.5"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E002, ABC, "2026-11-02", "09:00", "19:08"]
      expect: {exit: 0, stdout_contains: ["(10:15)"]}
    - run: [log, E002, ABC, "2026-11-03", "09:00", "19:15"]
      expect: {exit: 0}
    - run: [log, E002, ABC, "2026-11-04", "09:00", "19:15"]
      expect: {exit: 0}
    - run: [log, E002, ABC, "2026-11-05", "09:00", "19:15"]
      expect: {exit: 0}
    - run: [log, E002, ABC, "2026-11-07", "10:00", "11:15"]
      expect: {exit: 0}
    - run: [pay, E002, "2026-11-04"]
      expect: {exit: 0, stdout_regex: "^Regular  40:00  3020.00\\nOvertime  2:15  254.81\\nTotal  3274.81$"}
    - run: [pay, E002, "2026-11-10"]
      expect: {exit: 0, stdout_regex: "^Regular  0:00  0.00\\nOvertime  0:00  0.00\\nTotal  0.00$"}
- id: AS-015
  covers: [FR-013]
  steps:
    - run: [employee, add, E001, 张三, --rate, "33.33"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-04", "09:00", "10:52"]
      expect: {exit: 0, stdout_contains: ["(1:45)"]}
    - run: [pay, E001, "2026-11-04"]
      expect: {exit: 0, stdout_regex: "^Regular  1:45  58.33\\nOvertime  0:00  0.00\\nTotal  58.33$"}
    - run: [pay, E404, "2026-11-04"]
      expect: {exit: 3, stderr_nonempty: true}
- id: AS-016
  covers: [FR-014]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [employee, add, E002, 李四, --rate, "80"]
      expect: {exit: 0}
    - run: [employee, add, E003, 王五, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网, --budget, "10"]
      expect: {exit: 0}
    - run: [project, report, ABC]
      expect: {exit: 0, stdout_contains: ["No entries"]}
    - run: [log, E003, ABC, "2026-11-02", "09:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E002, ABC, "2026-11-03", "09:00", "13:00"]
      expect: {exit: 0}
    - run: [project, report, ABC]
      expect: {exit: 0, stdout_regex: "^E002  李四  4:00\\nE001  张三  3:00\\nE003  王五  3:00\\nTotal  10:00\\nBudget  10:00  used 100.0%$"}
    - run: [log, E001, ABC, "2026-11-04", "09:00", "09:20"]
      expect: {exit: 0}
    - run: [project, report, ABC]
      expect: {exit: 0, stdout_contains: ["E001  张三  3:15", "Total  10:15", "Budget  10:00  used 102.5%  OVER"]}
- id: AS-017
  covers: [FR-014]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, DEF, 内部, --budget, "3"]
      expect: {exit: 0}
    - run: [project, add, GHI, 无预算]
      expect: {exit: 0}
    - run: [log, E001, DEF, "2026-11-02", "09:00", "09:30"]
      expect: {exit: 0}
    - run: [log, E001, GHI, "2026-11-02", "10:00", "11:00"]
      expect: {exit: 0}
    - run: [project, report, DEF]
      expect: {exit: 0, stdout_contains: ["Total  0:30", "Budget  3:00  used 16.7%"], stdout_not_contains: ["OVER"]}
    - run: [project, report, GHI]
      expect: {exit: 0, stdout_contains: ["E001  张三  1:00", "Total  1:00"], stdout_not_contains: ["Budget"]}
- id: AS-018
  covers: [FR-015]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, DEF, 内部]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [project, add, XYZ, 闲置]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [log, E001, DEF, "2026-11-03", "09:00", "11:00"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-10", "09:00", "12:00"]
      expect: {exit: 0}
    - run: [log, E001, XYZ, "2026-11-03", "12:00", "12:05"]
      expect: {exit: 0}
    - run: [summary, --from, "2026-11-01", --to, "2026-11-05"]
      expect: {exit: 0, stdout_regex: "^ABC  1:00\\nDEF  2:00\\nTotal  3:00$"}
    - run: [summary, --from, "2026-11-06", --to, "2026-11-09"]
      expect: {exit: 0, stdout_contains: ["No entries"]}
    - run: [summary, --from, "2026-11-06", --to, "2026-11-05"]
      expect: {exit: 2, stderr_nonempty: true}
- id: AS-019
  covers: [FR-009, FR-008]
  files:
    entries.csv: |
      employee,project,date,start,end,note
      E001,ABC,2026-11-02,09:00,10:00,周会
      E009,ABC,2026-11-02,09:00,10:00,
      E001,ZZZ,2026-11-02,09:00,10:00,
      E001,ABC,2026-11-31,09:00,10:00,
      E001,ABC,2026-11-03,9:00,10:00,

      E001,ABC,2026-11-03,09:00,09:00,
      E001,OLD,2026-11-03,09:00,10:00,
      E001,ABC,2026-11-03,08:00,20:30,
      E001,ABC,2026-11-02,09:30,10:30,
      E001,ABC,2026-11-02,10:00,11:00
      E001,ABC,2026-11-02,10:00,11:00,"会议,讨论"
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [project, add, OLD, 旧项目]
      expect: {exit: 0}
    - run: [project, close, OLD]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-04", "09:00", "10:00"]
      expect: {exit: 0}
    - run: [import, entries.csv]
      expect: {exit: 0, stdout_contains: ["Imported 2 entries, skipped 9"]}
    - run: [entries, E001]
      expect: {exit: 0, stdout_regex: "^#2  2026-11-02  09:00-10:00  ABC  1:00\\n#3  2026-11-02  10:00-11:00  ABC  1:00\\n#1  2026-11-04  09:00-10:00  ABC  1:00$"}
- id: AS-020
  covers: [FR-009, R-009]
  files:
    entries.csv: |
      employee,project,date,start,end,note
      E001,ABC,2026-11-02,09:00,10:00,
      E009,ABC,2026-11-02,09:00,10:00,
    one.csv: |
      employee,project,date,start,end,note
      E001,ABC,2026-11-05,09:00,10:00,
    bad.csv: |
      employee,project,date,start,end
      E001,ABC,2026-11-02,09:00,10:00
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [import, entries.csv]
      expect: {exit: 0, stdout_contains: ["Imported 1 entry, skipped 1"], stderr_nonempty: true}
    - run: [import, bad.csv]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [import, missing.csv]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [import, one.csv]
      expect: {exit: 0, stdout_contains: ["Imported 1 entry, skipped 0"]}
- id: AS-021
  covers: [FR-010]
  steps:
    - run: [employee, add, E001, 张三, --rate, "80"]
      expect: {exit: 0}
    - run: [project, add, ABC, 官网]
      expect: {exit: 0}
    - run: [export, out.csv]
      expect: {exit: 0, stdout_contains: ["Exported 0 entries"]}
    - run: [log, E001, ABC, "2026-11-03", "10:00", "10:52"]
      expect: {exit: 0}
    - run: [log, E001, ABC, "2026-11-02", "23:00", "00:10"]
      expect: {exit: 0}
    - run: [export, out.csv]
      expect: {exit: 0, stdout_contains: ["Exported 2 entries"]}
    - run: [export, out.csv, --from, "2026-11-03", --to, "2026-11-03"]
      expect: {exit: 0, stdout_contains: ["Exported 1 entry"]}
    - run: [import, out.csv]
      expect: {exit: 2}
- id: AS-022
  covers: [NFR-001, FR-002]
  steps:
    - run: [--help]
      expect: {exit: 0}
    - run: [employee, list]
      expect: {exit: 0, stdout_contains: ["No employees"]}
```
