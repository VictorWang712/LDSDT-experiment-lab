# 智能体配置

这里的每个 `*.yaml` 是一个 iCode 智能体。`uv run ldsdt sync`（评测前会自动运行）把它们复制到 iCode 的用户目录，名称加前缀 `ldsdt-`，并统一绑定模型 `ldsdt-qwen`。因此：

- 工作流里用 `profile="ldsdt-<name>"` 引用；
- 不要写 `model` 字段（会被覆盖），也不允许 `acp` 外部智能体；
- 子智能体（`sub_agents`）引用本目录中的另一个智能体时写它的原名，sync 会自动改写。

最小示例（`agents/example.yaml`，名称、说明和指令换成你自己的）：

```yaml
name: example
description: 一句话说明这个智能体做什么
instructions: |
  你是……。用户会给你……。
  请……。完成后回复……。
tools:
  builtins: [filesystem.read, filesystem.write, search]   # 不需要工具时可以写 []
approval:
  default: auto                                            # 工作流里没有人审批，必须自动通过
```

需要运行命令时加 `shell` 并用白名单限制：

```yaml
tools:
  builtins: [filesystem.read, filesystem.write, search, shell]
  shell_filter:
    mode: whitelist
    commands: [python, python3, py, ls, dir, cat, type]
```

### Shell 白名单在 macOS 与 Windows 上的差别

iCode 在 macOS 上用 zsh 或 bash 运行命令，在 Windows 上用 PowerShell（工具名为 `pwsh` 或 `powershell`）。白名单按**命令名**匹配，所以同一份配置在两个平台上的表现可能不同。Windows 实测中被拦下的写法有：

| 写法 | 结果 | 改用 |
| --- | --- | --- |
| `cd <目录>; python x.py` | `cd` 不在白名单中 | Shell 工具自带「工作目录」参数，让智能体用它指定目录 |
| `$env:X=...`、`if (...) {...}` 等 PowerShell 语法 | `$env:...`、`if` 被当作命令名拦下 | 写成一个 Python 脚本或 `python -c "..."` |
| `Remove-Item`、`Get-ChildItem`、`Select-Object` 等 PowerShell 命令 | 不在白名单中 | 用文件工具（`filesystem.*`、`search`），或 `python -c` 调用 `shutil`、`pathlib` |
| `C:\...\.venv\Scripts\python.exe x.py`（完整路径） | 路径中的反斜杠被去掉后无法匹配 | 直接写 `python`。实测中，工作流里的智能体运行 `python` 时多数用的是仓库 `.venv` 中的 Python 3.12，偶尔会是 iCode 自带的较新版本；目标仓库最终由评测工具在 Python 3.12 下安装和测试 |
| `uv build`、`pip install` 等 | 不在白名单中，`.venv` 里也没有 pip | 目标仓库的安装由评测工具负责，智能体不需要自己安装 |

建议：

- 白名单只放跨平台都存在、你确实需要的命令，通常 `python`（加上 `python3`、`py` 兼容不同写法）就够了；
- 在智能体的 `instructions` 里写清楚：只用 `python` 运行脚本，不要用 `cd`、不要写完整路径、不要用 Shell 专有语法，文件操作用文件工具；
- 智能体被拦下时会收到 `command blocked — Command '...' not in whitelist` 的提示，通常会自己换一种写法，但每次都要多花一轮模型调用。在节点的会话记录中看到很多这样的提示时，就该改提示词了。

注意：

- iCode 不能限制写文件的路径，提示词里要写清楚只能写哪个目录。
- 智能体和工作流都不得调用课程工具包：不要让智能体运行 `ldsdt` 命令，也不要导入 `ldsdt_kit`。评测运行时这样做会直接失败。

完整字段（`sub_agents`、`skills`、`compaction` 等）见 iCode 文档 `docs/zh-Hans/reference/agent-profile.md`。
