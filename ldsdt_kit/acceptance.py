"""目标仓库验收：在干净虚拟环境中按 ldsdt-run.json 安装，然后逐个场景在空临时目录中黑盒运行。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .common import IS_WINDOWS, venv_python
from .reqdoc import Requirement, Scenario


@dataclass
class RunSpec:
    install: list[list[str]]
    run: list[str]


@dataclass
class InstallResult:
    ok: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    failures: list[str] = field(default_factory=list)


def load_run_spec(repo: Path) -> tuple[RunSpec | None, str]:
    p = repo / "ldsdt-run.json"
    if not p.is_file():
        return None, "缺少 ldsdt-run.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, f"ldsdt-run.json 不是合法 JSON：{e}"
    install, run = data.get("install", []), data.get("run")
    if not (isinstance(install, list) and all(isinstance(c, list) and c and all(isinstance(a, str) for a in c) for c in install)):
        return None, "install 必须是「参数数组」的数组"
    if not (isinstance(run, list) and run and all(isinstance(a, str) for a in run)):
        return None, "run 必须是非空的参数数组"
    return RunSpec(install=install, run=run), ""


def _normalize(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


class Environment:
    """一个临时虚拟环境。命令中的 python/pip 被替换为虚拟环境中的可执行文件（Windows 上子进程不按 env 的 PATH 查找）。"""

    def __init__(self, repo: Path):
        self.tmp = Path(tempfile.mkdtemp(prefix="ldsdt-env-"))
        # 在副本中安装，避免 pip install -e 等命令改动被评测的产物
        self.repo = self.tmp / "repo"
        shutil.copytree(repo, self.repo, ignore=shutil.ignore_patterns("*.egg-info", "__pycache__", ".venv"))
        self.venv = self.tmp / "venv"
        self.bin = self.venv / ("Scripts" if IS_WINDOWS else "bin")

    def env(self) -> dict:
        e = dict(os.environ)
        e.pop("PYTHONPATH", None)
        e["VIRTUAL_ENV"] = str(self.venv)
        e["PATH"] = str(self.bin) + os.pathsep + e.get("PATH", "")
        e["PYTHONIOENCODING"] = "utf-8"
        e["PYTHONUTF8"] = "1"
        e["NO_COLOR"] = "1"
        return e

    def resolve(self, argv: list[str]) -> list[str]:
        head = argv[0]
        if head in ("python", "python3", "py"):
            return [str(venv_python(self.venv)), *argv[1:]]
        candidate = self.bin / (head + (".exe" if IS_WINDOWS else ""))
        if candidate.exists():
            return [str(candidate), *argv[1:]]
        return argv

    def create(self) -> InstallResult:
        uv = shutil.which("uv")
        if not uv:
            return InstallResult(False, "找不到 uv")
        r = subprocess.run([uv, "venv", "--seed", "--python", "3.12", str(self.venv)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return InstallResult(r.returncode == 0, r.stderr[-500:])

    def install(self, spec: RunSpec) -> InstallResult:
        for cmd in spec.install:
            try:
                r = subprocess.run(self.resolve(cmd), cwd=self.repo, env=self.env(), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=config.INSTALL_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as e:
                return InstallResult(False, f"{cmd}: {e}")
            if r.returncode != 0:
                return InstallResult(False, f"{cmd} 退出码 {r.returncode}：{(r.stderr or r.stdout)[-800:]}")
        return InstallResult(True)

    def call(self, argv: list[str], cwd: Path) -> tuple[int, str, str]:
        try:
            r = subprocess.run(self.resolve(argv), cwd=cwd, env=self.env(), capture_output=True,
                               stdin=subprocess.DEVNULL, timeout=config.STEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            return -1, "", f"超时（{config.STEP_TIMEOUT} 秒）"
        except OSError as e:
            return -1, "", f"无法启动：{e}"
        dec = lambda b: _normalize(b.decode("utf-8", errors="replace"))
        return r.returncode, dec(r.stdout), dec(r.stderr)

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def check_step(expect: dict, code: int, out: str, err: str) -> list[str]:
    f = []
    if "exit" in expect:
        want = expect["exit"]
        if want == "nonzero":
            if code == 0:
                f.append("期望非 0 退出码，实际为 0")
        elif code != int(want):
            f.append(f"期望退出码 {want}，实际 {code}")
    for s in expect.get("stdout_contains", []):
        if str(s) not in out:
            f.append(f"stdout 缺少 {s!r}")
    for s in expect.get("stdout_not_contains", []):
        if str(s) in out:
            f.append(f"stdout 不应包含 {s!r}")
    if "stdout_regex" in expect and not re.search(str(expect["stdout_regex"]), out, re.M):
        f.append(f"stdout 不匹配 /{expect['stdout_regex']}/")
    if expect.get("stderr_nonempty") and not err.strip():
        f.append("期望 stderr 非空")
    for s in expect.get("stderr_contains", []):
        if str(s) not in err:
            f.append(f"stderr 缺少 {s!r}")
    return f


def run_scenario(env: Environment, spec: RunSpec, sc: Scenario) -> ScenarioResult:
    work = Path(tempfile.mkdtemp(prefix="ldsdt-sc-", dir=env.tmp))
    for name, content in sc.files.items():
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    failures: list[str] = []
    for i, step in enumerate(sc.steps, 1):
        code, out, err = env.call([*spec.run, *step.run], work)
        for msg in check_step(step.expect, code, out, err):
            failures.append(f"第 {i} 步 {step.run}：{msg}")
        if failures:
            if err.strip():
                failures.append(f"stderr 末尾：{err.strip()[-300:]}")
            break
    return ScenarioResult(sc.id, not failures, failures)


@dataclass
class AcceptanceReport:
    contract_ok: bool
    contract_detail: str
    readme_ok: bool
    install_ok: bool
    install_detail: str
    help_ok: bool
    scenarios: list[ScenarioResult]

    @property
    def pass_rate(self) -> float:
        return sum(s.passed for s in self.scenarios) / len(self.scenarios) if self.scenarios else 0.0

    def to_dict(self) -> dict:
        return {
            "contract_ok": self.contract_ok, "contract_detail": self.contract_detail,
            "readme_ok": self.readme_ok, "install_ok": self.install_ok, "install_detail": self.install_detail,
            "help_ok": self.help_ok, "pass_rate": round(self.pass_rate, 4),
            "scenarios": [{"id": s.id, "passed": s.passed, "failures": s.failures} for s in self.scenarios],
        }


def evaluate(repo: Path, req: Requirement | list[Scenario]) -> AcceptanceReport:
    """在目标仓库上运行一组场景。req 可以是需求文档（用其验收场景），也可以直接是场景列表。

    学生的工作流也可以调用它，例如：
        from ldsdt_kit.acceptance import evaluate
        from ldsdt_kit.reqdoc import parse
        report = evaluate(run_dir / "repo", parse(run_dir / "input.md"))
    """
    scenarios = req if isinstance(req, list) else req.scenarios
    readme_ok = (repo / "README.md").is_file() and (repo / "README.md").stat().st_size > 0
    spec, detail = load_run_spec(repo) if repo.is_dir() else (None, "目标仓库目录 repo/ 不存在")
    if spec is None:
        return AcceptanceReport(False, detail, readme_ok, False, "", False,
                                [ScenarioResult(s.id, False, ["未能安装"]) for s in scenarios])
    env = Environment(repo)
    try:
        res = env.create()
        if res.ok:
            res = env.install(spec)
        if not res.ok:
            return AcceptanceReport(True, "", readme_ok, False, res.detail, False,
                                    [ScenarioResult(s.id, False, ["未能安装"]) for s in scenarios])
        work = Path(tempfile.mkdtemp(prefix="ldsdt-help-", dir=env.tmp))
        code, out, _ = env.call([*spec.run, "--help"], work)
        help_ok = code == 0 and bool(out.strip())
        results = [run_scenario(env, spec, sc) for sc in scenarios]
        return AcceptanceReport(True, "", readme_ok, True, "", help_ok, results)
    finally:
        env.cleanup()
