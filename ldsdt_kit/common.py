"""路径、iCode 调用与输出等公共工具。"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

IS_WINDOWS = platform.system().lower() == "windows"


# ---------------------------------------------------------------- 路径

def repo_root() -> Path:
    """向上查找含 ldsdt_kit/ 与 pyproject.toml 的目录。"""
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "ldsdt_kit").is_dir() and (d / "pyproject.toml").is_file():
            return d
    die("请在实验仓库根目录（或其子目录）中运行本命令。")


def chrys_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "chrys"
    return Path.home() / ".chrys"


def agentix_dir() -> Path:
    return Path.home() / ".agentix"


def ldsdt_dir(root: Path) -> Path:
    d = root / ".ldsdt"
    d.mkdir(exist_ok=True)
    return d


def is_within(path: str | Path, root: Path) -> bool:
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    r = root.resolve()
    if IS_WINDOWS:
        return str(p).lower() == str(r).lower() or str(p).lower().startswith(str(r).lower() + os.sep)
    return p == r or r in p.parents


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


# ---------------------------------------------------------------- iCode

def icode_exe() -> str | None:
    return shutil.which("icode")


def icode_version() -> tuple[int, ...] | None:
    exe = icode_exe()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else None


def run_icode(args: list[str], timeout: float | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    exe = icode_exe()
    if not exe:
        die("找不到 icode 命令。请先按 Lab 0 安装 iCode：uv tool install iCode-TUI")
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )


def session_dir(session_id: str) -> Path:
    """iCode 会话目录名是会话 UUID 去掉连字符后的前 12 位。"""
    return chrys_dir() / "sessions" / session_id.replace("-", "")[:12]


# ---------------------------------------------------------------- 杂项

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def kit_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((root / "ldsdt_kit").rglob("*.py")):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def git_state(root: Path) -> dict:
    head = git(root, "rev-parse", "HEAD").stdout.strip() or None
    dirty = bool(git(root, "status", "--porcelain").stdout.strip())
    return {"commit": head, "dirty": dirty}


def platform_label() -> str:
    return f"{platform.system()}-{platform.machine()}"


# ---------------------------------------------------------------- 输出

def _enable_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK
        except (AttributeError, ValueError):
            pass


_enable_utf8_console()


def info(msg: str = "") -> None:
    print(msg, flush=True)


def ok(msg: str) -> None:
    print(f"  [通过] {msg}", flush=True)


def bad(msg: str) -> None:
    print(f"  [失败] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  [注意] {msg}", flush=True)


def die(msg: str, code: int = 1):
    print(f"错误：{msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)
