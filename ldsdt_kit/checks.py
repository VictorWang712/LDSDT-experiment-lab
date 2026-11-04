"""各模块产物的结构检查。评测与学生工作流共用：工作流的 Python 节点可以直接调用。

    from ldsdt_kit import checks
    problems = checks.spec(run_dir)        # 空列表表示通过

公开函数（spec、manifest、conformance、scenarios、report、fr_list）只返回问题列表，不涉及评分依据中的答案；
以下划线开头的函数返回评分需要的细节，供 grade 使用。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath

import yaml

from .reqdoc import Requirement, Scenario, parse, parse_scenario_items

MAX_SCENARIOS = 80
MAX_STEPS = 20


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _req(run_dir: Path, req: Requirement | None) -> Requirement:
    return req or parse(Path(run_dir) / "input.md")


def _str_list(x) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def _cycle(nodes: set[str], edges: list[tuple[str, str]]) -> bool:
    """edges 为 (a, b)：a 依赖 b。只考虑两端都在 nodes 中的边。"""
    deps = {n: {b for a, b in edges if a == n and b in nodes} for n in nodes}
    done: set[str] = set()
    while True:
        ready = [n for n in deps if n not in done and deps[n] <= done]
        if not ready:
            return len(done) < len(nodes)
        done |= set(ready)


# ------------------------------------------------------------------ Lab 0

def fr_list(run_dir: Path, req: Requirement | None = None) -> list[str]:
    """warmup/fr-list.json：{"requirement_id", "frs": [{"id", "summary"}]}。"""
    return _fr_list(Path(run_dir), _req(run_dir, req))[1]


def _fr_list(run_dir: Path, req: Requirement) -> tuple[float, list[str]]:
    data = _load(run_dir / "warmup" / "fr-list.json")
    if not isinstance(data, dict) or not isinstance(data.get("frs"), list):
        return 0.0, ["warmup/fr-list.json 不存在，或不是含 frs 数组的 JSON 对象"]
    problems = []
    ids, with_summary = [], 0
    for i, it in enumerate(data["frs"]):
        if not (isinstance(it, dict) and isinstance(it.get("id"), str)):
            problems.append(f"frs[{i}] 缺少 id")
            continue
        ids.append(it["id"])
        if isinstance(it.get("summary"), str) and it["summary"].strip():
            with_summary += 1
        else:
            problems.append(f"{it['id']} 的 summary 为空")
    want, got = set(req.frs), set(ids)
    if want - got:
        problems.append(f"缺少：{sorted(want - got)}")
    if got - want:
        problems.append(f"需求中没有这些编号：{sorted(got - want)}")
    if len(ids) != len(got):
        problems.append("有重复的编号")
    jaccard = len(want & got) / len(want | got) if want | got else 0.0
    return jaccard * (with_summary / len(ids) if ids else 0.0), problems


# ------------------------------------------------------------------ Lab 1：spec/

def spec(run_dir: Path, req: Requirement | None = None) -> list[str]:
    """spec/index.json（格式、FR 覆盖、切片）、spec/interface.json（格式）与 spec/FORMAT.md。"""
    run_dir, req = Path(run_dir), _req(run_dir, req)
    _, coverage, problems = _index(run_dir, req)
    problems += _slices(run_dir, req)[1]
    problems += _interface_format(run_dir)[1]
    if not (run_dir / "spec" / "FORMAT.md").is_file():
        problems.append("缺少 spec/FORMAT.md")
    return problems


def _index(run_dir: Path, req: Requirement) -> tuple[bool, float, list[str]]:
    """spec/index.json：合法性与 FR 覆盖率。"""
    data = _load(run_dir / "spec" / "index.json")
    if not isinstance(data, dict):
        return False, 0.0, ["spec/index.json 不存在或不是合法 JSON 对象"]
    problems: list[str] = []
    items = data.get("items")
    if not isinstance(items, list):
        problems.append("index.json 缺少 items 数组")
        items = []
    if not isinstance(data.get("assumptions"), list):
        problems.append("index.json 缺少 assumptions 数组")
    covered = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not isinstance(it.get("fr"), str):
            problems.append(f"items[{i}] 缺少 fr")
            continue
        if not (_str_list(it.get("spec_ids")) and it["spec_ids"]):
            problems.append(f"items[{i}]（{it['fr']}）spec_ids 必须是非空字符串数组")
            continue
        if not (_str_list(it.get("files")) and it["files"]):
            problems.append(f"items[{i}]（{it['fr']}）files 必须是非空字符串数组")
            continue
        missing = [f for f in it["files"] if not (run_dir / f).is_file()]
        if missing:
            problems.append(f"{it['fr']} 引用的文件不存在（路径相对于运行目录）：{missing}")
            continue
        covered.add(it["fr"])
    for i, a in enumerate(data.get("assumptions") or []):
        if not (isinstance(a, dict) and isinstance(a.get("id"), str) and isinstance(a.get("text"), str)):
            problems.append(f"assumptions[{i}] 需要 id 与 text 字符串")
    uncovered = [fr for fr in req.frs if fr not in covered]
    if uncovered:
        problems.append(f"index.json 未覆盖的 FR：{uncovered}")
    coverage = 1 - len(uncovered) / len(req.frs) if req.frs else 0.0
    return not problems, coverage, problems


def _slices(run_dir: Path, req: Requirement) -> tuple[bool, list[str]]:
    """每条 FR 恰好属于一个切片，依赖都指向已有切片且无环。"""
    data = _load(run_dir / "spec" / "index.json")
    slices = data.get("slices") if isinstance(data, dict) else None
    if not isinstance(slices, list) or not slices:
        return False, ["index.json 缺少非空的 slices 数组"]
    problems: list[str] = []
    owner: dict[str, str] = {}
    deps: dict[str, list[str]] = {}
    for i, s in enumerate(slices):
        if not (isinstance(s, dict) and isinstance(s.get("id"), str) and _str_list(s.get("frs"))
                and _str_list(s.get("depends_on", []))):
            problems.append(f"slices[{i}] 需要 id（字符串）、frs 与 depends_on（字符串数组）")
            continue
        if s["id"] in deps:
            problems.append(f"切片 {s['id']} 重复")
        deps[s["id"]] = list(s.get("depends_on", []))
        for fr in s["frs"]:
            if fr in owner:
                problems.append(f"{fr} 同时属于 {owner[fr]} 与 {s['id']}")
            owner[fr] = s["id"]
    missing = [fr for fr in req.frs if fr not in owner]
    if missing:
        problems.append(f"没有归入任何切片的 FR：{missing}")
    for sid, ds in deps.items():
        for d in ds:
            if d not in deps:
                problems.append(f"切片 {sid} 依赖不存在的切片 {d}")
    if _cycle(set(deps), [(a, b) for a, ds in deps.items() for b in ds]):
        problems.append("切片依赖有环")
    return not problems, problems


def _interface_format(run_dir: Path) -> tuple[dict | None, list[str]]:
    """spec/interface.json：{"commands": [{name, args, options, frs}], "errors": [{command, message, exit, frs}]}。"""
    data = _load(run_dir / "spec" / "interface.json")
    if not isinstance(data, dict):
        return None, ["spec/interface.json 不存在或不是合法 JSON 对象"]
    problems = []
    for key, fields in (("commands", {"name": str, "args": list, "options": list}),
                        ("errors", {"command": str, "message": str, "exit": int})):
        items = data.get(key)
        if not isinstance(items, list):
            problems.append(f"interface.json 缺少 {key} 数组")
            continue
        for i, it in enumerate(items):
            bad = [f for f, t in fields.items() if not (isinstance(it, dict) and isinstance(it.get(f), t)
                                                        and not isinstance(it.get(f), bool))]
            if bad:
                problems.append(f"{key}[{i}] 缺少或类型错误的字段：{bad}")
            elif not all(_str_list(it[f]) for f, ty in fields.items() if ty is list):
                problems.append(f"{key}[{i}] 的 args 与 options 必须是字符串数组")
            elif key == "errors" and it["exit"] == 0:
                problems.append(f"errors[{i}] 的 exit 为 0：接口目录只列让命令以非零退出码结束的错误"
                                "（退出码 0 的逐行报告、警告不算错误）")
    return data, problems


# ------------------------------------------------------------------ Lab 2：design/manifest.json

def manifest(run_dir: Path, req: Requirement | None = None) -> list[str]:
    """manifest 的格式、追溯（对照本次运行自己的 spec/interface.json）、结构与签名。"""
    run_dir, req = Path(run_dir), _req(run_dir, req)
    own = _load(run_dir / "spec" / "interface.json")
    commands = [c.get("name") for c in (own or {}).get("commands", []) if isinstance(c, dict)] if isinstance(own, dict) else []
    r = _manifest(run_dir, req, [c for c in commands if isinstance(c, str)])
    return r["problems"]


def parse_signature(sig: str) -> tuple[str, str, int | None] | None:
    """把 `def f(a, b) -> X` 或 `class C(Base)` 解析为 (kind, name, 参数个数)。类的参数个数为 None。"""
    s = sig.strip().rstrip(":").strip()
    try:
        tree = ast.parse(s + ": ...")
    except SyntaxError:
        return None
    if len(tree.body) != 1:
        return None
    node = tree.body[0]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "def", node.name, _param_count(node.args)
    if isinstance(node, ast.ClassDef):
        return "class", node.name, None
    return None


def _param_count(a: ast.arguments) -> int:
    return len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)


def normalize_command(name: str, program: str | None = None) -> str:
    parts = str(name).split()
    if program and parts and parts[0] == program:
        parts = parts[1:]
    return " ".join(parts)


def _manifest(run_dir: Path, req: Requirement, commands: list[str]) -> dict:
    """返回 {schema_ok, trace, structure, signatures, problems, modules, interfaces}；各项为 0–1。"""
    out = {"schema_ok": False, "trace": 0.0, "structure": 0.0, "signatures": 0.0, "problems": [],
           "modules": {}, "interfaces": {}}
    data = _load(run_dir / "design" / "manifest.json")
    if not isinstance(data, dict):
        out["problems"].append("design/manifest.json 不存在或不是合法 JSON 对象")
        return out
    problems = out["problems"]
    shapes = {
        "modules": {"name": str, "path": str, "responsibility": str},
        "interfaces": {"module": str, "signature": str},
        "dependencies": {"from": str, "to": str},
        "trace": {"interfaces": list},
        "plan": {"id": str, "module": str, "frs": list, "depends_on": list},
    }
    rows: dict[str, list[dict]] = {}
    for key, fields in shapes.items():
        items = data.get(key)
        if not isinstance(items, list) or (key == "modules" and not items):
            problems.append(f"manifest 缺少{'非空的 ' if key == 'modules' else ' '}{key} 数组")
            rows[key] = []
            continue
        good = []
        for i, it in enumerate(items):
            bad = [f for f, t in fields.items() if not (isinstance(it, dict) and isinstance(it.get(f), t))]
            if key == "trace" and isinstance(it, dict) and not (isinstance(it.get("fr"), str) or isinstance(it.get("command"), str)):
                bad.append("fr 或 command")
            if bad:
                problems.append(f"{key}[{i}] 缺少或类型错误的字段：{bad}")
            else:
                good.append(it)
        rows[key] = good
    out["schema_ok"] = not problems

    modules = {m["name"]: m["path"] for m in rows["modules"]}
    out["modules"] = modules
    interfaces: dict[str, tuple[str, str, int | None]] = {}   # "module.name" -> (module, kind, n)
    parsed = 0
    for it in rows["interfaces"]:
        sig = parse_signature(it["signature"])
        if sig is None:
            problems.append(f"签名无法解析：{it['module']}: {it['signature']}")
            continue
        if it["module"] not in modules:
            problems.append(f"接口 {sig[1]} 所属的模块 {it['module']} 不在 modules 中")
            continue
        parsed += 1
        interfaces[f"{it['module']}.{sig[1]}"] = (it["module"], sig[0], sig[2])
    out["interfaces"] = interfaces
    out["signatures"] = parsed / len(rows["interfaces"]) if rows["interfaces"] else 0.0

    # 追溯：每条 FR、每个命令都至少追溯到一个存在的接口
    targets = [("fr", f) for f in req.frs] + [("command", normalize_command(c, req.meta.get("interface", {}).get("command_name")))
                                               for c in commands]
    traced = set()
    for t in rows["trace"]:
        if any(ref in interfaces for ref in t["interfaces"] if isinstance(ref, str)):
            key = ("fr", t["fr"]) if isinstance(t.get("fr"), str) else (
                "command", normalize_command(t["command"], req.meta.get("interface", {}).get("command_name")))
            traced.add(key)
    untraced = [v for v in targets if v not in traced]
    if untraced:
        problems.append(f"没有追溯到已声明接口（模块名.函数或类名）的 FR/命令：{[v for _, v in untraced]}")
    out["trace"] = 1 - len(untraced) / len(targets) if targets else 0.0

    # 结构：5 项检查各占 1/5
    ok = []
    edges = [(d["from"], d["to"]) for d in rows["dependencies"]]
    bad_edges = [e for e in edges if e[0] not in modules or e[1] not in modules]
    if bad_edges:
        problems.append(f"dependencies 引用了不存在的模块：{bad_edges}")
    if _cycle(set(modules), edges):
        problems.append("模块依赖有环")
    ok.append(not bad_edges and not _cycle(set(modules), edges))
    linked = {m for e in edges for m in e}
    orphans = [m for m in modules if m not in linked] if len(modules) > 1 else []
    if orphans:
        problems.append(f"孤立模块（没有任何依赖边）：{orphans}")
    ok.append(not orphans)
    bad_paths = [p for p in modules.values() if not _good_path(p)]
    if bad_paths or len(set(modules.values())) != len(modules):
        problems.append(f"模块路径必须是相对于目标仓库根目录、不含 ..、以 .py 结尾且互不相同的路径：{bad_paths}")
    ok.append(not bad_paths and len(set(modules.values())) == len(modules))
    planned_modules = {t["module"] for t in rows["plan"]}
    planned_frs = {f for t in rows["plan"] for f in t["frs"]}
    miss = sorted(set(modules) - planned_modules) + [f for f in req.frs if f not in planned_frs]
    if miss:
        problems.append(f"plan 没有覆盖的模块或 FR：{miss}")
    ok.append(bool(rows["plan"]) and not miss)
    tasks = [t["id"] for t in rows["plan"]]
    plan_edges = [(t["id"], d) for t in rows["plan"] for d in t["depends_on"]]
    plan_bad = (len(set(tasks)) != len(tasks) or any(d not in tasks for _, d in plan_edges)
                or any(t["module"] not in modules for t in rows["plan"]) or _cycle(set(tasks), plan_edges))
    if plan_bad:
        problems.append("plan 的任务编号必须唯一，depends_on 指向已有任务且无环，module 必须是已声明的模块")
    ok.append(bool(rows["plan"]) and not plan_bad)
    out["structure"] = sum(ok) / len(ok)
    return out


def _good_path(p: str) -> bool:
    pp = PurePosixPath(p.replace("\\", "/"))
    return bool(p) and not pp.is_absolute() and ".." not in pp.parts and pp.suffix == ".py" and ":" not in p


# ------------------------------------------------------------------ Lab 3：目标仓库与设计一致

def conformance(run_dir: Path) -> list[str]:
    return _conformance(Path(run_dir))[1]


def _conformance(run_dir: Path, req: Requirement | None = None) -> tuple[float, list[str]]:
    """manifest 中的模块文件存在；接口以相同名字（函数还要相同参数个数）定义在模块文件的顶层。"""
    m = _manifest(run_dir, _req(run_dir, req), [])
    modules, interfaces = m["modules"], m["interfaces"]
    if not modules:
        return 0.0, ["没有可用的 design/manifest.json，无法检查设计一致性"]
    repo = run_dir / "repo"
    problems, passed, total = [], 0, len(modules) + len(interfaces)
    defs: dict[str, dict[str, tuple[str, int | None]]] = {}
    for name, path in modules.items():
        f = repo / path
        if not (_good_path(path) and f.is_file()):
            problems.append(f"模块 {name} 的文件 {path} 不存在")
            continue
        passed += 1
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            problems.append(f"{path} 无法解析：{e}")
            continue
        found = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[node.name] = ("def", _param_count(node.args))
            elif isinstance(node, ast.ClassDef):
                found[node.name] = ("class", None)
        defs[name] = found
    for ref, (module, kind, n) in interfaces.items():
        name = ref.split(".", 1)[1]
        got = defs.get(module, {}).get(name)
        if got is None:
            problems.append(f"{modules[module]} 中没有顶层的 {name}")
        elif got[0] != kind or (kind == "def" and got[1] != n):
            problems.append(f"{modules[module]} 中的 {name} 与设计不一致（设计：{kind}，{n} 个参数；实际：{got[0]}，{got[1]} 个参数）")
        else:
            passed += 1
    return passed / total if total else 0.0, problems


# ------------------------------------------------------------------ Lab 4：tests/

def scenarios(path: Path) -> list[str]:
    return _scenarios(Path(path))[1]


def _scenarios(path: Path) -> tuple[list[Scenario], list[str]]:
    """tests/scenarios.yaml：与需求文档验收场景同格式的 YAML 列表。"""
    try:
        items = yaml.safe_load(path.read_text(encoding="utf-8"))
        scs = parse_scenario_items(items)
    except OSError:
        return [], [f"{path.name} 不存在"]
    except (yaml.YAMLError, ValueError, TypeError, AttributeError) as e:
        return [], [f"{path.name} 格式错误：{e}"]
    problems = []
    ids = [s.id for s in scs]
    if len(set(ids)) != len(ids):
        problems.append("场景编号有重复")
    if len(scs) > MAX_SCENARIOS:
        problems.append(f"场景超过 {MAX_SCENARIOS} 个，只评前 {MAX_SCENARIOS} 个")
    long = [s.id for s in scs if len(s.steps) > MAX_STEPS or not s.steps]
    if long:
        problems.append(f"这些场景没有步骤或超过 {MAX_STEPS} 步，不参与评分：{long}")
    usable = [s for s in scs[:MAX_SCENARIOS] if 0 < len(s.steps) <= MAX_STEPS]
    return usable, problems


def report(run_dir: Path) -> list[str]:
    """tests/report.json：{"iterations": [{"round", "scenarios", "passed", "dispatch"}]}，至少一轮。"""
    data = _load(Path(run_dir) / "tests" / "report.json")
    its = data.get("iterations") if isinstance(data, dict) else None
    if not isinstance(its, list) or not its:
        return ["tests/report.json 不存在，或没有非空的 iterations 数组"]
    problems = []
    for i, it in enumerate(its):
        if not (isinstance(it, dict) and all(isinstance(it.get(k), int) for k in ("round", "scenarios", "passed"))
                and isinstance(it.get("dispatch", {}), dict)):
            problems.append(f"iterations[{i}] 需要整数 round、scenarios、passed，以及对象 dispatch")
    return problems
