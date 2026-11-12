# /// script
# requires-python = ">=3.12,<3.13"
# [tool.chrys]
# python = "../../../.venv"
# ///
"""LDSDT 学生系统入口（Lab 0 起始版本：只有 Python 节点，智能体节点由你加上）。

评测工具这样启动本工作流：
    icode-zju workflow run ldsdt --trust --json --timeout <秒> \
        --input '{"requirement": "<需求文档绝对路径>", "run_dir": "<本次运行目录绝对路径>", "lab": <N>}'

lab 是本次评测的子任务编号（0–4），告诉你这次需要哪些产物；也可以忽略它，总是跑完整条链。

固定契约（不要改）：
  - 工作流 ID 为 ldsdt（即本文件夹名），模块顶层必须有 `workflow = wf.build()`；
  - 起点节点接收上面的 JSON 文本；
  - 各 Lab 要求的产物写在 run_dir 下（Lab 0 是 warmup/fr-list.json，见课程网站）；
  - 不得导入或调用课程工具包 ldsdt_kit（包括运行 `ldsdt` 命令），评测运行时导入会直接失败。
其余部分（节点划分、提示词、校验、循环……）由你设计。工作流 API 见 docs/icode-workflow-cheatsheet.md。
"""

import json
from pathlib import Path

from chrys.workflows import WorkflowBuilder, WorkflowValue

wf = WorkflowBuilder("LDSDT system", description="需求文档 → 各模块产物")


def prepare(value: WorkflowValue) -> WorkflowValue:
    """解析评测输入，建立输出目录，把需求文档交给下一个节点。"""
    args = json.loads(value.text)
    run_dir = Path(args["run_dir"])
    (run_dir / "warmup").mkdir(parents=True, exist_ok=True)
    requirement = Path(args["requirement"]).read_text(encoding="utf-8")
    # text 是交给下游智能体节点的消息；data 可以放任意 JSON 数据，供下游 Python 节点使用
    return WorkflowValue(text=requirement, data={"run_dir": str(run_dir), "lab": args.get("lab", 0)})


# TODO(Lab 0)：
#   1. 在 agents/ 下写一个智能体配置（例如 agents/warmup.yaml，格式见 agents/README.md），
#      运行 `uv run ldsdt sync` 后它在 iCode 中的名称是 ldsdt-warmup；
#   2. 在这里加一个智能体节点，让它读需求、列出全部功能需求：
#        warmup = wf.agent("warmup", profile="ldsdt-warmup", timeout=300)
#   3. 把结果写成 <run_dir>/warmup/fr-list.json，格式为
#        {"requirement_id": "...", "frs": [{"id": "FR-001", "summary": "一句话概括"}]}
#      可以让智能体自己用写文件工具写，也可以让它只回复 JSON 文本、由下面的 Python 节点解析后写入。
#      注意：智能体节点只输出 text，前面 Python 节点的 data 不会自动传到它后面（见速查表「在节点之间传递数据」）。
#   4. 修改下面的 wf.chain，把新节点接进去。


def finish(value: WorkflowValue) -> WorkflowValue:
    """收尾。"""
    return WorkflowValue(text=value.text)


prepare_node = wf.python("prepare", prepare)
finish_node = wf.python("finish", finish)

wf.start(prepare_node)
wf.chain(prepare_node, finish_node)
wf.output(finish_node)
workflow = wf.build()
