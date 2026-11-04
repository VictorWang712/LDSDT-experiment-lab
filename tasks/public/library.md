---
id: library
title: 图书馆借阅管理
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: lib
  data_dir: .library
---

# 背景

一所中学图书馆想用一个命令行程序替代纸质登记簿。馆员用它登记读者和藏书、办理借书还书与续借、管理预约队列、收取逾期罚款，并在学期末导入导出数据、查看统计。

读者分为学生（student）和教职工（staff），两类读者的借书数量、借期和罚款标准不同。同一种书可以有多个副本；副本不单独编号，程序只记录每种书的副本总数。所有数据保存在当前工作目录下的 `.library/` 目录中，目录或文件不存在时视为没有任何数据。

本需求是课程的**基准需求**，Lab 1–4 每次都会运行。

# 规则

- **R-001** 日期一律写作 `YYYY-MM-DD`，必须是真实存在的日期（例如 `2026-02-30` 非法）。非法日期报错 `error: invalid date <原值>`，退出码 2。
- **R-002** 读者证号和书号都是 1 个大写英文字母加 3 位数字（如 `S001`、`B101`）。不符合时报错 `error: invalid id <原值>`，退出码 2。
- **R-003** 姓名、书名、作者先去掉首尾空白。去掉后为空时报错 `error: empty <字段>`（字段为 `name`、`title`），退出码 2；超过 40 个字符时报错 `error: <字段> too long`，退出码 2。作者可以省略，省略时显示为 `-`。
- **R-004** 输入的金额必须是正数，最多两位小数（如 `3`、`2.5`、`0.75`），否则报错 `error: invalid amount <原值>`，退出码 2。所有金额输出都保留两位小数（如 `3.00`）；计算时使用十进制精确运算，需要舍入时四舍五入到分。
- **R-005** 错误信息一律输出到 stderr，格式为 `error: <说明>`，stdout 不输出任何内容。退出码：2 表示参数错误（包括命令行用法错误、R-001 至 R-004），3 表示读者、书或文件不存在，4 表示违反业务规则。
- **R-006** 一条命令同时有多个错误时，只报告第一个：先按参数在命令中出现的顺序检查参数格式，再检查读者是否存在、书是否存在，最后按各 FR 中列出的顺序检查业务规则。
- **R-007** 两类读者的规则：

  | 类型 | 同时在借上限 | 借期 | 逾期罚款 |
  | --- | --- | --- | --- |
  | student | 3 本 | 14 天 | 每天 0.50 |
  | staff | 10 本 | 28 天 | 每天 0.20 |

  每一次借阅的罚款最多 20.00。
- **R-008** 借出日期为 D 时，应还日期为 D 加上借期天数。在日期 D 时，若 D 晚于应还日期，则该借阅已逾期，逾期天数为 D 与应还日期相差的天数。
- **R-009** 一种书的可借副本数 = 副本总数 − 借出中的副本数 − 已为预约读者保留的副本数。
- **R-010** 每当有副本空出（还书、增加副本、取消已保留的预约）且这种书有「等待中」的预约时，空出的副本立即保留给排在最前的等待中读者，该预约变为「已保留」，并输出一行 `Held for <证号>`（每保留一个副本输出一行）。只有没有等待中的预约时，副本才计入可借副本。
- **R-011** 列表输出时，各列之间用两个空格分隔；列表为空时输出对应 FR 规定的提示语。英文单复数：数量为 1 时用单数（`1 copy`、`1 day`），否则用复数（`3 copies`、`2 days`）。
- **R-012** 命令行中的整数参数（如编号、数量、上限）按十进制解析，允许前导零，例如 `--copies 03` 等同于 `--copies 3`。

# 功能需求

## 读者

- **FR-001** `lib reader add <证号> <姓名> [--type student|staff]` 登记读者，类型默认为 student，成功时输出 `Reader <证号> added`。证号已存在时报错 `error: reader <证号> already exists`（退出码 4）。
- **FR-002** `lib reader show <证号>` 按如下格式输出读者信息，其中 Loans 是当前在借数量，Fines 是未缴罚款总额，Status 为 `active` 或 `suspended`：

  ```text
  Reader: S001
  Name: 张三
  Type: student
  Loans: 2
  Fines: 1.50
  Status: active
  ```

  读者不存在时报错 `error: reader <证号> not found`（退出码 3）。之后所有涉及读者的命令都用同样的错误。
