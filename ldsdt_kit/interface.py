"""接口目录比对：学生的 spec/interface.json 与课程组为每份需求整理的 <id>.interface.json。

- 命令：按命令名（去掉程序名、合并空白）计 F1；命中的命令再看参数个数与选项集合是否一致。
  得分 = 0.5 × 命令名 F1 + 0.5 × 参数与选项都一致的命令数 / 课程组命令数。
- 错误：一条错误由「错误信息 + 退出码」确定，不看所属命令（同一错误常被多条命令共用）。
  错误信息中的 `<...>` 是占位符，可以匹配任意文字，名字不计；两条信息只要有一方能匹配另一方即视为同一错误。
  得分为 F1。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .checks import normalize_command

PLACEHOLDER = re.compile(r"<[^<>]*>")


def truth_path(req_path: Path) -> Path:
    return req_path.with_name(f"{req_path.stem}.interface.json")


def load_truth(req_path: Path) -> dict | None:
    p = truth_path(req_path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _opts(options: list[str]) -> frozenset[str]:
    out = set()
    for o in options:
        head = str(o).split()[0] if str(o).split() else ""
        head = head.split("=")[0].strip("[]")
        if head and head not in ("--help", "-h"):
            out.add(head)
    return frozenset(out)


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def compare_commands(student: list[dict], truth: list[dict], program: str | None) -> dict:
    s = {normalize_command(c["name"], program): c for c in student}
    t = {normalize_command(c["name"], program): c for c in truth}
    hit = set(s) & set(t)
    precision = len(hit) / len(s) if s else 0.0
    recall = len(hit) / len(t) if t else 0.0
    exact = [n for n in hit if len(s[n].get("args", [])) == len(t[n]["args"])
             and _opts(s[n].get("options", [])) == _opts(t[n]["options"])]
    return {"score": 0.5 * _f1(precision, recall) + 0.5 * (len(exact) / len(t) if t else 0.0),
            "missing": sorted(set(t) - set(s)), "extra": sorted(set(s) - set(t)),
            "mismatched": sorted(hit - set(exact))}


def _norm_msg(m: str) -> str:
    return " ".join(str(m).split())


def _pattern(m: str) -> re.Pattern | None:
    """占位符变成通配。去掉占位符与 `error:` 后不到 3 个字符的信息（如 `error: <说明>`）不能当作模式。"""
    literal = PLACEHOLDER.sub("", m).replace("error:", "")
    if len(literal.strip()) < 3:
        return None
    parts = PLACEHOLDER.split(m)
    return re.compile(".+?".join(re.escape(p) for p in parts) + r"\Z")


def same_error(a: dict, b: dict) -> bool:
    if a["exit"] != b["exit"]:
        return False
    ma, mb = _norm_msg(a["message"]), _norm_msg(b["message"])
    if ma == mb:
        return True
    pa, pb = _pattern(ma), _pattern(mb)
    return bool((pa and pa.match(mb)) or (pb and pb.match(ma)))


def compare_errors(student: list[dict], truth: list[dict]) -> dict:
    # 接口目录的错误只指让命令以非零退出码结束的情况；退出码 0 的逐行报告、警告等不算错误，不参与比对。
    s = [e for e in student if isinstance(e.get("message"), str) and isinstance(e.get("exit"), int)
         and not isinstance(e.get("exit"), bool) and e["exit"] != 0]
    found = [any(same_error(x, t) for x in s) for t in truth]
    useful = [any(same_error(x, t) for t in truth) for x in s]
    precision = sum(useful) / len(s) if s else 0.0
    recall = sum(found) / len(truth) if truth else 0.0
    return {"score": _f1(precision, recall),
            "missing": [f"{t['message']}（{t['exit']}）" for t, f in zip(truth, found) if not f],
            "extra": [f"{x['message']}（{x['exit']}）" for x, u in zip(s, useful) if not u]}


def compare(student: dict | None, truth: dict, program: str | None) -> dict:
    """返回 {"commands": {...}, "errors": {...} 或 None}。课程组接口目录的 errors 为 null 时不评错误。"""
    student = student if isinstance(student, dict) else {}
    cmds = [c for c in student.get("commands") or [] if isinstance(c, dict) and isinstance(c.get("name"), str)]
    errs = [e for e in student.get("errors") or [] if isinstance(e, dict)]
    return {"commands": compare_commands(cmds, truth["commands"], program),
            "errors": compare_errors(errs, truth["errors"]) if truth.get("errors") is not None else None}
