"""ldsdt collect --week N：打包本机与本仓库相关的 iCode / AiWork 原始会话记录（脱敏后），供研究使用。

只拷贝原始文件，不经模型整理。打包结果在 .ldsdt/collect/，不提交到 Git。是否参与研究由本人决定，不影响成绩。
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, secrets
from .common import (
    agentix_dir, append_jsonl, chrys_dir, die, info, is_within, ldsdt_dir, now_iso, ok, read_json, repo_root, warn,
    write_json,
)

AIWORK_AGENTS = ("coder", "coder-tui", "worker")
AIWORK_DEFAULT_PROJECT = Path.home() / ".dtcoder-external" / "default_project"
SHA_RE = re.compile(r"\b[0-9a-f]{64}\b")


@dataclass
class Session:
    tool: str               # icode / aiwork
    sid: str
    title: str
    updated: str
    cwd: str
    files: list[tuple[Path, str]] = field(default_factory=list)  # (源文件, 包内路径)
    needs_confirm: bool = False


# ------------------------------------------------------------------ iCode

def icode_sessions(root: Path) -> list[Session]:
    out = []
    base = chrys_dir() / "sessions"
    for sj in sorted(base.glob("*/session.json")):
        meta = (read_json(sj, {}) or {}).get("meta") or {}
        dirs = [meta.get("primary_cwd") or ""] + list(meta.get("working_dirs") or [])
        if not any(d and is_within(d, root) for d in dirs):
            continue
        sdir = sj.parent
        files = []
        for p in sorted(sdir.rglob("*")):
            rel = p.relative_to(sdir)
            if p.is_file() and rel.parts[0] != "snapshots" and not p.name.endswith((".lock", ".bak")):
                files.append((p, f"icode/{sdir.name}/{rel.as_posix()}"))
        out.append(Session("icode", sdir.name, f"[{meta.get('kind', '?')}] {meta.get('title', '')}",
                           str(meta.get("updated_at", "")), dirs[0], files))
    return out


# ------------------------------------------------------------------ AiWork

def _aiwork_first_user_message(events: list[dict], objects: Path) -> str:
    for e in events:
        if e.get("type") != "transcript.batch_imported":
            continue
        ref = ((e.get("data") or {}).get("entries_ref") or {}).get("sha256")
        for entry in read_json(objects / str(ref), []) or []:
            if entry.get("type") == "message" and entry.get("role") == "user":
                return str(entry.get("content", ""))[:40].replace("\n", " ")
    return ""


def aiwork_sessions(root: Path) -> list[Session]:
    out = []
    for agent in AIWORK_AGENTS:
        v2 = agentix_dir() / "agents" / agent / "sessions" / "v2"
        objects = v2 / "objects"
        for journal in sorted((v2 / "journals").glob("*.jsonl")):
            text = journal.read_text(encoding="utf-8", errors="replace")
            events, cwds, last_ms = [], [], 0
            for line in text.splitlines():
                try:
                    body = json.loads(line)["body"]
                except (ValueError, KeyError, TypeError):
                    continue
                last_ms = max(last_ms, int(body.get("committed_at_ms") or 0))
                for e in body.get("events", []):
                    events.append(e)
                    d = e.get("data") or {}
                    if e.get("type") == "domain.replaced" and d.get("domain") == "profile":
                        cwd = (d.get("after") or {}).get("cwd")
                        if cwd and cwd not in cwds:
                            cwds.append(cwd)
            in_repo = any(is_within(c, root) for c in cwds)
            in_default = any(is_within(c, AIWORK_DEFAULT_PROJECT) for c in cwds)
            if not (in_repo or in_default):
                continue
            files = [(journal, f"aiwork/{agent}/journals/{journal.name}")]
            head = journal.with_name(journal.name + ".head.json")
            if head.is_file():
                files.append((head, f"aiwork/{agent}/journals/{head.name}"))
            # 内容寻址对象可能再引用其他对象，按引用闭包收集
            pending, seen = set(SHA_RE.findall(text)), set()
            while pending:
                h = pending.pop()
                seen.add(h)
                obj = objects / h
                if obj.is_file():
                    files.append((obj, f"aiwork/{agent}/objects/{h}"))
                    pending |= set(SHA_RE.findall(obj.read_text(encoding="utf-8", errors="replace"))) - seen
            updated = datetime.fromtimestamp(last_ms / 1000, timezone.utc).astimezone().isoformat(timespec="seconds") if last_ms else ""
            out.append(Session("aiwork", f"{agent}:{journal.stem}", _aiwork_first_user_message(events, objects),
                               updated, cwds[-1] if cwds else "", files, needs_confirm=not in_repo))
    return out


# ------------------------------------------------------------------ 打包

def pseudonym(root: Path, given: str | None) -> str:
    local = ldsdt_dir(root) / "local.json"
    data = read_json(local, {}) or {}
    value = given or data.get("pseudonym")
    if not value:
        value = input("请输入课程分配给你的研究编号（例如 G07-A）：").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", value or ""):
        die("研究编号只能包含字母、数字、下划线和连字符。")
    write_json(local, {**data, "pseudonym": value})
    return value


def choose(sessions: list[Session], assume_yes: bool) -> tuple[list[Session], list[str]]:
    info("将要打包的会话：")
    for i, s in enumerate(sessions, 1):
        flag = "（AiWork 默认项目，需确认）" if s.needs_confirm else ""
        info(f"  {i:>3}. {s.tool:<6} {s.updated[:16]:<16} {s.title[:40]}{flag}")
    if assume_yes:
        return [s for s in sessions if not s.needs_confirm], [s.sid for s in sessions if s.needs_confirm]
    info("\n标为「需确认」的会话来自 AiWork 的默认项目目录，只有与本课程有关时才应打包。")
    raw = input("输入要排除的编号（空格分隔），直接回车表示全部打包：").strip()
    drop = {int(x) for x in raw.split() if x.isdigit()}
    keep = [s for i, s in enumerate(sessions, 1) if i not in drop]
    return keep, [s.sid for i, s in enumerate(sessions, 1) if i in drop]


def run(args) -> int:
    root = repo_root()
    name = pseudonym(root, args.pseudonym)
    sessions = icode_sessions(root) + aiwork_sessions(root)
    if not sessions:
        warn("没有找到工作目录在本仓库中的 iCode 或 AiWork 会话。AiWork 请在「编码 → 项目」中打开本仓库后再工作。")
        return 0
    keep, excluded = choose(sessions, args.yes)

    values = secrets.known_values()
    out_dir = ldsdt_dir(root) / "collect"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"week-{args.week}-{name}.zip"
    manifest = {
        "week": args.week, "pseudonym": name, "time": now_iso(), "kit_version": config.KIT_VERSION,
        "sessions": [{"tool": s.tool, "id": s.sid, "updated": s.updated, "files": len(s.files)} for s in keep],
        "excluded": excluded,
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for s in keep:
            for src, arc in s.files:
                data = src.read_bytes()
                try:
                    data = secrets.redact(data.decode("utf-8"), values).encode("utf-8")
                except UnicodeDecodeError:
                    continue  # 本工具只收集文本记录
                z.writestr(arc, data)
        for extra in ("grade-history.jsonl", "submissions.jsonl"):
            p = ldsdt_dir(root) / extra
            if p.is_file():
                z.writestr(f"ldsdt/{extra}", p.read_bytes())
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    # 随仓库提交的收集记录只有数量，不含研究编号与内容；Lab 0 用它确认 collect 已经跑通。
    append_jsonl(ldsdt_dir(root) / "collect-log.jsonl",
                 {"week": args.week, "time": now_iso(), "excluded": len(excluded),
                  "sessions": {tool: sum(s.tool == tool for s in keep) for tool in ("icode", "aiwork")}})
    ok(f"已打包 {len(keep)} 个会话（排除 {len(excluded)} 个）：{zip_path}")
    info("请按课程网站「C 角色指南 / 数据提交」页的说明上传该文件。不要把它提交到 Git 仓库。")
    return 0
