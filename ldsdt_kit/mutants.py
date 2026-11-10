"""用参考实现与变异体评价测试模块生成的场景（tests/scenarios.yaml）。

- 有效场景：在参考实现上通过的场景。
- 变异体：参考实现注入一个行为缺陷后的副本，由 mutants.yaml 中的「把 old 换成 new」描述。
  有效场景中只要有一个在变异体上失败，该变异体即被击杀。

参考实现与变异体的位置：
- 练习需求：tasks/practice/reference/<id>/solution/ 与 tasks/practice/reference/<id>/mutants.yaml（公开）；
- 计分需求：只在课程组手里，环境变量 LDSDT_REFERENCE_DIR 指向的目录下的 solutions/<id>/ 与 grading/<id>/mutants.yaml。
  学生本地没有这些文件，这两项在官方复评中计算。

参考实现只用标准库，直接以 `python -m <包>` 加 PYTHONPATH 运行，不建虚拟环境。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import config
from .acceptance import _normalize, check_step, load_run_spec
from .reqdoc import Scenario


@dataclass
class Mutant:
    id: str
    category: str
    file: str
    old: str
    new: str


@dataclass
class Reference:
    solution: Path
    mutants: list[Mutant]


def load_mutants(path: Path) -> list[Mutant]:
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Mutant(str(m["id"]), str(m.get("category", "")), str(m["file"]), str(m["old"]), str(m["new"]))
            for m in items]


def find_reference(root: Path, task_id: str) -> Reference | None:
    practice = root / "tasks" / "practice" / "reference" / task_id
    candidates = [(practice / "solution", practice / "mutants.yaml")]
    ref = os.environ.get(config.REFERENCE_ENV_VAR)
    if ref:
        candidates.append((Path(ref) / "solutions" / task_id, Path(ref) / "grading" / task_id / "mutants.yaml"))
    for sol, mut in candidates:
        if sol.is_dir() and mut.is_file():
            return Reference(sol, load_mutants(mut))
    return None


def apply(solution: Path, m: Mutant, dest: Path) -> Path:
    shutil.copytree(solution, dest, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", ".venv"))
    f = dest / m.file
    text = f.read_text(encoding="utf-8")
    if text.count(m.old) != 1:
        raise ValueError(f"变异体 {m.id}：old 在 {m.file} 中出现 {text.count(m.old)} 次（必须恰好 1 次）")
    f.write_text(text.replace(m.old, m.new), encoding="utf-8")
    return dest


class DirectRunner:
    """在源码目录上直接运行 `python -m <包>`（只适用于课程组的标准库参考实现）。"""

    def __init__(self, src: Path, tmp: Path):
        spec, detail = load_run_spec(src)
        if spec is None or spec.run[:2] not in (["python", "-m"], ["python3", "-m"]):
            raise ValueError(f"参考实现的 ldsdt-run.json 必须是 python -m <包>：{detail}")
        self.argv = [sys.executable, *spec.run[1:]]
        self.src, self.tmp = src, tmp
        self.env = {**os.environ, "PYTHONPATH": str(src), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"}

    def passes(self, sc: Scenario) -> tuple[bool, list[str]]:
        work = Path(tempfile.mkdtemp(prefix="sc-", dir=self.tmp))
        try:
            for name, content in sc.files.items():
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            for i, step in enumerate(sc.steps, 1):
                try:
                    r = subprocess.run([*self.argv, *step.run], cwd=work, env=self.env, capture_output=True,
                                       stdin=subprocess.DEVNULL, timeout=config.STEP_TIMEOUT)
                    code, out, err = r.returncode, r.stdout, r.stderr
                except subprocess.TimeoutExpired:
                    code, out, err = -1, b"", b"timeout"
                msgs = check_step(step.expect, code, _normalize(out.decode("utf-8", "replace")),
                                  _normalize(err.decode("utf-8", "replace")))
                if msgs:
                    return False, [f"第 {i} 步 {step.run}：{m}" for m in msgs]
            return True, []
        finally:
            shutil.rmtree(work, ignore_errors=True)


def evaluate_tests(ref: Reference, scenarios: list[Scenario], workers: int | None = None) -> dict:
    """返回 {valid, invalid, killed, survived, categories, validity, kill_rate}。"""
    workers = workers or min(8, os.cpu_count() or 2)
    tmp = Path(tempfile.mkdtemp(prefix="ldsdt-mut-"))
    try:
        base = DirectRunner(ref.solution, tmp)
        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(base.passes, scenarios))
        valid = [s for s, (ok, _) in zip(scenarios, results) if ok]
        invalid = {s.id: f for s, (ok, f) in zip(scenarios, results) if not ok}

        def kill(m: Mutant) -> str | None:
            runner = DirectRunner(apply(ref.solution, m, tmp / f"m-{m.id}"), tmp)
            return next((s.id for s in valid if not runner.passes(s)[0]), None)

        with ThreadPoolExecutor(workers) as pool:
            killers = list(pool.map(kill, ref.mutants))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    killed = {m.id: k for m, k in zip(ref.mutants, killers) if k}
    return {
        "valid": [s.id for s in valid], "invalid": invalid,
        "killed": killed, "survived": [m.id for m in ref.mutants if m.id not in killed],
        "categories": {m.id: m.category for m in ref.mutants},
        "validity": len(valid) / max(len(scenarios), 10),
        "kill_rate": len(killed) / len(ref.mutants) if ref.mutants else 0.0,
    }
