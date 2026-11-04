"""ldsdt sync：把仓库 agents/*.yaml 复制到 iCode 用户目录，统一加 ldsdt- 前缀并绑定 ldsdt-qwen。

iCode 只从用户目录加载智能体配置，不读项目目录，因此以仓库 agents/ 为准、每次评测前自动同步。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import config
from .common import chrys_dir, repo_root, info, ok, bad, warn

HEADER = "# 由 ldsdt sync 从实验仓库 agents/{src} 生成，请勿在此修改（修改仓库里的文件后重新 sync）。\n"


def agents_dir() -> Path:
    return chrys_dir() / "agents"


def repo_agents(root: Path) -> list[tuple[Path, dict]]:
    out = []
    for p in sorted((root / "agents").glob("*.yaml")) + sorted((root / "agents").glob("*.yml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{p.name}：顶层必须是映射（key: value）")
        name = str(data.get("name") or p.stem).strip()
        if not name or any(c in name for c in '/\\:*?"<>| '):
            raise ValueError(f"{p.name}：name 不合法：{name!r}")
        if "acp" in data:
            raise ValueError(f"{p.name}：本课程不允许 ACP 外部智能体")
        data["name"] = name
        out.append((p, data))
    names = [d["name"] for _, d in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"agents/ 中有重名智能体：{', '.join(sorted(dup))}")
    return out


def transform(data: dict, local_names: set[str]) -> dict:
    """生成用户目录中的配置：加前缀、固定 ID、强制绑定 ldsdt-qwen、改写对本仓库智能体的子智能体引用。"""
    src_name = data["name"]
    out = dict(data)
    out["name"] = config.AGENT_PREFIX + src_name
    out["id"] = config.stable_id("agent", out["name"])
    out["model"] = {"profile_id": config.MODEL_PROFILE_ID}
    out.setdefault("display_name", f"LDSDT {src_name}")
    subs = (out.get("sub_agents") or {}).get("agents")
    if isinstance(subs, list):
        new_subs = []
        for item in subs:
            item = dict(item)
            ref = item.get("profile")
            if ref in local_names:
                item["profile"] = config.AGENT_PREFIX + ref
                # 工具名只能含字母数字下划线，默认会用带连字符的 name，所以显式保留原名
                item.setdefault("tool_name", ref.replace("-", "_"))
            new_subs.append(item)
        out["sub_agents"] = {**out["sub_agents"], "agents": new_subs}
    return out


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, s: str):
    # 多行文本（提示词）用 | 块样式输出，便于在 iCode 中阅读
    return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)


_Dumper.add_representer(str, _str)


def render(src: Path, data: dict) -> str:
    return HEADER.format(src=src.name) + yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False)


def planned(root: Path) -> dict[str, str]:
    """目标文件名 -> 期望内容。"""
    items = repo_agents(root)
    local = {d["name"] for _, d in items}
    result = {}
    for src, data in items:
        t = transform(data, local)
        result[f"{t['name']}.yaml"] = render(src, t)
    return result


def status(root: Path) -> tuple[bool, list[str]]:
    """检查用户目录是否与仓库一致；返回 (一致, 问题列表)。"""
    try:
        plan = planned(root)
    except (ValueError, yaml.YAMLError) as e:
        return False, [f"agents/ 解析失败：{e}"]
    problems = []
    d = agents_dir()
    for fname, text in plan.items():
        p = d / fname
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            problems.append(f"{fname} 未同步或已过期")
    for p in d.glob(f"{config.AGENT_PREFIX}*.yaml"):
        if p.name not in plan:
            problems.append(f"{p.name} 在仓库 agents/ 中已不存在")
    # Lab 0 开始时仓库里还没有智能体，这不算错误
    return not problems, problems


def sync_agents(verbose: bool = False) -> bool:
    root = repo_root()
    try:
        plan = planned(root)
    except (ValueError, yaml.YAMLError) as e:
        bad(f"agents/ 解析失败：{e}")
        return False
    d = agents_dir()
    d.mkdir(parents=True, exist_ok=True)
    for fname, text in plan.items():
        (d / fname).write_text(text, encoding="utf-8")
        if verbose:
            ok(f"{fname}")
    for p in d.glob(f"{config.AGENT_PREFIX}*.yaml"):
        if p.name not in plan:
            p.unlink()
            if verbose:
                warn(f"已删除仓库中不存在的 {p.name}")
    if verbose:
        info(f"  共 {len(plan)} 个智能体 → {d}")
    return True


def run(args) -> int:
    return 0 if sync_agents(verbose=True) else 1
