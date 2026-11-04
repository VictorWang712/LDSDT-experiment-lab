"""ldsdt doctor：检查 Python、uv、iCode、密钥、模型配置、Qwen 接口、智能体同步与工作流。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import config, sync
from .common import (
    info, ok, bad, icode_version, ldsdt_dir, now_iso, repo_root, run_icode, write_json, git,
)
from .setup_cmd import expected_profile, load_model_profiles, resolve_base_url


def _ping_qwen(base_url: str, key: str) -> tuple[bool, str]:
    body = json.dumps({
        "model": config.QWEN_MODEL_ID,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        hint = {401: "密钥无效", 403: "无权限", 404: "地址或模型 ID 错误", 429: "被限流"}.get(e.code, "")
        return False, f"HTTP {e.code} {hint}".strip()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, f"无法连接：{e}"


def checks(root: Path, offline: bool = False) -> list[dict]:
    results: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        results.append({"name": name, "ok": passed, "detail": detail})
        (ok if passed else bad)(f"{name}{'：' + detail if detail else ''}")

    v = sys.version_info
    add("Python 3.12", (v.major, v.minor) == config.PYTHON_MAJOR_MINOR, f"当前 {v.major}.{v.minor}.{v.micro}")
    add("uv", shutil.which("uv") is not None, "" if shutil.which("uv") else "找不到 uv 命令")

    is_repo = git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    remote = git(root, "remote", "get-url", "origin").stdout.strip() if is_repo else ""
    add("Git 仓库与 origin", is_repo and bool(remote), remote or "不是 git 仓库或没有 origin 远程")

    iv = icode_version()
    if iv is None:
        add("iCode", False, "找不到 icode 命令（uv tool install iCode-TUI）")
    else:
        need = ".".join(map(str, config.MIN_ICODE_VERSION))
        add("iCode", iv >= config.MIN_ICODE_VERSION, f"{'.'.join(map(str, iv))}（至少 {need}）")

    key = os.environ.get(config.QWEN_ENV_VAR, "")
    add(f"环境变量 {config.QWEN_ENV_VAR}", bool(key), "已设置" if key else "未设置")

    profiles = {str(d.get("id")): (p, d) for p, d in load_model_profiles()}
    found = profiles.get(config.MODEL_PROFILE_ID)
    env_url = resolve_base_url(None)
    base_url = ""
    if not found:
        add("模型配置 ldsdt-qwen", False, "不存在，请运行 `uv run ldsdt setup`")
    else:
        base_url = str(found[1].get("base_url") or "").rstrip("/")
        exp = expected_profile(base_url)
        diff = [k for k in ("name", "model_id", "api_key", "max_output_tokens", "chat_options")
                if str(found[1].get(k)) != str(exp[k])]
        if not base_url:
            diff.append("base_url")
        elif env_url and env_url != base_url:
            diff.append(f"base_url（与 {config.QWEN_BASE_URL_ENV_VAR} 不同）")
        add("模型配置 ldsdt-qwen", not diff,
            f"字段不一致：{', '.join(diff)}，请重新运行 `uv run ldsdt setup`" if diff else "已配置")  # 不输出地址：doctor.json 随仓库提交

    if offline:
        add("Qwen 接口", True, "已跳过（--offline）")
    elif not key or not base_url:
        add("Qwen 接口", False, "缺少密钥或地址，无法检查")
    else:
        reachable, detail = _ping_qwen(base_url, key)
        add("Qwen 接口", reachable, detail)

    synced, problems = sync.status(root)
    add("智能体同步", synced, "；".join(problems) if problems else "")

    wf = root / ".chrys" / "workflows" / config.WORKFLOW_ID / f"{config.WORKFLOW_ID}.py"
    if not wf.is_file():
        add("工作流 ldsdt", False, f"找不到 {wf.relative_to(root)}")
    elif iv is None:
        add("工作流 ldsdt", False, "需要先安装 iCode")
    else:
        r = run_icode(["workflow", "validate", str(wf)], timeout=180)
        first = (r.stdout or r.stderr).strip().splitlines()[:1]
        add("工作流 ldsdt", r.returncode == 0, first[0] if first else f"退出码 {r.returncode}")

    return results


def run(args) -> int:
    root = repo_root()
    results = checks(root, offline=getattr(args, "offline", False))
    passed = all(r["ok"] for r in results)
    write_json(ldsdt_dir(root) / "doctor.json", {"time": now_iso(), "passed": passed, "checks": results})
    info("\n全部通过。" if passed else "\n有检查未通过，请按提示修复后重新运行 `uv run ldsdt doctor`。")
    return 0 if passed else 1