- **FR-003** `lib reader suspend <证号>` 停用读者，输出 `Reader <证号> suspended`；`lib reader activate <证号>` 恢复读者，输出 `Reader <证号> activated`。对已处于该状态的读者重复操作也视为成功。停用的读者不能借书、续借和预约，但可以还书和缴罚款。
- **FR-004** `lib reader list` 每行输出一位读者：`<证号>  <姓名>  <类型>  <状态>`，按证号升序。没有读者时输出 `No readers`。

## 馆藏

- **FR-005** `lib book add <书号> <书名> [--author <作者>] [--copies <N>]` 登记一种书，副本数默认为 1。N 必须是 1 到 20 之间的整数，否则报错 `error: invalid copies <原值>`（退出码 2）。成功时输出 `Book <书号> added with <N> copies`（N 为 1 时为 `1 copy`）。书号已存在时报错 `error: book <书号> already exists`（退出码 4）。
- **FR-006** `lib book add-copies <书号> <N>` 增加 N 个副本（N 的要求同 FR-005），输出 `Book <书号> now has <总数> copies`（总数为 1 时为 `1 copy`）。新副本按 R-010 先保留给等待中的预约，`Held for` 行输出在这一行之后。书不存在时报错 `error: book <书号> not found`（退出码 3），之后所有涉及书的命令都用同样的错误。
- **FR-007** `lib book remove-copies <书号> <N>` 减少 N 个副本（N 的要求同 FR-005），只能移除可借副本（R-009）。N 超过可借副本数时报错 `error: only <可借数> available to remove`（退出码 4）。成功时输出格式同 FR-006。副本总数可以减为 0。
- **FR-008** `lib book show <书号>` 按如下格式输出，Holds 为该书预约队列的长度（包括等待中与已保留）：

  ```text
  Book: B101
  Title: 三体
  Author: 刘慈欣
  Copies: 3
  Available: 1
  On loan: 2
  Holds: 0
  ```

- **FR-009** `lib book list [--available]` 每行输出一种书：`<书号>  <书名>  <可借数>/<副本总数>`，按书号升序；加 `--available` 时只列出可借数大于 0 的书。没有可列出的书时输出 `No books`。
- **FR-010** `lib book search <关键词>` 在书名和作者中查找包含关键词的书（不区分英文大小写，关键词先去掉首尾空白），每行输出 `<书号>  <书名>  <作者>`，按书号升序。关键词为空时报错 `error: empty keyword`（退出码 2）；没有结果时输出 `No books found`。

## 借还

- **FR-011** `lib borrow <证号> <书号> --date <日期>` 借书，成功时输出 `Borrowed <书号> by <证号>, due <应还日期>`。业务规则按以下顺序检查（R-006），均为退出码 4：
  1. 读者已停用：`error: reader <证号> is suspended`
  2. 读者在该日期有逾期未还的借阅（R-008）：`error: reader <证号> has overdue loans`
  3. 未缴罚款总额超过 10.00（恰好 10.00 可以借）：`error: reader <证号> has unpaid fines over 10.00`
  4. 在借数量已达上限（R-007）：`error: loan limit reached`
  5. 读者正在借这种书：`error: reader <证号> already has <书号>`
  6. 该书有为此读者保留的副本时，借出该副本并移除这条预约；否则若可借副本为 0：`error: no copies available`
- **FR-012** `lib return <证号> <书号> --date <日期>` 还书，输出 `Returned <书号> by <证号>`。读者没有在借这种书时报错 `error: reader <证号> does not have <书号>`（退出码 4）；还书日期早于借出日期时报错 `error: return date before borrow date`（退出码 4）。若逾期（R-008），按 R-007 计算罚款并记入读者的罚款记录，第二行输出 `Overdue <天数> days, fine <金额>`（1 天时为 `1 day`）。之后按 R-010 处理空出的副本。
- **FR-013** `lib renew <证号> <书号> --date <日期>` 续借，新的应还日期为原应还日期加上一个借期，输出 `Renewed <书号> for <证号>, due <新应还日期>`。业务规则按以下顺序检查，均为退出码 4：
  1. 读者没有在借这种书：同 FR-012
  2. 读者已停用：同 FR-011
  3. 这次借阅在该日期已逾期：`error: loan is overdue`
  4. 这次借阅已续借 2 次：`error: renewal limit reached`
  5. 这种书的预约队列不为空：`error: book has pending holds`
