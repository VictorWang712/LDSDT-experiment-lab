"""ldsdt_kit 的离线单元测试（不调用模型、不需要 iCode）。"""

import json
import textwrap
from pathlib import Path

import pytest

from ldsdt_kit import acceptance, checks, config, grade, interface, mutants, secrets, sync
from ldsdt_kit.reqdoc import parse

ROOT = Path(__file__).resolve().parents[1]

ECHO_DOC = textwrap.dedent("""\
    ---
    id: echo
    title: 回显
    ---
    # 功能需求
    - **FR-001** `echo say <文本>` 输出 `You said: <文本>`。
    - **FR-002** `echo fail` 在 stderr 报错，退出码 3。
    - **FR-001** 重复出现的编号只算一次。

    # 验收场景
    ```yaml
    - id: AS-001
      covers: [FR-001]
      files:
        note.txt: "hi"
      steps:
        - run: [say, "你好"]
          expect: {exit: 0, stdout_contains: ["You said: 你好"], stdout_not_contains: ["Traceback"]}
    - id: AS-002
      covers: [FR-002]
      steps:
        - run: [fail]
          expect: {exit: 3, stderr_nonempty: true}
    - id: AS-003
      covers: [FR-001]
      steps:
        - run: [say, "x"]
          expect: {exit: 0, stdout_regex: "^Wrong"}
    ```
    """)

ECHO_MAIN = textwrap.dedent("""\
    import sys
    if sys.argv[1:2] == ["--help"]:
        print("usage: echo"); sys.exit(0)
    if sys.argv[1] == "say":
        print("You said: " + sys.argv[2])
    else:
        print("boom", file=sys.stderr); sys.exit(3)
    """)


@pytest.fixture
def echo(tmp_path):
    doc = tmp_path / "echo.md"
    doc.write_text(ECHO_DOC, encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / "echo").mkdir(parents=True)
    (repo / "echo" / "__main__.py").write_text(ECHO_MAIN, encoding="utf-8")
    (repo / "README.md").write_text("# echo\n", encoding="utf-8")
    (repo / "ldsdt-run.json").write_text(json.dumps({"install": [], "run": ["python", str(repo / "echo" / "__main__.py")]}))
    return parse(doc), repo


def test_parse(echo):
    req, _ = echo
    assert req.id == "echo"
    assert req.frs == ["FR-001", "FR-002"]
    assert [s.id for s in req.scenarios] == ["AS-001", "AS-002", "AS-003"]
    assert req.scenarios[0].files == {"note.txt": "hi"}


def test_evaluate(echo):
    req, repo = echo
    rep = acceptance.evaluate(repo, req)
    assert rep.contract_ok and rep.readme_ok and rep.install_ok and rep.help_ok
    assert [s.passed for s in rep.scenarios] == [True, True, False]
    assert "不匹配" in rep.scenarios[2].failures[0]


def test_evaluate_missing_contract(echo):
    req, repo = echo
    (repo / "ldsdt-run.json").unlink()
    rep = acceptance.evaluate(repo, req)
    assert not rep.contract_ok and rep.pass_rate == 0


def test_check_step():
    assert acceptance.check_step({"exit": "nonzero"}, 2, "", "") == []
    assert acceptance.check_step({"exit": "nonzero"}, 0, "", "")
    assert acceptance.check_step({"stdout_contains": ["a"]}, 0, "b", "")


def task_docs():
    return sorted((ROOT / "tasks" / "public").glob("*.md")) + sorted((ROOT / "tasks" / "practice").glob("*.md"))


def test_public_tasks_parse():
    docs = task_docs()
    assert docs
    for p in docs:
        req = parse(p)
        assert req.id == p.stem
        known = set(req.frs) | set(req.rules) | {"NFR-001", "NFR-002"}
        covered = {c for s in req.scenarios for c in s.covers}
        assert set(req.frs) <= covered, f"{p.name} 有未被验收场景覆盖的 FR：{set(req.frs) - covered}"
        assert covered <= known, f"{p.name} 的 covers 引用了不存在的编号：{covered - known}"
        assert len({s.id for s in req.scenarios}) == len(req.scenarios), f"{p.name} 场景 id 重复"


def test_lab_tasks():
    sizes = {p.stem: len(parse(p).frs) for p in (ROOT / "tasks" / "public").glob("*.md")}
    assert sizes == {"library": 25, "timesheet": 15}
    for tid in config.LAB0_TASKS:
        assert (ROOT / "tasks" / "practice" / f"{tid}.md").is_file()


