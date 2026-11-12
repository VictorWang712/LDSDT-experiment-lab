"""ldsdt grade lab<N>：在本 Lab 的计分需求上运行系统，再对运行产物确定性打分。

Lab 0 热身工作流；Lab 1–4 依次评需求分析、设计、实现、测试模块的产物，Lab 2 起另计「前序模块」（之前各模块的产物评分项按比例折算）。
需求、验收场景与接口目录全部公开，本地评测分与官方复评一致；只有 Lab 4 的「场景有效率」与「变异体击杀率」
需要课程组的参考实现，在官方复评中计算。超时或出错不判 0：按运行目录中已有的产物评分。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from . import checks, config, doctor, interface, sync
from .acceptance import evaluate
from .common import (
    append_jsonl, bad, die, find_kit_usage, git, git_state, info, kit_hash, ldsdt_dir, now_iso, ok, platform_label,
    read_json, repo_root, warn, write_json,
)
from .mutants import evaluate_tests, find_reference
from .reqdoc import Requirement, parse
from .runner import run_task

A1_MAX, A2_MAX, A3_PRE_MAX = 90, 70, 30   # 各模块产物评分项的满分（不含 design-choices 与场景通过率）


# ------------------------------------------------------------------ 仓库级检查

_MODULE_LABEL = {"A1": "需求分析", "A2": "设计", "A3": "实现", "A4": "测试"}


def check_format_doc(root: Path, run_dir: Path) -> tuple[bool, bool | None, str]:
    """spec/FORMAT.md 是否存在；若仓库提供 validators/spec.py，则用它自证规约与声明一致。"""
    has_format = (run_dir / "spec" / "FORMAT.md").is_file()
    validator = root / "validators" / "spec.py"
    if not validator.is_file():
        return has_format, None, "未提供 validators/spec.py"
    try:
        r = subprocess.run([sys.executable, str(validator), str(run_dir / "spec")], cwd=root,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return has_format, False, "validators/spec.py 超时"
    return has_format, r.returncode == 0, (r.stdout + r.stderr).strip()[-500:]


def check_design_choices(root: Path, lab: int) -> tuple[bool, list[str]]:
    dims = config.DESIGN_DIMENSIONS.get(lab, [])
    try:
        data = yaml.safe_load((root / "design-choices.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return False, [f"design-choices.yaml 无法读取：{e}"]
    section = (data.get(f"lab{lab}") or {}) if isinstance(data, dict) else {}
    missing = [d for d in dims if not str(((section.get(d) or {}) if isinstance(section, dict) else {}).get("choice") or "").strip()]
    return not missing, [f"design-choices.yaml：lab{lab}.{d}.choice 未填写" for d in missing]


def repo_role(root: Path) -> str | None:
    """A / B：先看 origin 仓库名（<组号>-aiwork / <组号>-icode），再看 collect 记下的个人编号（G05-A）。"""
    url = git(root, "remote", "get-url", "origin").stdout.strip()
    m = re.search(r"-(aiwork|icode)(?:\.git)?/?$", url, re.IGNORECASE)
    if m:
        return "A" if m.group(1).lower() == "aiwork" else "B"
    name = str((read_json(root / ".ldsdt" / "local.json", {}) or {}).get("pseudonym") or "")
    m = re.search(r"-([AB])$", name, re.IGNORECASE)
    return m.group(1).upper() if m else None


COLLECT_NEEDS = {
    "A": "至少一个 AiWork 会话（在 AiWork「编码 → 项目」中打开本仓库后工作）",
    "B": "至少一个 iCode 对话会话（在本仓库中启动 icode-zju 与 DS-4.1-flash 对话；`ldsdt try` 产生的工作流会话不算）",
    None: "至少一个 AiWork 会话或 iCode 对话会话（工作流运行产生的会话不算）",
}


def check_collect(root: Path) -> tuple[bool, str]:
    """Lab 0：.ldsdt/collect-log.jsonl 中至少有一次收集到本角色辅助工具的会话。

    A 要求 AiWork 会话，B 要求 iCode 对话（chat）会话；只靠评测运行产生的工作流会话不算。
    """
    role = repo_role(root)
    need = COLLECT_NEEDS[role]
    p = root / ".ldsdt" / "collect-log.jsonl"
    if not p.is_file():
        return False, need
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            aiwork = int((entry.get("sessions") or {}).get("aiwork") or 0)
            chat = int(entry.get("icode_chat") or 0)
        except (ValueError, AttributeError, TypeError):
            continue
        if (role == "A" and aiwork) or (role == "B" and chat) or (role is None and (aiwork or chat)):
            return True, need
    return False, need


# ------------------------------------------------------------------ 各模块

def score_a1(root: Path, run_dir: Path, req: Requirement) -> tuple[dict, dict]:
    valid, coverage, index_problems = checks._index(run_dir, req)
    slices_ok, slice_problems = checks._slices(run_dir, req)
    student, fmt_problems = checks._interface_format(run_dir)
    has_format, validator_ok, vdetail = check_format_doc(root, run_dir)
    truth = interface.load_truth(req.path)
    cmp = interface.compare(student, truth, req.meta.get("interface", {}).get("command_name")) if truth else None
    points = {
        "index": 10 * valid,
        "coverage_slices": 7.5 * coverage + 7.5 * slices_ok,
        "interface_commands": 25 * cmp["commands"]["score"] if cmp else 0.0,
        "interface_errors": 30 * cmp["errors"]["score"] if cmp and cmp["errors"] else 0.0,
        "format": 5 * has_format + 5 * bool(validator_ok),
    }
    detail = {"index_valid": valid, "coverage": round(coverage, 4), "slices_ok": slices_ok,
              "problems": index_problems + slice_problems + fmt_problems,
              "interface": cmp, "truth": "ok" if truth else f"缺少 {interface.truth_path(req.path).name}",
              "format_doc": has_format, "validator_ok": validator_ok, "validator_detail": vdetail}
    if cmp and cmp["errors"] is None:
        detail["not_scored"] = ["interface_errors"]
    return points, detail


def score_a2(run_dir: Path, req: Requirement) -> tuple[dict, dict]:
    truth = interface.load_truth(req.path)
    m = checks._manifest(run_dir, req, [c["name"] for c in truth["commands"]] if truth else [])
    points = {"manifest_schema": 10 * m["schema_ok"], "trace": 20 * m["trace"],
              "structure": 20 * m["structure"], "signatures": 20 * m["signatures"]}
    detail = {k: round(m[k], 4) if isinstance(m[k], float) else m[k] for k in ("schema_ok", "trace", "structure", "signatures")}
    detail["problems"] = m["problems"]
    return points, detail


def score_a3(run_dir: Path, req: Requirement, acc) -> tuple[dict, dict]:
    conf, problems = checks._conformance(run_dir, req)
    points = {"contract": 2.5 * acc.contract_ok + 2.5 * acc.readme_ok,
              "install_start": 5 * acc.install_ok + 5 * acc.help_ok,
              "conformance": 15 * conf}
    return points, {"conformance": round(conf, 4), "problems": problems}


def score_a4(root: Path, run_dir: Path, req: Requirement) -> tuple[dict, dict]:
    report_problems = checks.report(run_dir)
    scs, sc_problems = checks._scenarios(run_dir / "tests" / "scenarios.yaml")
    detail: dict = {"report_problems": report_problems, "scenario_problems": sc_problems, "scenario_count": len(scs)}
    points: dict = {"report": 5.0 * (not report_problems)}
    ref = find_reference(root, req.id)
    if ref is None:
        detail["pending"] = ["test_validity", "mutation_kill"]
        detail["note"] = "本地没有参考实现：场景有效率与变异体击杀率在官方复评中计算"
    elif not scs:
        points |= {"test_validity": 0.0, "mutation_kill": 0.0}
    else:
        r = evaluate_tests(ref, scs)
        points |= {"test_validity": 10 * r["validity"], "mutation_kill": 25 * r["kill_rate"]}
        detail["mutation"] = r
    return points, detail


def _sum(points: dict) -> float:
    return sum(v for v in points.values() if v is not None)


# ------------------------------------------------------------------ 打分

def score_task(root: Path, lab: int, req: Requirement, run_dir: Path) -> dict:
    record = read_json(run_dir / "run.json", {}) or {}
    t: dict = {"task_id": req.id, "outcome": record.get("outcome", "missing")}
    if lab == 0:
        frs_score, problems = checks._fr_list(run_dir, req)
        t["points"] = {"workflow_completed": 20.0 * (t["outcome"] == "completed"), "fr_list": 40 * frs_score}
        t["details"] = {"fr_list_problems": problems}
        return t

    a1, d1 = score_a1(root, run_dir, req)
    t["details"] = {"A1": d1}
    if lab == 1:
        t["points"] = a1
        return t
    a2, d2 = score_a2(run_dir, req)
    t["details"]["A2"] = d2
    if lab == 2:
        t["points"] = {"prior_modules": 20 * _sum(a1) / A1_MAX, **a2}
        return t
    acc = evaluate(run_dir / "repo", req)
    t["acceptance"] = acc.to_dict()
    a3, d3 = score_a3(run_dir, req, acc)
    t["details"]["A3"] = d3
    if lab == 3:
        t["points"] = {"prior_modules": 10 * (_sum(a1) + _sum(a2)) / (A1_MAX + A2_MAX), **a3,
                       "scenarios": 50 * acc.pass_rate}
        return t
    a4, d4 = score_a4(root, run_dir, req)
    t["details"]["A4"] = d4
    t["points"] = {"prior_modules": 10 * (_sum(a1) + _sum(a2) + _sum(a3)) / (A1_MAX + A2_MAX + A3_PRE_MAX),
                   **a4, "scenarios": 40 * acc.pass_rate}
    return t


def aggregate(lab: int, tasks: list[dict], doctor_ok: bool, workflow_ok: bool,
              design: tuple[bool, list[str]], root: Path | None = None, kit_free: bool = True) -> dict:
    """门槛：工作流能加载，系统不引用评测工具，且每份计分需求都启动过运行（有 run.json）。
    超时、出错的运行照常按产物计分。"""
    gate = workflow_ok and kit_free and bool(tasks) and all(t["outcome"] != "missing" for t in tasks)
    per_task: dict[str, float] = {}
    for t in tasks:
        for k, v in t["points"].items():
            per_task[k] = per_task.get(k, 0) + v / len(tasks)
    pending = sorted({p for t in tasks for p in (t.get("details", {}).get("A4", {}).get("pending") or [])})
    repo_level: dict[str, float] = {}
    if lab == 0:
        repo_level["doctor"] = 30 * doctor_ok
        repo_level["collect"] = 10 * (check_collect(root)[0] if root else False)
    else:
        repo_level["design_choices"] = 10 * design[0]
    breakdown = {k: round(v, 2) for k, v in {**repo_level, **per_task}.items()}
    total = round(sum(breakdown.values()), 2) if gate else 0.0
    return {"gate_passed": gate, "total": total, "breakdown": breakdown, "pending": pending}


# ------------------------------------------------------------------ 命令

def parse_lab(s: str) -> int:
    s = s.lower().removeprefix("lab")
    if not s.isdigit() or int(s) not in config.LABS:
        die(f"不支持的子任务：{s}（当前支持 {', '.join(f'lab{n}' for n in config.LABS)}）")
    return int(s)


def lab_tasks(root: Path, lab: int, only: list[str] | None) -> list[Requirement]:
    if lab == 0:
        reqs = [parse(root / "tasks" / "practice" / f"{i}.md") for i in config.LAB0_TASKS]
    else:
        reqs = [parse(p) for p in sorted((root / "tasks" / "public").glob("*.md"))]
    if only:
        reqs = [r for r in reqs if r.id in only]
    if not reqs:
        die("没有可用的计分需求")
    return reqs


PENDING_MAX = {"test_validity": 10, "mutation_kill": 25}


def print_task(t: dict, verbose: bool) -> None:
    acc = t.get("acceptance")
    extra = f"，验收场景 {sum(s['passed'] for s in acc['scenarios'])}/{len(acc['scenarios'])}" if acc else ""
    (ok if t["outcome"] == "completed" else warn)(
        f"{t['task_id']}：运行 {t['outcome']}{extra}，本题得分 {_sum(t['points']):.1f}")
    if acc and not acc["install_ok"]:
        info(f"      未能安装：{acc['contract_detail'] or acc['install_detail']}")
    if not verbose:
        return
    for mod, d in (t.get("details") or {}).items():
        probs = d.get("problems") or [] if isinstance(d, dict) else d
        if mod == "A4":
            probs = d["report_problems"] + d["scenario_problems"] + ([d["note"]] if d.get("note") else [])
            mut = d.get("mutation")
            if mut:
                info(f"      [测试] 有效场景 {len(mut['valid'])}/{d['scenario_count']}，"
                     f"击杀变异体 {len(mut['killed'])}/{len(mut['killed']) + len(mut['survived'])}；"
                     f"存活：{[(m, mut['categories'][m]) for m in mut['survived']]}")
        for p in probs[:15]:
            info(f"      [{_MODULE_LABEL.get(mod, mod)}] {p}")
        cmp = d.get("interface") if isinstance(d, dict) else None
        if cmp:
            c = cmp["commands"]
            info(f"      [需求分析] 接口目录·命令：缺少 {c['missing']}，多出 {c['extra']}，参数或选项不一致 {c['mismatched']}")
            if cmp["errors"]:
                info(f"      [需求分析] 接口目录·错误：缺少 {cmp['errors']['missing']}，多出 {cmp['errors']['extra']}")
    for s in (acc or {}).get("scenarios", []):
        if not s["passed"]:
            info(f"      {s['id']}：{'；'.join(s['failures'])}")


def run(args) -> int:
    root = repo_root()
    lab = parse_lab(args.lab)
    reqs = lab_tasks(root, lab, args.task)
    timeout = args.timeout or config.LAB_TIMEOUTS[lab]

    info("== 环境检查")
    doctor.ensure_pull_merges(root)
    checks_ = doctor.checks(root, offline=args.no_run)
    doctor_ok = all(c["ok"] for c in checks_)
    workflow_ok = any(c["name"] == "工作流 ldsdt" and c["ok"] for c in checks_)
    kit_free = all(c["ok"] for c in checks_ if c["name"] == "系统不调用评测工具")
    gateway_busy = any(c.get("warning") for c in checks_ if c["name"] == "Qwen 接口")

    if not args.no_run:
        info("\n== 同步智能体")
        if not sync.sync_agents(verbose=False):
            return 1
        ok("已同步")
        info(f"\n== 在 {len(reqs)} 份计分需求上运行系统")
        for req in reqs:
            run_task(root, lab, req, timeout)

    info("\n== 打分")
    tasks = []
    for req in reqs:
        run_dir = root / "runs" / f"lab{lab}" / req.id
        if not (run_dir / "run.json").is_file():
            bad(f"{req.id}：没有运行产物（runs/lab{lab}/{req.id}/run.json）")
            tasks.append({"task_id": req.id, "outcome": "missing", "points": {}})
            continue
        t = score_task(root, lab, req, run_dir)
        tasks.append(t)
        print_task(t, args.verbose)

    design = check_design_choices(root, lab)
    result = aggregate(lab, tasks, doctor_ok, workflow_ok, design, root, kit_free=kit_free)
    report = {
        "lab": lab, "time": now_iso(), "no_run": args.no_run, "platform": platform_label(),
        "kit_version": config.KIT_VERSION, "kit_hash": kit_hash(root), "git": git_state(root),
        "doctor_ok": doctor_ok, "design_choices_problems": design[1], **result, "tasks": tasks,
    }
    write_json(root / "runs" / f"lab{lab}" / "grade.json", report)
    append_jsonl(ldsdt_dir(root) / "grade-history.jsonl",
                 {k: report[k] for k in ("lab", "time", "no_run", "platform", "kit_version", "kit_hash", "git",
                                         "doctor_ok", "gate_passed", "total", "breakdown", "pending")}
                 | {"tasks": [{"task_id": t["task_id"], "outcome": t["outcome"], "points": t.get("points"),
                               "pass_rate": (t.get("acceptance") or {}).get("pass_rate")} for t in tasks]})

    info("")
    for k, v in result["breakdown"].items():
        info(f"  {k:<20}{v:>7.2f}")
    for k in result["pending"]:
        info(f"  {k:<20}{'待复评':>7}（满分 {PENDING_MAX[k]}）")
    if result["gate_passed"]:
        rest = f"，另有 {sum(PENDING_MAX[k] for k in result['pending'])} 分在官方复评中计算" if result["pending"] else ""
        info(f"\n评测分：{result['total']:.2f} / 100{rest}（可以 `uv run ldsdt submit lab{lab}`）")
    else:
        warn("门槛未通过：工作流必须能加载（doctor 中「工作流 ldsdt」通过），系统不得引用评测工具 ldsdt_kit"
             "（doctor 中「系统不调用评测工具」通过），并在每份计分需求上都运行过，否则评测分为 0。")
    for p in design[1]:
        warn(p)
    if not doctor_ok:
        warn("doctor 有未通过的检查，运行 `uv run ldsdt doctor` 查看。")
    if gateway_busy:
        warn("评测开始时课程网关繁忙（doctor 的 Qwen 接口检查超时），这一项没有扣分。如果系统运行也因此超时或出错，"
             "请过一段时间重新运行 `uv run ldsdt grade lab" + str(lab) + "`，以最后一次提交为准。")
    if lab == 0 and not result["breakdown"].get("collect"):
        warn(f"「会话收集」还没有得分：需要{check_collect(root)[1]}。在本仓库中这样工作后，"
             "运行 `uv run ldsdt collect --week 1`，再重新评测。")
    info(f"详细结果：runs/lab{lab}/grade.json（加 -v 显示问题与失败场景）")
    return 0 if result["gate_passed"] else 1


def try_run(args) -> int:
    """ldsdt try <需求文档> [--lab N]：在任意需求上运行系统，按 Lab N 的评分项检查，不计分。"""
    root = repo_root()
    path = Path(args.requirement)
    if not path.is_file():
        die(f"找不到需求文档：{path}")
    req = parse(path)
    lab = parse_lab(str(args.lab))
    run_dir = root / "runs" / "try" / req.id
    if not args.no_run:
        if not sync.sync_agents(verbose=False):
            return 1
        run_task(root, lab, req, args.timeout or config.LAB_TIMEOUTS[lab], run_dir)
    elif not (run_dir / "run.json").is_file():
        die(f"没有已有产物：{run_dir}")
    t = score_task(root, lab, req, run_dir)
    write_json(run_dir / "result.json", t)
    append_jsonl(ldsdt_dir(root) / "grade-history.jsonl",
                 {"lab": "try", "try_lab": lab, "time": now_iso(), "no_run": args.no_run, "platform": platform_label(),
                  "kit_version": config.KIT_VERSION, "git": git_state(root),
                  "tasks": [{"task_id": req.id, "outcome": t["outcome"], "points": t["points"],
                             "pass_rate": (t.get("acceptance") or {}).get("pass_rate")}]})
    print_task(t, args.verbose)
    for k, v in t["points"].items():
        info(f"  {k:<20}{v:>7.2f}")
    used = find_kit_usage(root)
    if used:
        warn(f"以下文件引用了课程工具包 ldsdt_kit：{', '.join(used[:5])}。学生系统不得导入或调用评测工具，"
             "正式评测时门槛不通过，评测分为 0。")
    if t["outcome"] != "completed":
        err = str((read_json(run_dir / "run.json", {}) or {}).get("error") or "").strip().splitlines()
        if err:
            info(f"      出错信息：{err[-1][:300]}")
    info(f"详细结果：runs/try/{req.id}/result.json（不计分）")
    return 0
