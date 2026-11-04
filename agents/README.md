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

注意：iCode 不能限制写文件的路径，提示词里要写清楚只能写哪个目录。

完整字段（`sub_agents`、`skills`、`compaction` 等）见 iCode 文档 `docs/zh-Hans/reference/agent-profile.md`。