def test_truth_files():
    for p in task_docs():
        truth = interface.load_truth(p)
        if p.parent.name == "public":
            assert truth and truth["errors"], p.name
        if not truth:
            continue
        req = parse(p)
        names = [c["name"] for c in truth["commands"]]
        assert len(set(names)) == len(names)
        refs = {f for x in truth["commands"] + (truth["errors"] or []) for f in x["frs"]}
        assert refs <= set(req.frs) | set(req.rules), (p.name, refs - set(req.frs) - set(req.rules))


def test_interface_compare():
    truth = {"commands": [{"name": "reader add", "args": ["证号", "姓名"], "options": ["--type"]},
                          {"name": "stats", "args": [], "options": []}],
             "errors": [{"message": "error: reader <证号> not found", "exit": 3},
                        {"message": "error: empty name", "exit": 2}]}
    same = interface.compare(truth, truth, "lib")
    assert same["commands"]["score"] == 1 and same["errors"]["score"] == 1
    student = {"commands": [{"name": "lib reader add", "args": ["id", "name"], "options": ["--type student|staff"]},
                            {"name": "reader list", "args": [], "options": []}],
               "errors": [{"message": "error: reader <id> not found", "exit": 3},
                          {"message": "error: empty <field>", "exit": 2},
                          {"message": "error: <说明>", "exit": 2},
                          {"message": "error: reader <id> not found", "exit": 4}]}
    r = interface.compare(student, truth, "lib")
    assert r["commands"]["missing"] == ["stats"] and r["commands"]["extra"] == ["reader list"]
    assert r["commands"]["score"] == 0.5 * 0.5 + 0.5 * 0.5
    assert r["errors"]["missing"] == []
    assert len(r["errors"]["extra"]) == 2          # 过于笼统的信息不算命中；退出码不同不算命中
    assert interface.compare(None, truth, "lib")["commands"]["score"] == 0
    # 退出码 0 的逐行报告不算错误：不参与比对，也不算多列
    with_reports = {**truth, "errors": truth["errors"] + [{"message": "line <行号>: unknown reader", "exit": 0}]}
    r = interface.compare(with_reports, truth, "lib")
    assert r["errors"]["score"] == 1 and r["errors"]["extra"] == []


def make_run(tmp_path, req_text):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "input.md").write_text(req_text, encoding="utf-8")
    return run_dir


def test_fr_list(tmp_path):
    run_dir = make_run(tmp_path, ECHO_DOC)
    assert checks.fr_list(run_dir)
    (run_dir / "warmup").mkdir()
    (run_dir / "warmup" / "fr-list.json").write_text(json.dumps(
        {"requirement_id": "echo", "frs": [{"id": "FR-001", "summary": "回显"}, {"id": "FR-002", "summary": "报错"}]}))
    assert checks.fr_list(run_dir) == []
    assert checks._fr_list(run_dir, parse(run_dir / "input.md"))[0] == 1


def test_spec_checks(tmp_path):
    run_dir = make_run(tmp_path, ECHO_DOC)
    req = parse(run_dir / "input.md")
    (run_dir / "spec").mkdir()
    (run_dir / "spec" / "a.md").write_text("x")
    index = {"requirement_id": "echo",
             "items": [{"fr": "FR-001", "spec_ids": ["S1"], "files": ["spec/a.md"]},
                       {"fr": "FR-002", "spec_ids": ["S2"], "files": ["spec/missing.md"]}],
             "assumptions": [{"id": "ASM-1", "text": "t"}],
             "slices": [{"id": "a", "frs": ["FR-001"], "depends_on": ["b"]},
                        {"id": "b", "frs": ["FR-002"], "depends_on": ["a"]}]}
    (run_dir / "spec" / "index.json").write_text(json.dumps(index))
    valid, coverage, problems = checks._index(run_dir, req)
    assert not valid and coverage == 0.5 and "不存在" in problems[0]
    ok, problems = checks._slices(run_dir, req)
    assert not ok and "环" in problems[-1]
    all_problems = checks.spec(run_dir)
    assert any("interface.json" in p for p in all_problems) and any("FORMAT.md" in p for p in all_problems)
    (run_dir / "spec" / "interface.json").write_text(json.dumps(
        {"commands": [{"name": "say", "args": ["文本"], "options": []}], "errors": [{"command": "fail", "message": "x", "exit": "3"}]}))
    assert any("errors[0]" in p for p in checks._interface_format(run_dir)[1])
    (run_dir / "spec" / "interface.json").write_text(json.dumps(
        {"commands": [], "errors": [{"command": "import", "message": "line <行号>: bad", "exit": 0}]}))
    assert any("exit 为 0" in p for p in checks._interface_format(run_dir)[1])


