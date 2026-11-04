"""启动学生系统（iCode 工作流 ldsdt）处理一份需求，并把运行信息写入 run.json。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import config
from .common import (
    icode_version, now_iso, read_json, run_icode, run_icode_long, session_dir, write_json, platform_label, info,
)
from .reqdoc import Requirement


def workflow_input(req_file: Path, run_dir: Path, lab: int) -> str:
    return json.dumps({"requirement": str(req_file.resolve()), "run_dir": str(run_dir.resolve()), "lab": lab},
                      ensure_ascii=False)


def collect_usage(session_id: str | None, run_id: str | None) -> dict:
    """token 用量与实际调用的模型。只记录、不计分；模型名用于核对是否只用了 Qwen。"""
    usage: dict = {"total_tokens": 0, "tool_calls": 0, "input_tokens": None, "output_tokens": None,
                   "model_calls": None, "models": []}
    if not session_id:
        return usage
    sdir = session_dir(session_id)
    if run_id:
        for p in (sdir / "workflows" / run_id / "nodes").glob("*.usage.*.json"):
            d = read_json(p, {}) or {}
            usage["total_tokens"] += int(d.get("total_usage_tokens") or 0)
            usage["tool_calls"] += int(d.get("tool_call_count") or 0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "turns.json"
        try:
            run_icode(["trajectory", "export", "--session", session_id, "--format", "turns", "--out", str(out)],
                      timeout=120)
        except subprocess.TimeoutExpired:
            return usage
        data = read_json(out, {}) or {}
    level = data.get("sessionLevel") or {}
    u = level.get("usage") or {}
    calls = level.get("modelCalls") or []
    usage.update(input_tokens=u.get("inputTokens"), output_tokens=u.get("outputTokens"),
                 model_calls=len(calls), models=sorted({c.get("requestModel") for c in calls if c.get("requestModel")}))
    return usage


def run_task(root: Path, lab: int, req: Requirement, timeout: int, run_dir: Path | None = None) -> dict:
    """运行目录默认 runs/lab<N>/<id>/，每次运行前清空。try 传入自己的 run_dir，lab 为要模拟的 Lab。"""
    run_dir = run_dir or root / "runs" / f"lab{lab}" / req.id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    input_md = run_dir / "input.md"
    shutil.copyfile(req.path, input_md)

    info(f"  运行 {req.id}（上限 {timeout // 60} 分钟）……")
    started, t0 = now_iso(), time.monotonic()
    try:
        r = run_icode_long(["workflow", "run", config.WORKFLOW_ID, "--trust", "--json", "--quiet",
                       "--timeout", str(timeout), "--input", workflow_input(input_md, run_dir, lab)],
                      timeout=timeout + 300)
        exit_code, stdout, stderr = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        exit_code, stdout, stderr = 124, "", "ldsdt: iCode 未在时限内退出"
    elapsed = round(time.monotonic() - t0, 1)

    result: dict = {}
    for line in reversed(stdout.strip().splitlines()):
        try:
            result = json.loads(line)
            break
        except ValueError:
            continue
    iv = icode_version()
    record = {
        "lab": lab, "task_id": req.id, "started_at": started, "elapsed_seconds": elapsed,
        "timeout_seconds": timeout, "exit_code": exit_code,
        "outcome": result.get("outcome") or ("timeout" if exit_code == 124 else "error"),
        "reason": result.get("reason", ""), "failed_node": result.get("node_id", ""),
        "error": (result.get("error") or stderr.strip()[-2000:]),
        "session_id": result.get("session_id"), "run_id": result.get("run_id"),
        "icode_version": ".".join(map(str, iv)) if iv else None,
        "kit_version": config.KIT_VERSION, "platform": platform_label(),
    }
    record["usage"] = collect_usage(record["session_id"], record["run_id"])
    write_json(run_dir / "run.json", record)
    info(f"    {record['outcome']}，{elapsed} 秒，{record['usage']['total_tokens']} tokens")
    return record
