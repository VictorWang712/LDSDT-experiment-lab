---
id: gradebook-mini
title: 课程成绩册
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: gradebook
  data_file: gradebook.json
---

# 背景

助教用来记录学生各门课程成绩的命令行工具。可以逐条录入，也可以从 CSV 批量导入，然后查看个人成绩单、课程排名和统计信息。数据保存在当前目录的 `gradebook.json`。

# 功能需求

- **FR-001** 添加学生：`gradebook add-student <学号> <姓名>`，成功时输出 `Added student <学号>`。学号已存在时报错。
- **FR-002** 录入成绩：`gradebook record <学号> <课程> <分数>`，成功时输出 `Recorded <学号> <课程> <分数>`。分数为 0 到 100 之间（含两端）的数，最多一位小数；同一学生同一课程再次录入时覆盖原成绩。学号不存在或分数不合法时报错。
- **FR-003** 分数显示：所有输出中的分数去掉多余的 0：`90.0` 显示为 `90`，`85.50` 显示为 `85.5`。平均分、均值固定保留两位小数。
- **FR-004** 个人成绩单：`gradebook report <学号>` 按课程名的字典序每行输出 `<课程>: <分数>`，最后一行输出 `Average: <平均分>`；该学生没有任何成绩时只输出 `Average: N/A`。
- **FR-005** 课程排名：`gradebook top <课程> [-n N]`（默认 N=3）按分数降序输出排名不超过 N 的学生，每行 `<名次>. <姓名> <分数>`。同分同名次，下一名次跳过（如 1、1、3），同分者按学号升序排列。课程没有任何成绩时输出 `No records`。
- **FR-006** 课程统计：`gradebook stats <课程>` 依次输出 `count: <人数>`、`mean: <均值>`、`max: <最高分>`、`min: <最低分>`；课程没有成绩时输出 `No records`。
- **FR-007** 批量导入：`gradebook import <CSV 文件>`。CSV 为 UTF-8 编码，首行为表头 `id,name,course,score`。学号不存在时自动添加学生；已存在时忽略该行的姓名。合法的行按 FR-002 录入；不合法的行跳过，并在 stderr 输出 `Skipped line <行号>: <原因>`（行号从文件第 1 行即表头开始计）。结束时输出 `Imported <成功行数> rows`，退出码为 0。

# 非功能需求

- **NFR-001** 除 FR-007 中跳过的行外，所有错误信息输出到 stderr，退出码为 1，且不修改已保存的数据。
- **NFR-002** `gradebook --help` 输出用法说明，退出码为 0。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-002, FR-004, FR-003]
  steps:
    - run: [add-student, "S01", "张三"]
      expect: {exit: 0, stdout_contains: ["Added student S01"]}
    - run: [record, "S01", "math", "90.0"]
      expect: {exit: 0, stdout_contains: ["Recorded S01 math 90"]}
    - run: [record, "S01", "art", "85.5"]
      expect: {exit: 0}
    - run: [report, "S01"]
      expect: {exit: 0, stdout_regex: "\\Aart: 85\\.5\\nmath: 90\\nAverage: 87\\.75\\n?\\Z"}
- id: AS-002
  covers: [FR-001, FR-002]
  steps:
    - run: [add-student, "S01", "张三"]
      expect: {exit: 0}
    - run: [add-student, "S01", "李四"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [record, "S09", "math", "80"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [record, "S01", "math", "100.5"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [record, "S01", "math", "80.25"]
      expect: {exit: 1, stderr_nonempty: true}
    - run: [report, "S01"]
      expect: {exit: 0, stdout_contains: ["Average: N/A"], stdout_not_contains: ["math"]}
- id: AS-003
  covers: [FR-002, FR-004]
  steps:
    - run: [add-student, "S01", "张三"]
      expect: {exit: 0}
    - run: [record, "S01", "math", "60"]
      expect: {exit: 0}
    - run: [record, "S01", "math", "70"]
      expect: {exit: 0}
    - run: [report, "S01"]
      expect: {exit: 0, stdout_contains: ["math: 70", "Average: 70.00"], stdout_not_contains: ["math: 60"]}
- id: AS-004
  covers: [FR-005]
  files:
    s.csv: "id,name,course,score\nS03,王五,math,88\nS01,张三,math,95\nS02,李四,math,95\nS04,赵六,math,70\n"
  steps:
    - run: [import, s.csv]
      expect: {exit: 0, stdout_contains: ["Imported 4 rows"]}
    - run: [top, math]
      expect: {exit: 0, stdout_regex: "\\A1\\. 张三 95\\n1\\. 李四 95\\n3\\. 王五 88\\n?\\Z"}
    - run: [top, math, -n, "1"]
      expect: {exit: 0, stdout_regex: "\\A1\\. 张三 95\\n1\\. 李四 95\\n?\\Z"}
    - run: [top, physics]
      expect: {exit: 0, stdout_contains: ["No records"]}
- id: AS-005
  covers: [FR-006, FR-003]
  files:
    s.csv: "id,name,course,score\nS01,A,math,90\nS02,B,math,85.5\nS03,C,math,71\n"
  steps:
    - run: [import, s.csv]
      expect: {exit: 0}
    - run: [stats, math]
      expect: {exit: 0, stdout_regex: "\\Acount: 3\\nmean: 82\\.17\\nmax: 90\\nmin: 71\\n?\\Z"}
    - run: [stats, art]
      expect: {exit: 0, stdout_contains: ["No records"]}
- id: AS-006
  covers: [FR-007]
  files:
    bad.csv: "id,name,course,score\nS01,张三,math,90\nS02,李四,math,abc\nS03,王五,math,101\nS01,别名,art,77\n"
  steps:
    - run: [import, bad.csv]
      expect: {exit: 0, stdout_contains: ["Imported 2 rows"], stderr_nonempty: true}
    - run: [report, "S01"]
      expect: {exit: 0, stdout_contains: ["art: 77", "math: 90", "Average: 83.50"]}
    - run: [record, "S02", "math", "60"]
      expect: {exit: 1, stderr_nonempty: true}
- id: AS-007
  covers: [FR-007]
  files:
    one.csv: "id,name,course,score\nS01,张三,math,90\n"
  steps:
    - run: [import, one.csv]
      expect: {exit: 0, stdout_contains: ["Imported 1 rows"]}
    - run: [top, math]
      expect: {exit: 0, stdout_contains: ["1. 张三 90"]}
```