MANIFEST = {
    "modules": [{"name": "cli", "path": "echo/cli.py", "responsibility": "命令行"},
                {"name": "core", "path": "echo/core.py", "responsibility": "逻辑"}],
    "interfaces": [{"module": "cli", "signature": "def main(argv: list[str] | None = None) -> int"},
                   {"module": "core", "signature": "def say(text: str) -> str"},
                   {"module": "core", "signature": "class Store"}],
    "dependencies": [{"from": "cli", "to": "core"}],
    "trace": [{"fr": "FR-001", "interfaces": ["core.say"]}, {"fr": "FR-002", "interfaces": ["cli.main"]},
              {"command": "say", "interfaces": ["cli.main"]}],
    "plan": [{"id": "T1", "module": "core", "frs": ["FR-001"], "depends_on": []},
             {"id": "T2", "module": "cli", "frs": ["FR-002"], "depends_on": ["T1"]}],
}


def test_manifest_and_conformance(tmp_path):
    run_dir = make_run(tmp_path, ECHO_DOC)
    req = parse(run_dir / "input.md")
    (run_dir / "design").mkdir()
    (run_dir / "design" / "manifest.json").write_text(json.dumps(MANIFEST))
    m = checks._manifest(run_dir, req, ["say", "echo fail"])
    assert m["schema_ok"] and m["signatures"] == 1 and m["structure"] == 1
    assert m["trace"] == 3 / 4 and "fail" in m["problems"][0]
    bad = dict(MANIFEST, dependencies=[{"from": "cli", "to": "core"}, {"from": "core", "to": "cli"}],
               interfaces=MANIFEST["interfaces"] + [{"module": "core", "signature": "def broken("}])
    (run_dir / "design" / "manifest.json").write_text(json.dumps(bad))
    m = checks._manifest(run_dir, req, [])
    assert m["structure"] == 0.8 and m["signatures"] == 3 / 4
    (run_dir / "design" / "manifest.json").write_text(json.dumps(MANIFEST))
    pkg = run_dir / "repo" / "echo"
    pkg.mkdir(parents=True)
    (pkg / "cli.py").write_text("def main(argv=None):\n    return 0\n")
    (pkg / "core.py").write_text("def say(text, loud):\n    return text\n")
    score, problems = checks._conformance(run_dir, req)
    assert score == 3 / 5 and any("Store" in p for p in problems) and any("say" in p for p in problems)


def test_scenarios_and_report(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("- id: X1\n  steps:\n    - run: [a]\n      expect: {exit: 0, stderr_contains: [boom]}\n"
                 "- id: X1\n  steps: []\n", encoding="utf-8")
    scs, problems = checks._scenarios(p)
    assert [s.id for s in scs] == ["X1"] and len(problems) == 2
    p.write_text("- id: X1\n  steps:\n    - run: [a]\n      expect: {stdout_has: [x]}\n", encoding="utf-8")
    assert "格式错误" in checks.scenarios(p)[0]
    run_dir = tmp_path / "run"
    (run_dir / "tests").mkdir(parents=True)
    assert checks.report(run_dir)
    (run_dir / "tests" / "report.json").write_text(json.dumps(
        {"iterations": [{"round": 1, "scenarios": 3, "passed": 2, "dispatch": {"impl": 1}}]}))
    assert checks.report(run_dir) == []


def test_mutants_practice():
    for tid in config.LAB0_TASKS:
        ref = mutants.find_reference(ROOT, tid)
        assert ref and ref.mutants
        req = parse(ROOT / "tasks" / "practice" / f"{tid}.md")
        r = mutants.evaluate_tests(ref, req.scenarios)
        assert r["invalid"] == {} and r["killed"] == {}, (tid, r)
        assert r["validity"] == len(req.scenarios) / 10
    ref = mutants.find_reference(ROOT, "todo-cli")
    sc = checks.parse_scenario_items([{"id": "K", "steps": [
        {"run": ["add", "buy milk"], "expect": {"exit": 0}},
        {"run": ["list"], "expect": {"stdout_contains": ["#1 [ ] buy milk"]}}]}])
    r = mutants.evaluate_tests(ref, sc)
    assert r["valid"] == ["K"] and list(r["killed"]) == ["M03"]


def test_aggregate_gate():
    tasks = [{"outcome": "completed", "points": {"scenarios": 40}}, {"outcome": "timeout", "points": {"scenarios": 20}}]
    r = grade.aggregate(3, tasks, True, True, (True, []))
    assert r["gate_passed"] and r["total"] == 10 + 30
    assert grade.aggregate(3, tasks, True, False, (True, []))["total"] == 0
    tasks[1] = {"outcome": "missing", "points": {}}
    assert not grade.aggregate(3, tasks, True, True, (True, []))["gate_passed"]
    r = grade.aggregate(0, [{"outcome": "completed", "points": {"fr_list": 40}}], True, True, (True, []), ROOT)
    assert r["breakdown"]["doctor"] == 30 and "design_choices" not in r["breakdown"]


def test_design_choices_template():
    for lab in (1, 2, 3, 4):
        ok, problems = grade.check_design_choices(ROOT, lab)
        assert len(problems) == len(config.DESIGN_DIMENSIONS[lab])


def test_parse_rules(tmp_path):
    doc = tmp_path / "r.md"
    doc.write_text("---\nid: r\n---\n# 规则\n- **R-001** a\n- **R-002** b\n# 功能需求\n## 子系统\n"
                   "- **FR-001** x，见 R-001\n# 验收场景\n", encoding="utf-8")
    req = parse(doc)
    assert req.rules == ["R-001", "R-002"] and req.frs == ["FR-001"]


def test_secrets():
    text = 'key = "sk-abcdefghijklmnopqrstuvwxyz123456"'
    assert secrets.find(text, [])
    assert "sk-" not in secrets.redact(text, [])
    assert secrets.redact("my token is SECRETVALUE1234", ["SECRETVALUE1234"]) == "my token is [REDACTED]"
    assert not secrets.find('api_key: "{{LDSDT_API_KEY}}"', [])


def test_run_icode_long_kills_tree(monkeypatch):
    """超时后结束整棵进程树并及时返回（子进程继承了输出也不会卡住）；正常结束时拿到输出。"""
    import subprocess
    import sys
    import time
    from ldsdt_kit import common
    monkeypatch.setattr(common, "icode_exe", lambda: sys.executable)
    r = common.run_icode_long(["-c", "print('中文 ok')"], timeout=60)
    assert r.returncode == 0 and "中文 ok" in r.stdout
    child = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)"
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        common.run_icode_long(["-c", child], timeout=2)
    assert time.monotonic() - t0 < 20


