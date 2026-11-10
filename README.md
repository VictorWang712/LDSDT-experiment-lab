# LDSDT 实验仓库

浙江大学「大模型驱动的软件开发与测试」（CS3297M）课程实验仓库。你将基于 [iCode](https://github.com/openJiuwen-ai/iCode) 一个模块一个模块地搭建多智能体系统：输入一份按课程格式编写的需求文档，依次产出规约、设计、可以直接安装使用的 Python 命令行应用和测试。

**完整的实验说明在课程网站上。** 本 README 只给出最常用的命令。

## 快速开始

需要先安装 [uv](https://docs.astral.sh/uv/) 与课程特供版 iCode（`uv tool install --python 3.14 --index-url https://1.92.199.78/pypi/simple icode-zju`，命令名 `icode-zju`），并把小组分到的 Qwen Key 和百炼接口地址分别设为环境变量 `LDSDT_QWEN_API_KEY`、`LDSDT_QWEN_BASE_URL`（见课程网站 Lab 0）。

```bash
uv run ldsdt setup      # 生成 iCode 模型配置 ldsdt-qwen，同步智能体，检查环境
uv run ldsdt doctor     # 只检查环境
```

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `uv run ldsdt sync` | 把 `agents/*.yaml` 同步到 iCode（名称加前缀 `ldsdt-`，自动绑定 `ldsdt-qwen`）。评测前会自动执行 |
| `uv run ldsdt try tasks/practice/todo-cli.md --lab 1` | 在任意一份需求上运行系统，按指定 Lab 的评分项检查，不计分。调试时先用 `tasks/practice/` 里的小需求 |
| `uv run ldsdt grade lab0` | 在本 Lab 的计分需求上运行你的系统并打分；`--task <id>` 只跑一份，`--no-run` 只对已有产物打分，`-v` 显示问题与失败原因 |
| `uv run ldsdt submit lab0` | 门槛通过后提交运行产物，打标签 `lab0-submit` 并推送 |
| `uv run ldsdt collect --week N` | 打包本周的本地会话记录（研究用） |

手动运行一次系统：

```bash
icode-zju workflow run ldsdt --trust --input '{"requirement": "<需求文档的绝对路径>", "run_dir": "<输出目录的绝对路径>", "lab": 0}'
```

Windows 上的 PowerShell 5（系统自带的 Windows PowerShell）会吃掉单引号里的双引号，上面的命令会收到不合法的 JSON。在 Windows 上请改用 `uv run ldsdt try <需求文档> --lab <N>`，它会替你拼好输入并在 `runs/try/` 下检查产物。

## 目录

```text
.chrys/workflows/ldsdt/   你的系统：工作流入口 ldsdt.py 及辅助模块
agents/                   你的智能体配置（格式见 agents/README.md）
prompts/                  可选：提示词与模板
tasks/public/             Lab 1–4 的计分需求，以及评分用的接口目录 <id>.interface.json
tasks/practice/           练习需求（Lab 0 计分，之后用于调试）；reference/ 下是练习需求的参考实现与变异体
runs/                     运行产物，提交时一并提交
design-choices.yaml       各 Lab 自由度的选择声明（A、B 两份必须一致）
docs/                     iCode 工作流速查表
research/                 C 的记录
ldsdt_kit/                课程工具包，不得修改
```

## 规则摘要

- API Key 只能放在环境变量里，**不得提交到仓库**；`submit` 会检查。
- A、B 之间禁止共享代码、提示词与智能体配置，只能讨论设计思路。
- 需求、验收场景与接口目录全部公开，本地评测分就是成绩中的评测分；只有 Lab 4 的「场景有效率」与「变异体击杀率」需要课程组的参考实现，在官方复评中计算。运行超时不判 0，按已经生成的产物评分。
- 系统运行时不得读取 `tasks/` 下的评分依据（接口目录、参考实现、变异体），也不得在提示词里写入针对某份需求的内容。
- 每个 Lab 开始前运行 `git pull upstream main` 拉取评测工具与说明的更新。
