"""ldsdt doctor：检查 Python、uv、iCode、密钥、模型配置、Qwen 接口、智能体同步与工作流。"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import common, config, sync
from .common import (
    ensure_pull_merges, info, ok, bad, warn, icode_version, icode_version_text, ldsdt_dir, now_iso, repo_root, run_icode,
    write_json, git,
)
from .setup_cmd import expected_profile, load_model_profiles


BUSY_HINT = ("本项不扣分。请过几分钟运行 `uv run ldsdt doctor` 重新检查；"
             "如果一直如此，请在课程群里反馈，不要反复连续重试。")


def _ping_once(key: str, timeout: float) -> tuple[str, str]:
    """返回 (状态, 说明)。状态：ok 通过；busy 网关繁忙（超时、限流、5xx），不算失败；fail 失败。"""
    body = json.dumps({
        "model": config.QWEN_MODEL_ID,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode()
    req = urllib.request.Request(
        config.GATEWAY_BASE_URL + "/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **config.GATEWAY_HEADERS},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return "ok", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            return "busy", f"HTTP {e.code}"
        hint = {401: "密钥无效", 403: "无权限或缺少请求头", 404: "地址或模型 ID 错误"}.get(e.code, "")
        return "fail", f"HTTP {e.code} {hint}".strip()
    except (TimeoutError, socket.timeout):
        return "busy", f"{timeout:.0f} 秒内没有响应"
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            return "busy", f"{timeout:.0f} 秒内没有响应"
        return "fail", f"无法连接：{e.reason}"
    except OSError as e:
        return "fail", f"无法连接：{e}"


def _ping_qwen(key: str, timeout: float = 45, retry_wait: float = 5) -> tuple[str, str]:
    """网关繁忙时自动重试一次；两次都繁忙则返回 busy，由调用方给出提示但不算失败。"""
    status, detail = _ping_once(key, timeout)
    if status != "busy":
        return status, detail
    time.sleep(retry_wait)
    status2, detail2 = _ping_once(key, timeout)
    if status2 != "busy":
        return status2, detail2 + "（第 2 次尝试）"
    return "busy", f"网关繁忙：两次请求均未成功（{detail}；{detail2}）。{BUSY_HINT}"


def _norm(v) -> str:
    """比较配置字段：地址去掉末尾斜杠，JSON 字符串按内容比较。"""
    s = str(v if v is not None else "").strip().rstrip("/")
    if s.startswith("{"):
        try:
            return json.dumps(json.loads(s), sort_keys=True)
        except ValueError:
            pass
    return s


def checks(root: Path, offline: bool = False) -> list[dict]:
    results: list[dict] = []

    def add(name: str, passed: bool, detail: str = "", warning: bool = False) -> None:
        results.append({"name": name, "ok": passed, "detail": detail, **({"warning": True} if warning else {})})
        (warn if warning else ok if passed else bad)(f"{name}{'：' + detail if detail else ''}")

    v = sys.version_info
    add("Python 3.12", (v.major, v.minor) == config.PYTHON_MAJOR_MINOR, f"当前 {v.major}.{v.minor}.{v.micro}")
    add("uv", shutil.which("uv") is not None, "" if shutil.which("uv") else "找不到 uv 命令")

    is_repo = git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    remote = git(root, "remote", "get-url", "origin").stdout.strip() if is_repo else ""
    add("Git 仓库与 origin", is_repo and bool(remote), remote or "不是 git 仓库或没有 origin 远程")

    iv, ivt = icode_version(), icode_version_text()
    if iv is None:
        add("iCode（课程特供版）", False, f"找不到 {config.ICODE_COMMAND} 命令（{config.ICODE_INSTALL}）")
    else:
        need = ".".join(map(str, config.MIN_ICODE_VERSION))
        good = iv >= config.MIN_ICODE_VERSION and "+zju" in (ivt or "")
        add("iCode（课程特供版）", good, f"{ivt}（至少 {need}+zju）")

    key = os.environ.get(config.API_KEY_ENV_VAR, "")
    source = {"zsh": "（从 ~/.zshrc 读取）", "registry": "（从 Windows 用户环境变量读取）"}.get(common.API_KEY_SOURCE, "")
    note = "已设置" + source if key else "未设置"
    add(f"环境变量 {config.API_KEY_ENV_VAR}", bool(key), note)

    profiles = {str(d.get("id")): (p, d) for p, d in load_model_profiles()}
    found = profiles.get(config.MODEL_PROFILE_ID)
    if not found:
        add("模型配置 ldsdt-qwen", False, "不存在，请运行 `uv run ldsdt setup`")
    else:
        exp = expected_profile()
        diff = [k for k in ("name", "model_id", "api_key", "base_url", "http_headers", "max_output_tokens", "chat_options")
                if _norm(found[1].get(k)) != _norm(exp[k])]
        add("模型配置 ldsdt-qwen", not diff,
            f"字段不一致：{', '.join(diff)}，请重新运行 `uv run ldsdt setup`" if diff else "已配置")

    if offline:
        add("Qwen 接口", True, "已跳过（--offline）")
    elif not key:
        add("Qwen 接口", False, "缺少密钥，无法检查")
    else:
        status, detail = _ping_qwen(key)
        add("Qwen 接口", status != "fail", detail, warning=status == "busy")

    used = common.find_kit_usage(root)
    add("系统不调用评测工具", not used,
        f"以下文件引用了 ldsdt_kit：{', '.join(used[:5])}{' 等' if len(used) > 5 else ''}。"
        "学生系统不得导入或调用评测工具，评测运行时会直接失败，评测分为 0" if used else "")

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
    ensure_pull_merges(root)
    results = checks(root, offline=getattr(args, "offline", False))
    passed = all(r["ok"] for r in results)
    write_json(ldsdt_dir(root) / "doctor.json", {"time": now_iso(), "passed": passed, "checks": results})
    warned = [r["name"] for r in results if r.get("warning")]
    if passed and warned:
        info(f"\n全部通过，但「{'、'.join(warned)}」有提示，请按上面的说明稍后重新检查。")
        return 0
    info("\n全部通过。" if passed else "\n有检查未通过，请按提示修复后重新运行 `uv run ldsdt doctor`。")
    return 0 if passed else 1