def test_collect_icode_recovery_only(tmp_path, monkeypatch):
    """iCode 被直接关掉时只有 session.recovery.json，collect 也要找到这个会话。"""
    import json as _json
    from ldsdt_kit import collect
    home, repo = tmp_path / "chrys", tmp_path / "repo"
    repo.mkdir()
    for sid, name in (("aaa", "session.json"), ("bbb", "session.recovery.json"), ("ccc", "session.json")):
        d = home / "sessions" / sid
        (d / "trajectory").mkdir(parents=True)
        cwd = str(repo) if sid != "ccc" else str(tmp_path / "elsewhere")
        (d / name).write_text(_json.dumps({"meta": {"primary_cwd": cwd, "kind": "chat", "title": sid}}))
        (d / "trajectory" / "events.jsonl").write_text("{}\n")
    (home / "sessions" / "attribution").mkdir()
    monkeypatch.setattr(collect, "chrys_dir", lambda: home)
    found = sorted(s.sid for s in collect.icode_sessions(repo))
    assert found == ["aaa", "bbb"]


def test_ensure_pull_merges(tmp_path):
    import subprocess as sp
    from ldsdt_kit.common import ensure_pull_merges
    sp.run(["git", "init", "-q", str(tmp_path)], check=True)
    ensure_pull_merges(tmp_path)
    got = sp.run(["git", "config", "--local", "--get", "pull.rebase"], cwd=tmp_path, capture_output=True, text=True)
    assert got.stdout.strip() == "false"
    sp.run(["git", "config", "--local", "pull.rebase", "true"], cwd=tmp_path, check=True)
    ensure_pull_merges(tmp_path)  # 不覆盖已有设置
    got = sp.run(["git", "config", "--local", "--get", "pull.rebase"], cwd=tmp_path, capture_output=True, text=True)
    assert got.stdout.strip() == "true"


def test_ensure_api_key(tmp_path, monkeypatch):
    from ldsdt_kit import common

    monkeypatch.setenv(config.API_KEY_ENV_VAR, "already-set-key")
    assert common.ensure_api_key() == "env"

    monkeypatch.delenv(config.API_KEY_ENV_VAR)
    monkeypatch.setattr(common.platform, "system", lambda: "Darwin")
    fake = tmp_path / "fakezsh"
    fake.write_text('#!/bin/sh\necho "noise from rc"\nLDSDT_API_KEY=from-rc-key-1234\nexport LDSDT_API_KEY\nshift 2\nexec /bin/sh -c "$1"\n')
    fake.chmod(0o755)
    assert common.ensure_api_key(shell=str(fake)) == "zsh"
    assert common.os.environ[config.API_KEY_ENV_VAR] == "from-rc-key-1234"

    monkeypatch.delenv(config.API_KEY_ENV_VAR)
    empty = tmp_path / "emptyzsh"
    empty.write_text('#!/bin/sh\nshift 2\nexec /bin/sh -c "$1"\n')
    empty.chmod(0o755)
    assert common.ensure_api_key(shell=str(empty)) == ""
    assert config.API_KEY_ENV_VAR not in common.os.environ