- **FR-014** `lib loans <证号>` 列出读者当前的借阅，每行 `<书号>  <书名>  due <应还日期>  renewed <续借次数>`，按应还日期升序，相同时按书号升序。没有借阅时输出 `No loans`。
- **FR-015** `lib overdue --date <日期>` 列出在该日期已逾期的全部借阅，每行 `<证号>  <书号>  <天数> days  <预计罚款>`（1 天时为 `1 day`；预计罚款按 R-007 计算，含上限），按逾期天数降序，再按证号、书号升序。没有时输出 `No overdue loans`。

## 预约

- **FR-016** `lib hold <证号> <书号>` 预约一种书，加入该书预约队列的末尾，状态为「等待中」，输出 `Hold placed for <证号> on <书号>, position <N>`，N 为在队列中的位置（从 1 开始，包括已保留的预约）。业务规则按以下顺序检查，均为退出码 4：
  1. 读者已停用：同 FR-011
  2. 读者正在借这种书：同 FR-011
  3. 读者已在该书的预约队列中：`error: reader <证号> already holds <书号>`
  4. 该书有可借副本：`error: copies available, borrow instead`
- **FR-017** `lib unhold <证号> <书号>` 取消预约，输出 `Hold cancelled for <证号> on <书号>`。读者不在该书预约队列中时报错 `error: reader <证号> has no hold on <书号>`（退出码 4）。若取消的是已保留的预约，按 R-010 处理空出的副本。
- **FR-018** `lib holds <书号>` 按队列顺序列出预约，每行 `<位置>  <证号>  <状态>`，状态为 `ready`（已保留）或 `waiting`（等待中）。队列为空时输出 `No holds`。

## 罚款

- **FR-019** `lib fines <证号>` 按产生顺序列出读者的全部罚款记录，每行 `<还书日期>  <书号>  <金额>`，最后一行为 `Total unpaid: <未缴总额>`。未缴总额 = 罚款总额 − 已缴总额。没有任何罚款记录时只输出 `No fines`。
- **FR-020** `lib pay <证号> <金额>` 缴纳罚款（金额格式见 R-004），输出 `Paid <金额>, remaining <剩余未缴>`。业务规则按以下顺序检查，均为退出码 4：未缴总额为 0：`error: no unpaid fines`；金额超过未缴总额：`error: amount exceeds unpaid fines`。

## 导入导出

- **FR-021** `lib import readers <文件>` 从 UTF-8 编码的 CSV 文件导入读者。第一行必须恰好是 `id,name,type`，否则报错 `error: bad header`（退出码 2）；文件不存在时报错 `error: file not found: <文件>`（退出码 3）。之后每个非空行是一位读者，type 为空时视为 student。有问题的行跳过，并在 stderr 输出一行 `line <行号>: <原因>`（行号为文件中的物理行号，表头是第 1 行），按以下顺序检查原因：`wrong number of fields`、`invalid id`、`empty name`、`name too long`、`invalid type`、`duplicate id`（与已有读者或文件中前面的行重复）。最后输出 `Imported <K> readers, skipped <M>`，退出码 0。
- **FR-022** `lib import books <文件>` 从 CSV 导入书，表头必须恰好是 `id,title,author,copies`，author 为空表示省略，copies 为空时视为 1。其余规则同 FR-021，原因依次为 `wrong number of fields`、`invalid id`、`empty title`、`title too long`、`invalid copies`、`duplicate id`。最后输出 `Imported <K> books, skipped <M>`。
- **FR-023** `lib export loans <文件>` 把当前全部借阅写入 CSV 文件（覆盖已有文件），表头 `reader,book,borrowed,due,renewals`，按证号、书号升序，输出 `Exported <N> loans`（N 为 1 时为 `1 loan`）。

## 统计

- **FR-024** `lib stats` 按如下格式输出全馆统计：

  ```text
  Readers: 3 (suspended 1)
  Books: 2 (copies 5)
  Loans: 2
  Holds: 1
  Unpaid fines: 3.50
  ```

  Loans 为当前借阅数，Holds 为全部预约队列的总长度。
- **FR-025** `lib top [--limit <N>]` 按历史借出次数（包括已归还的借阅，续借不算新的借出）列出最受欢迎的书，每行 `<名次>  <书号>  <书名>  <次数>`。按次数降序，次数相同按书号升序；次数相同的书名次相同，下一名次跳过（如 1、1、3）。只列出次数大于 0 的书，最多 N 行，N 默认为 5，必须是正整数，否则报错 `error: invalid limit <原值>`（退出码 2）。没有任何借出记录时输出 `No loans yet`。

