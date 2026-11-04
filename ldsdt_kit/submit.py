"""ldsdt submit lab<N>：检查门槛与密钥，提交运行产物，打标签 lab<N>-submit 并推送。"""

from __future__ import annotations

from pathlib import Path

from . import config, secrets
from .common import (
    append_jsonl, bad, die, git, info, kit_hash, ldsdt_dir, now_iso, ok, read_json, repo_root, warn,
)
from .grade import parse_lab

MAX_SCAN_BYTES = 5 * 1024 * 1024


def scan_staged(root: Path) -> list[str]:
    values = secrets.known_values()
    problems = []
    names = git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0")
    for name in filter(None, names):
        p = root / name
        if not p.is_file() or p.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = p.read_bytes().decode("utf-8", errors="ignore")
        for hit in secrets.find(text, values):
            problems.append(f"{name}：{hit}")
    return problems


def run(args) -> int:
    root = repo_root()
    lab = parse_lab(args.lab)
    tag = f"lab{lab}-submit"

    grade = read_json(root / "runs" / f"lab{lab}" / "grade.json")
    if not grade or grade.get("lab") != lab:
        die(f"还没有 lab{lab} 的评测结果，请先运行 `uv run ldsdt grade lab{lab}`。")
    if not grade.get("gate_passed"):
        die(f"lab{lab} 门槛未通过（工作流必须能加载，并在每份计分需求上都运行过），不能提交。")
    ok(f"门槛已通过，评测分 {grade['total']}")
    if grade.get("no_run"):
        warn("最近一次评测使用了 --no-run，只对已有产物打分。")
    if grade.get("kit_hash") != kit_hash(root):
        warn("ldsdt_kit/ 与评测时不一致。官方复评使用课程组副本，修改评测代码不影响成绩。")

    if git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        die("当前目录不是 git 仓库。")
    if not args.no_push and not git(root, "remote", "get-url", "origin").stdout.strip():
        die("没有 origin 远程仓库，无法推送。")

    append_jsonl(ldsdt_dir(root) / "submissions.jsonl", {
        "lab": lab, "time": now_iso(), "local_total": grade.get("total"),
        "kit_version": config.KIT_VERSION, "kit_hash": kit_hash(root),
    })
    git(root, "add", "-A")
    problems = scan_staged(root)
    if problems:
        git(root, "reset", "-q")
        bad("发现疑似密钥，已取消暂存，未提交：")
        for p in problems:
            info(f"    {p}")
        info("请删除这些文件里的密钥（密钥只能放在环境变量中）后重试。")
        return 1
    ok("未发现密钥")

    if git(root, "diff", "--cached", "--quiet").returncode != 0:
        r = git(root, "commit", "-q", "-m", f"ldsdt submit lab{lab}")
        if r.returncode != 0:
            die(f"git commit 失败：{r.stderr.strip()}")
    head = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    git(root, "tag", "-f", tag)
    ok(f"已提交 {head} 并打标签 {tag}")

    if args.no_push:
        warn("已按 --no-push 跳过推送。")
        return 0
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    for cmd in (["push", "-u", "origin", branch], ["push", "-f", "origin", f"refs/tags/{tag}"]):
        r = git(root, *cmd)
        if r.returncode != 0:
            die(f"git {' '.join(cmd)} 失败：{r.stderr.strip()}")
    ok(f"已推送到 origin（分支 {branch}，标签 {tag}）。截止前可重复提交，以最后一次标签为准。")
    return 0
