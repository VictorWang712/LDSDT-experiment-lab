# iCode 工作流速查表

本页只列出本课程最常用的写法。完整说明见 iCode 文档《工作流参考》（`docs/zh-Hans/reference/workflows.md`）与《智能体配置文件参考》（`docs/zh-Hans/reference/agent-profile.md`）。

## 1. 文件与入口

- 工作流文件：`.chrys/workflows/ldsdt/ldsdt.py`。同一文件夹里的其他 `.py` 可以用 `from helpers import f` 导入（不能用相对导入），其他文件用 `Path(__file__).parent / "prompts" / "x.md"` 读取。
- 文件头的脚本元数据让 Python 节点使用仓库的 `.venv`（Python 3.12，能 import `ldsdt_kit`），不要删。
- 模块顶层必须有 `workflow = wf.build()`。顶层只放导入、函数定义和构建代码。
- 检查能否加载：`icode-zju workflow validate .chrys/workflows/ldsdt/ldsdt.py`（`uv run ldsdt doctor` 也会检查）。

## 2. 节点

```python
from chrys.workflows import Retry, WorkflowBuilder, WorkflowValue

wf = WorkflowBuilder("LDSDT system")

def prepare(value: WorkflowValue) -> WorkflowValue:      # Python 节点：接收上游的 WorkflowValue
    return WorkflowValue(text="给下游智能体的消息", data={"任意": "JSON 数据"})

p = wf.python("prepare", prepare, timeout=300)            # 返回 str 或 WorkflowValue
a = wf.agent("analyst", profile="ldsdt-analyst", timeout=900,  # 智能体节点：profile 是 iCode 中的智能体名称
             retry=Retry(max_attempts=2, backoff=5),
             instructions_suffix="可选：只对这个节点追加的指令")
```

- 智能体节点**只读上游的 `text`**，`data` 不会进入提示；输出的 `text` 是智能体的最终回复，`data` 为 `None`。
- 各智能体节点的上下文互相独立，连线只传递输出，不传对话历史。
- Python 节点里的相对路径以仓库根目录为基准；建议总用运行目录的绝对路径。

## 3. 连线

```python
wf.start(p)                          # 唯一起点
wf.chain(p, a, q)                    # p → a → q
wf.edge(a, q, when=lambda v: "OK" in v.text)            # 条件连线
wf.switch(a, [(lambda v: v.data["ok"], done)], default=fix)  # 多选一
wf.output(q)                         # 至少一个输出节点
workflow = wf.build()
```

连线不能成环；要重复执行就用 `loop`。

## 4. 在节点之间传递数据

智能体节点会丢掉 `data`。需要把运行目录等状态带过智能体节点时，用 `join` 把「智能体前的 Python 节点」与「智能体」汇合：

```python
def combine(sources):                      # sources: list[SourceValue]，按 join 声明的顺序
    state = sources[0].value.data          # 来自 Python 节点
    reply = sources[1].value.text          # 来自智能体
    return WorkflowValue(text=reply, data=state)

wf.edge(task, agent)
wf.join([task, agent], after, combine=combine)
```

`combine` 每次最多运行 **30 秒**，超时整个工作流失败。只在里面做合并；安装仓库、跑场景这类耗时的检查放到 `after` 这样的 Python 节点里（Python 节点的 `timeout` 可以自己设）。

也可以把状态写进运行目录里的文件，下一个 Python 节点再读出来。

## 5. 循环

```python
def body(scope):                           # 循环体：用 scope 建节点和连线
    t = scope.python("task", make_task)
    a = scope.agent("analyst", profile="ldsdt-analyst", timeout=600)
    c = scope.python("check", validate, timeout=600)   # validate 返回带 data["ok"] 的 WorkflowValue
    scope.edge(t, a)
    scope.join([t, a], c, combine=combine)   # combine 见第 4 节：只合并 data 与回复
    return t, c                            # (入口, 出口)

loop = wf.loop("spec", body=body, until=lambda v: v.data["ok"], max_iterations=3)
wf.chain(prep, loop, next_step)
```

第一轮入口收到循环节点的输入，之后每轮收到上一轮出口的输出。达到 `max_iterations` 仍未结束时默认继续往下走（`on_exhausted="continue"`）。

## 6. 课程工具包提供的检查函数

Python 节点里可以直接调用，返回问题列表（空表示通过），适合做「校验失败就把问题反馈给智能体重做」：

```python
from ldsdt_kit import checks
from ldsdt_kit.acceptance import evaluate
from ldsdt_kit.reqdoc import parse

checks.fr_list(run_dir)           # Lab 0：warmup/fr-list.json
checks.spec(run_dir)              # Lab 1：spec/index.json、spec/interface.json、spec/FORMAT.md
checks.manifest(run_dir)          # Lab 2：design/manifest.json
checks.conformance(run_dir)       # Lab 3：repo/ 是否实现了 manifest 中的模块与签名
report = evaluate(run_dir / "repo", parse(run_dir / "input.md"))   # Lab 3：运行需求中的验收场景
checks.scenarios(run_dir / "tests" / "scenarios.yaml")             # Lab 4：生成的场景格式
checks.report(run_dir)            # Lab 4：tests/report.json
```

## 7. 智能体配置（`agents/*.yaml`）

见 `agents/README.md`。改完运行 `uv run ldsdt sync`，iCode 中的名称是 `ldsdt-<name>`。

## 8. 手动运行与排错

```bash
icode-zju workflow run ldsdt --trust --json --input '{"requirement": "<需求绝对路径>", "run_dir": "<输出目录绝对路径>", "lab": 0}'
```

Windows 上的 PowerShell 5（系统自带的 Windows PowerShell）会吃掉单引号里的双引号，上面的命令会收到不合法的 JSON。在 Windows 上请改用 `uv run ldsdt try <需求文档> --lab <N>`，它会替你拼好输入并在 `runs/try/` 下检查产物。

- 每次运行都是一个 iCode 会话，`--json` 输出里的 `session_id` 与 `run_id` 也写在 `runs/.../run.json` 中。
- 智能体节点的完整对话在 `~/.chrys/sessions/<会话目录>/workflows/<run_id>/nodes/<节点>@iter#*.session.*.json`（Windows 为 `%APPDATA%\chrys\sessions\...`）。会话目录名是 `session_id` 去掉连字符后的前 12 位。
- 也可以在 iCode TUI 里打开工作流会话，逐个节点查看输入输出。