# 非功能需求

- **NFR-001** `lib --help` 输出用法说明，退出码 0。
- **NFR-002** 命令成功时退出码为 0。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-002]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0, stdout_contains: ["Reader S001 added"]}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Reader: S001", "Name: 张三", "Type: student", "Loans: 0", "Fines: 0.00", "Status: active"]}
- id: AS-002
  covers: [FR-001, R-002, R-003, R-005]
  steps:
    - run: [reader, add, s001, 张三]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [reader, add, S001, "   "]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [reader, add, S001, 张三, --type, teacher]
      expect: {exit: 2}
    - run: [reader, add, S001, "  李四  ", --type, staff]
      expect: {exit: 0}
    - run: [reader, add, S001, 王五]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Name: 李四", "Type: staff"]}
- id: AS-003
  covers: [FR-002, R-005]
  steps:
    - run: [reader, show, S404]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [reader, show, S404]
      expect: {stdout_not_contains: ["Reader"]}
- id: AS-004
  covers: [FR-003, FR-004]
  steps:
    - run: [reader, list]
      expect: {exit: 0, stdout_contains: ["No readers"]}
    - run: [reader, add, T002, 赵六, --type, staff]
      expect: {exit: 0}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, suspend, T002]
      expect: {exit: 0, stdout_contains: ["Reader T002 suspended"]}
    - run: [reader, suspend, T002]
      expect: {exit: 0}
    - run: [reader, list]
      expect: {exit: 0, stdout_regex: "^S001  张三  student  active\\nT002  赵六  staff  suspended$"}
    - run: [reader, activate, T002]
      expect: {exit: 0, stdout_contains: ["Reader T002 activated"]}
- id: AS-005
  covers: [FR-005, FR-008, R-011]
  steps:
    - run: [book, add, B101, 三体, --author, 刘慈欣, --copies, "3"]
      expect: {exit: 0, stdout_contains: ["Book B101 added with 3 copies"]}
    - run: [book, add, B102, 草房子]
      expect: {exit: 0, stdout_contains: ["Book B102 added with 1 copy"]}
    - run: [book, show, B102]
      expect: {exit: 0, stdout_contains: ["Book: B102", "Title: 草房子", "Author: -", "Copies: 1", "Available: 1", "On loan: 0", "Holds: 0"]}
- id: AS-006
  covers: [FR-005, R-003]
  steps:
    - run: [book, add, B101, 三体, --copies, "0"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [book, add, B101, 三体, --copies, "21"]
      expect: {exit: 2}
    - run: [book, add, B101, 三体, --copies, "2.5"]
      expect: {exit: 2}
    - run: [book, add, B101, "12345678901234567890123456789012345678901"]
      expect: {exit: 2}
    - run: [book, add, B101, "1234567890123456789012345678901234567890"]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-007
  covers: [FR-006, FR-007, FR-008]
  steps:
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [book, add-copies, B101, "3"]
      expect: {exit: 0, stdout_contains: ["Book B101 now has 5 copies"]}
    - run: [book, remove-copies, B101, "4"]
      expect: {exit: 0, stdout_contains: ["Book B101 now has 1 copy"]}
    - run: [book, add-copies, B999, "1"]
      expect: {exit: 3, stderr_nonempty: true}
- id: AS-008
  covers: [FR-007, R-009]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --copies, "3"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [book, remove-copies, B101, "3"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [book, remove-copies, B101, "3"]
      expect: {stdout_not_contains: ["now has"]}
    - run: [book, remove-copies, B101, "2"]
      expect: {exit: 0, stdout_contains: ["Book B101 now has 1 copy"]}
    - run: [book, show, B101]
      expect: {exit: 0, stdout_contains: ["Copies: 1", "Available: 0", "On loan: 1"]}
- id: AS-009
  covers: [FR-007]
  steps:
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [book, remove-copies, B101, "3"]
      expect: {exit: 4}
    - run: [book, remove-copies, B101, "2"]
      expect: {exit: 0, stdout_contains: ["Book B101 now has 0 copies"]}
- id: AS-010
  covers: [FR-009]
  steps:
    - run: [book, list]
      expect: {exit: 0, stdout_contains: ["No books"]}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B200, 活着]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [borrow, S001, B200, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [book, list]
      expect: {exit: 0, stdout_regex: "^B101  三体  2/2\\nB200  活着  0/1$"}
    - run: [book, list, --available]
      expect: {exit: 0, stdout_contains: ["B101  三体  2/2"], stdout_not_contains: ["B200"]}
- id: AS-011
  covers: [FR-010]
  steps:
    - run: [book, add, B102, Harry Potter, --author, "J. K. Rowling"]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --author, 刘慈欣]
      expect: {exit: 0}
    - run: [book, add, B103, 平凡的世界]
      expect: {exit: 0}
    - run: [book, search, "  harry "]
      expect: {exit: 0, stdout_contains: ["B102  Harry Potter  J. K. Rowling"], stdout_not_contains: ["B101"]}
    - run: [book, search, ROWLING]
      expect: {exit: 0, stdout_contains: ["B102"]}
    - run: [book, search, 刘]
      expect: {exit: 0, stdout_contains: ["B101  三体  刘慈欣"]}
    - run: [book, search, 世界]
      expect: {exit: 0, stdout_contains: ["B103  平凡的世界  -"]}
    - run: [book, search, 哈利]
      expect: {exit: 0, stdout_contains: ["No books found"]}
    - run: [book, search, "  "]
      expect: {exit: 2, stderr_nonempty: true}
- id: AS-012
  covers: [FR-011, R-007, R-008]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, T001, 李老师, --type, staff]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-12-20"]
      expect: {exit: 0, stdout_contains: ["Borrowed B101 by S001, due 2027-01-03"]}
    - run: [borrow, T001, B101, --date, "2027-02-01"]
      expect: {exit: 0, stdout_contains: ["Borrowed B101 by T001, due 2027-03-01"]}
