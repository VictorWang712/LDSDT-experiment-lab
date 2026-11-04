"""需求文档解析：YAML 头 + 背景 + 规则 + 编号功能需求 + YAML 验收场景（格式见实验文档）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FR_RE = re.compile(r"\*\*(FR-\d{3})\*\*")
RULE_RE = re.compile(r"\*\*(R-\d{3})\*\*")
EXPECT_KEYS = {"exit", "stdout_contains", "stdout_not_contains", "stdout_regex", "stderr_nonempty", "stderr_contains"}


@dataclass
class Step:
    run: list[str]
    expect: dict


@dataclass
class Scenario:
    id: str
    covers: list[str]
    steps: list[Step]
    files: dict[str, str] = field(default_factory=dict)  # 场景开始前写入临时目录的文件


@dataclass
class Requirement:
    path: Path
    meta: dict
    frs: list[str]
    scenarios: list[Scenario] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.meta["id"])


def _split_front_matter(text: str) -> tuple[dict, str]:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        raise ValueError("缺少 YAML 头（以 --- 开始和结束）")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict) or "id" not in meta:
        raise ValueError("YAML 头必须包含 id")
    return meta, text[m.end():]


def _section(body: str, title: str) -> str:
    """一级标题下的内容（含其中的二级标题）。"""
    m = re.search(rf"^#\s*{re.escape(title)}\s*$(.*?)(?=^#\s|\Z)", body, re.M | re.S)
    return m.group(1) if m else ""


def _ids(regex: re.Pattern, text: str) -> list[str]:
    out: list[str] = []
    for x in regex.findall(text):
        if x not in out:
            out.append(x)
    return out


def parse_scenario_items(items) -> list[Scenario]:
    """把 YAML 列表解析为场景。需求文档的验收场景与 A4 生成的 tests/scenarios.yaml 共用这一格式。"""
    if not isinstance(items, list):
        raise ValueError("场景必须是 YAML 列表")
    out: list[Scenario] = []
    for n, item in enumerate(items):
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(f"第 {n + 1} 个场景缺少 id")
        steps = []
        for s in item.get("steps") or []:
            if not isinstance(s, dict) or not isinstance(s.get("run"), list):
                raise ValueError(f"{item['id']}: 每一步都需要 run 数组")
            expect = dict(s.get("expect") or {})
            unknown = set(expect) - EXPECT_KEYS
            if unknown:
                raise ValueError(f"{item['id']}: 不支持的 expect 字段 {sorted(unknown)}")
            steps.append(Step(run=[str(a) for a in s["run"]], expect=expect))
        files = {str(k): str(v) for k, v in (item.get("files") or {}).items()}
        out.append(Scenario(id=str(item["id"]), covers=[str(c) for c in item.get("covers") or []],
                            steps=steps, files=files))
    return out


def _parse_scenarios(section: str) -> list[Scenario]:
    out: list[Scenario] = []
    for block in re.findall(r"```ya?ml\s*\n(.*?)```", section, re.S):
        out += parse_scenario_items(yaml.safe_load(block) or [])
    return out


def parse(path: Path) -> Requirement:
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
    return Requirement(path=path, meta=meta, frs=_ids(FR_RE, _section(body, "功能需求")),
                       scenarios=_parse_scenarios(_section(body, "验收场景")),
                       rules=_ids(RULE_RE, _section(body, "规则")))
