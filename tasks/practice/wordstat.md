---
id: wordstat
title: 文本统计命令行工具
version: 1
environment:
  python: "3.12"
  allowed_dependencies: ["标准库"]
interface:
  type: cli
  command_name: wordstat
---

# 背景

一个统计文本文件的小工具：统计行数、单词数和字符数，并找出最常出现的单词。输入文件均为 UTF-8 编码。

# 功能需求

- **FR-001** 统计单个文件：`wordstat count <文件>` 依次输出三行：`lines: <行数>`、`words: <单词数>`、`chars: <字符数>`。
- **FR-002** 行数定义：等于文件中换行符 `\n` 的个数；若文件非空且最后一个字符不是换行符，再加 1。空文件的三项统计都为 0。
- **FR-003** 单词定义：由 Unicode 字母或数字组成的最长连续片段（下划线和标点都是分隔符）。字符数是文件解码后的 Unicode 字符个数，包括换行符。
- **FR-004** 统计多个文件：`wordstat count <文件1> <文件2> ...`（两个及以上文件）时，每个文件输出一行 `<文件名>\t<行数>\t<单词数>\t<字符数>`（`\t` 为制表符，文件名按命令行中的写法原样输出），最后输出一行 `total\t<行数合计>\t<单词数合计>\t<字符数合计>`。
- **FR-005** 高频词：`wordstat top <文件> [-k K]` 输出出现次数最多的 K 个单词（默认 K=5），每行 `<单词> <次数>`。单词统一转为小写后再计数；按次数降序排列，次数相同时按单词的字典序升序。不同单词少于 K 个时全部输出。
- **FR-006** 最短长度：`wordstat top` 支持 `--min-length L`，长度（字符数）小于 L 的单词不参与统计。

# 非功能需求

- **NFR-001** 文件不存在时，在 stderr 输出包含 `not found` 的错误信息，退出码为 2；不输出任何统计结果。
- **NFR-002** `wordstat --help` 输出用法说明，退出码为 0。

# 验收场景

```yaml
- id: AS-001
  covers: [FR-001, FR-002, FR-003]
  files:
    a.txt: "Hello, world!\nhello again\n"
  steps:
    - run: [count, a.txt]
      expect: {exit: 0, stdout_contains: ["lines: 2", "words: 4", "chars: 26"]}
- id: AS-002
  covers: [FR-002]
  files:
    b.txt: "one\ntwo"
    empty.txt: ""
  steps:
    - run: [count, b.txt]
      expect: {exit: 0, stdout_contains: ["lines: 2", "words: 2", "chars: 7"]}
    - run: [count, empty.txt]
      expect: {exit: 0, stdout_contains: ["lines: 0", "words: 0", "chars: 0"]}
- id: AS-003
  covers: [FR-003]
  files:
    c.txt: "snake_case 3.14 中文 café\n"
  steps:
    - run: [count, c.txt]
      expect: {exit: 0, stdout_contains: ["lines: 1", "words: 6", "chars: 24"]}
- id: AS-004
  covers: [FR-004]
  files:
    a.txt: "x y\n"
    b.txt: "z\n\n"
  steps:
    - run: [count, a.txt, b.txt]
      expect: {exit: 0, stdout_regex: "^a\\.txt\\t1\\t2\\t4$", stdout_contains: ["b.txt\t2\t1\t3", "total\t3\t3\t7"]}
- id: AS-005
  covers: [FR-005]
  files:
    t.txt: "the cat and the hat. The end, and THE dog\n"
  steps:
    - run: [top, t.txt, -k, "2"]
      expect: {exit: 0, stdout_regex: "\\Athe 4\\nand 2\\n?\\Z"}
    - run: [top, t.txt]
      expect: {exit: 0, stdout_regex: "\\Athe 4\\nand 2\\ncat 1\\ndog 1\\nend 1\\n?\\Z"}
- id: AS-006
  covers: [FR-006]
  files:
    t.txt: "a an ant ant bee be a\n"
  steps:
    - run: [top, t.txt, --min-length, "3"]
      expect: {exit: 0, stdout_regex: "\\Aant 2\\nbee 1\\n?\\Z"}
- id: AS-007
  covers: [FR-001]
  steps:
    - run: [count, missing.txt]
      expect: {exit: 2, stderr_nonempty: true, stdout_not_contains: ["lines"]}
```