- id: AS-013
  covers: [FR-011, R-001]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-02-30"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [borrow, S001, B101, --date, "2026/11/02"]
      expect: {exit: 2}
    - run: [borrow, S001, B101]
      expect: {exit: 2}
    - run: [borrow, S001, B101, --date, "2028-02-29"]
      expect: {exit: 0, stdout_contains: ["due 2028-03-14"]}
- id: AS-014
  covers: [FR-011, R-006]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S404, B999, --date, "2026-13-01"]
      expect: {exit: 2}
    - run: [borrow, S404, B999, --date, "2026-11-01"]
      expect: {exit: 3, stderr_nonempty: true}
    - run: [borrow, S001, B999, --date, "2026-11-01"]
      expect: {exit: 3}
    - run: [borrow, s001, B999, --date, "2026-11-01"]
      expect: {exit: 2}
- id: AS-015
  covers: [FR-011, FR-003]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [reader, suspend, S001]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [reader, activate, S001]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
- id: AS-016
  covers: [FR-011, R-007]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [book, add, B103, C]
      expect: {exit: 0}
    - run: [book, add, B104, D]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B103, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B104, --date, "2026-11-01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Loans: 3"]}
- id: AS-017
  covers: [FR-011]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [borrow, S002, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [borrow, S003, B101, --date, "2026-11-01"]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-018
  covers: [FR-011, R-008]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0, stdout_contains: ["due 2026-11-15"]}
    - run: [borrow, S001, B102, --date, "2026-11-15"]
      expect: {exit: 0}
    - run: [return, S001, B102, --date, "2026-11-15"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-16"]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-019
  covers: [FR-011, FR-020, R-007]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-12-08"]
      expect: {exit: 0, stdout_contains: ["Overdue 23 days, fine 11.50"]}
    - run: [borrow, S001, B102, --date, "2026-12-08"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [pay, S001, "1.5"]
      expect: {exit: 0, stdout_contains: ["Paid 1.50, remaining 10.00"]}
    - run: [borrow, S001, B102, --date, "2026-12-08"]
      expect: {exit: 0}
- id: AS-020
  covers: [FR-011, R-006]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [reader, suspend, S001]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-12-01"]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-021
  covers: [FR-012, R-007]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, T001, 李老师, --type, staff]
      expect: {exit: 0}
    - run: [book, add, B101, 三体, --copies, "2"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, T001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-15"]
      expect: {exit: 0, stdout_contains: ["Returned B101 by S001"], stdout_not_contains: ["Overdue"]}
    - run: [return, T001, B101, --date, "2026-11-30"]
      expect: {exit: 0, stdout_contains: ["Returned B101 by T001", "Overdue 1 day, fine 0.20"]}
- id: AS-022
  covers: [FR-012, R-007]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-09-01"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-12-31"]
      expect: {exit: 0, stdout_contains: ["Overdue 107 days, fine 20.00"]}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Loans: 0", "Fines: 20.00"]}
- id: AS-023
  covers: [FR-012]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [borrow, S001, B101, --date, "2026-11-10"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-09"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [return, S001, B101, --date, "2026-11-10"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-10"]
      expect: {exit: 4}
- id: AS-024
  covers: [FR-013, R-007]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-03"]
      expect: {exit: 0, stdout_contains: ["Renewed B101 for S001, due 2026-11-29"]}
    - run: [renew, S001, B101, --date, "2026-11-29"]
      expect: {exit: 0, stdout_contains: ["due 2026-12-13"]}
    - run: [renew, S001, B101, --date, "2026-11-30"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [loans, S001]
      expect: {exit: 0, stdout_contains: ["B101  三体  due 2026-12-13  renewed 2"]}
- id: AS-025
  covers: [FR-013]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-16"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [renew, S001, B101, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-02"]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-026
  covers: [FR-013, FR-016]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-02"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [renew, S002, B101, --date, "2026-11-02"]
      expect: {exit: 4}
- id: AS-027
  covers: [FR-014]
  steps:
    - run: [reader, add, T001, 李老师, --type, staff]
      expect: {exit: 0}
    - run: [loans, T001]
      expect: {exit: 0, stdout_contains: ["No loans"]}
    - run: [book, add, B103, 活着]
      expect: {exit: 0}
    - run: [book, add, B102, 三体]
      expect: {exit: 0}
    - run: [book, add, B101, 围城]
      expect: {exit: 0}
    - run: [borrow, T001, B103, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, T001, B102, --date, "2026-11-05"]
      expect: {exit: 0}
    - run: [borrow, T001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [loans, T001]
      expect: {exit: 0, stdout_regex: "^B101  围城  due 2026-11-29  renewed 0\\nB103  活着  due 2026-11-29  renewed 0\\nB102  三体  due 2026-12-03  renewed 0$"}
- id: AS-028
  covers: [FR-015]
  steps:
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, T001, 李老师, --type, staff]
      expect: {exit: 0}
    - run: [book, add, B101, A, --copies, "3"]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [overdue, --date, "2026-12-01"]
      expect: {exit: 0, stdout_contains: ["No overdue loans"]}
    - run: [borrow, S002, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-03"]
      expect: {exit: 0}
    - run: [borrow, T001, B101, --date, "2026-10-01"]
      expect: {exit: 0}
    - run: [overdue, --date, "2026-11-16"]
      expect: {exit: 0, stdout_regex: "^T001  B101  18 days  3.60\\nS001  B102  1 day  0.50\\nS002  B101  1 day  0.50$"}
- id: AS-029
  covers: [FR-016, FR-018, R-010]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [holds, B101]
      expect: {exit: 0, stdout_contains: ["No holds"]}
    - run: [hold, S002, B101]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0, stdout_contains: ["Hold placed for S002 on B101, position 1"]}
    - run: [hold, S003, B101]
      expect: {exit: 0, stdout_contains: ["position 2"]}
    - run: [return, S001, B101, --date, "2026-11-10"]
      expect: {exit: 0, stdout_contains: ["Returned B101 by S001", "Held for S002"]}
    - run: [holds, B101]
      expect: {exit: 0, stdout_regex: "^1  S002  ready\\n2  S003  waiting$"}
    - run: [book, show, B101]
      expect: {exit: 0, stdout_contains: ["Available: 0", "On loan: 0", "Holds: 2"]}
- id: AS-030
  covers: [FR-016, FR-011, R-010]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [borrow, S003, B101, --date, "2026-11-02"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [borrow, S002, B101, --date, "2026-11-03"]
      expect: {exit: 0, stdout_contains: ["Borrowed B101 by S002, due 2026-11-17"]}
    - run: [holds, B101]
      expect: {exit: 0, stdout_contains: ["No holds"]}
- id: AS-031
  covers: [FR-016]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S001, B101]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [reader, suspend, S002]
      expect: {exit: 0}
    - run: [hold, S002, B999]
      expect: {exit: 3}
- id: AS-032
  covers: [FR-017, R-010]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [hold, S003, B101]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-05"]
      expect: {exit: 0, stdout_contains: ["Held for S002"]}
    - run: [unhold, S002, B101]
      expect: {exit: 0, stdout_contains: ["Hold cancelled for S002 on B101", "Held for S003"]}
    - run: [unhold, S003, B101]
      expect: {exit: 0, stdout_not_contains: ["Held for"]}
    - run: [book, show, B101]
      expect: {exit: 0, stdout_contains: ["Available: 1", "Holds: 0"]}
    - run: [unhold, S003, B101]
      expect: {exit: 4, stderr_nonempty: true}
- id: AS-033
  covers: [FR-006, R-010]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [book, add, B101, 三体]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [hold, S003, B101]
      expect: {exit: 0}
    - run: [book, add-copies, B101, "3"]
      expect: {exit: 0, stdout_regex: "^Book B101 now has 4 copies\\nHeld for S002\\nHeld for S003$"}
    - run: [book, show, B101]
      expect: {exit: 0, stdout_contains: ["Copies: 4", "Available: 1", "On loan: 1", "Holds: 2"]}
- id: AS-034
  covers: [FR-019, FR-020, R-004]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [fines, S001]
      expect: {exit: 0, stdout_contains: ["No fines"]}
    - run: [pay, S001, "1"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [return, S001, B102, --date, "2026-11-18"]
      expect: {exit: 0, stdout_contains: ["Overdue 3 days, fine 1.50"]}
    - run: [return, S001, B101, --date, "2026-11-20"]
      expect: {exit: 0, stdout_contains: ["fine 2.50"]}
    - run: [pay, S001, "0.755"]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [pay, S001, "-1"]
      expect: {exit: 2}
    - run: [pay, S001, "4.01"]
      expect: {exit: 4, stderr_nonempty: true}
    - run: [pay, S001, "0.5"]
      expect: {exit: 0, stdout_contains: ["Paid 0.50, remaining 3.50"]}
    - run: [fines, S001]
      expect: {exit: 0, stdout_regex: "^2026-11-18  B102  1.50\\n2026-11-20  B101  2.50\\nTotal unpaid: 3.50$"}
    - run: [pay, S001, "3.50"]
      expect: {exit: 0, stdout_contains: ["remaining 0.00"]}
    - run: [fines, S001]
      expect: {exit: 0, stdout_contains: ["Total unpaid: 0.00"]}
- id: AS-035
  covers: [FR-021]
  files:
    readers.csv: |
      id,name,type
      S001,张三,
      T001,李老师,staff
      x01,坏证号,student

      S002,  ,student
      S003,王五,teacher
      S001,重复,student
      S004,赵六
      S005,孙七,student
  steps:
    - run: [reader, add, S005, 已存在]
      expect: {exit: 0}
    - run: [import, readers, readers.csv]
      expect: {exit: 0, stdout_contains: ["Imported 2 readers, skipped 6"]}
    - run: [reader, list]
      expect: {exit: 0, stdout_regex: "^S001  张三  student  active\\nS005  已存在  student  active\\nT001  李老师  staff  active$"}
- id: AS-036
  covers: [FR-021, R-005]
  files:
    readers.csv: |
      id,name,type
      S001,张三,
      x01,坏证号,student

      S002,  ,student
      S003,王五,teacher
      S001,重复,student
      S004,赵六
    bad.csv: |
      id,name
      S001,张三
  steps:
    - run: [import, readers, readers.csv]
      expect: {exit: 0, stderr_nonempty: true}
    - run: [import, readers, bad.csv]
      expect: {exit: 2, stderr_nonempty: true}
    - run: [import, readers, missing.csv]
      expect: {exit: 3, stderr_nonempty: true}
- id: AS-037
  covers: [FR-022, FR-009]
  files:
    books.csv: |
      id,title,author,copies
      B101,三体,刘慈欣,3
      B102,草房子,,
      B103,,某人,1
      B104,活着,余华,0
      B105,围城,钱锺书,abc
      B101,三体 第二部,刘慈欣,1
      B106,边城,沈从文,20
  steps:
    - run: [import, books, books.csv]
      expect: {exit: 0, stdout_contains: ["Imported 3 books, skipped 4"]}
    - run: [book, list]
      expect: {exit: 0, stdout_regex: "^B101  三体  3/3\\nB102  草房子  1/1\\nB106  边城  20/20$"}
    - run: [book, show, B102]
      expect: {exit: 0, stdout_contains: ["Author: -"]}
- id: AS-038
  covers: [FR-023]
  steps:
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [book, add, B101, A, --copies, "2"]
      expect: {exit: 0}
    - run: [export, loans, out.csv]
      expect: {exit: 0, stdout_contains: ["Exported 0 loans"]}
    - run: [borrow, S002, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [export, loans, out.csv]
      expect: {exit: 0, stdout_contains: ["Exported 1 loan"]}
    - run: [borrow, S001, B102, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-03"]
      expect: {exit: 0}
    - run: [renew, S001, B101, --date, "2026-11-04"]
      expect: {exit: 0}
    - run: [export, loans, out.csv]
      expect: {exit: 0, stdout_contains: ["Exported 3 loans"]}
    - run: [import, readers, out.csv]
      expect: {exit: 2}
- id: AS-039
  covers: [FR-024]
  steps:
    - run: [stats]
      expect: {exit: 0, stdout_contains: ["Readers: 0 (suspended 0)", "Books: 0 (copies 0)", "Loans: 0", "Holds: 0", "Unpaid fines: 0.00"]}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [reader, add, S003, 王五]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B102, B, --copies, "4"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [hold, S002, B101]
      expect: {exit: 0}
    - run: [return, S001, B102, --date, "2026-11-22"]
      expect: {exit: 0}
    - run: [reader, suspend, S003]
      expect: {exit: 0}
    - run: [stats]
      expect: {exit: 0, stdout_regex: "^Readers: 3 \\(suspended 1\\)\\nBooks: 2 \\(copies 5\\)\\nLoans: 1\\nHolds: 1\\nUnpaid fines: 3.50$"}
- id: AS-040
  covers: [FR-025]
  steps:
    - run: [top]
      expect: {exit: 0, stdout_contains: ["No loans yet"]}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, add, S002, 李四]
      expect: {exit: 0}
    - run: [book, add, B103, C]
      expect: {exit: 0}
    - run: [book, add, B102, B]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [book, add, B104, D]
      expect: {exit: 0}
    - run: [borrow, S001, B103, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [renew, S001, B103, --date, "2026-11-02"]
      expect: {exit: 0}
    - run: [return, S001, B103, --date, "2026-11-03"]
      expect: {exit: 0}
    - run: [borrow, S002, B103, --date, "2026-11-03"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-03"]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-04"]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-04"]
      expect: {exit: 0}
    - run: [borrow, S001, B102, --date, "2026-11-04"]
      expect: {exit: 0}
    - run: [top]
      expect: {exit: 0, stdout_regex: "^1  B101  A  2\\n1  B103  C  2\\n3  B102  B  1$"}
    - run: [top, --limit, "1"]
      expect: {exit: 0, stdout_contains: ["1  B101  A  2"], stdout_not_contains: ["B103"]}
    - run: [top, --limit, "0"]
      expect: {exit: 2, stderr_nonempty: true}
- id: AS-041
  covers: [FR-012, FR-015, R-007]
  steps:
    - run: [reader, add, T001, 李老师, --type, staff]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [borrow, T001, B101, --date, "2026-01-01"]
      expect: {exit: 0, stdout_contains: ["due 2026-01-29"]}
    - run: [overdue, --date, "2026-12-31"]
      expect: {exit: 0, stdout_contains: ["T001  B101  336 days  20.00"]}
    - run: [return, T001, B101, --date, "2026-03-06"]
      expect: {exit: 0, stdout_contains: ["Overdue 36 days, fine 7.20"]}
- id: AS-042
  covers: [FR-002, FR-012, FR-019]
  steps:
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [book, add, B101, A]
      expect: {exit: 0}
    - run: [borrow, S001, B101, --date, "2026-11-01"]
      expect: {exit: 0}
    - run: [reader, suspend, S001]
      expect: {exit: 0}
    - run: [return, S001, B101, --date, "2026-11-17"]
      expect: {exit: 0, stdout_contains: ["Overdue 2 days, fine 1.00"]}
    - run: [pay, S001, "1"]
      expect: {exit: 0, stdout_contains: ["Paid 1.00, remaining 0.00"]}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Loans: 0", "Fines: 0.00", "Status: suspended"]}
- id: AS-043
  covers: [NFR-001, FR-001]
  steps:
    - run: [--help]
      expect: {exit: 0}
    - run: [reader, add, S001, 张三]
      expect: {exit: 0}
    - run: [reader, show, S001]
      expect: {exit: 0, stdout_contains: ["Reader: S001"]}
```
