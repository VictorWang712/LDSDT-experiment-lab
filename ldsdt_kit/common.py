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
    from . import config
    return shutil.which(config.ICODE_COMMAND)


def icode_version_text() -> str | None:
    """`icode-zju --version` 的原样输出，例如 0.35.2+zju.6；找不到命令时为 None。"""
    exe = icode_exe()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"\d+\.\d+\.\d+\S*", out)
    return m.group(0) if m else None


def icode_version() -> tuple[int, ...] | None:
    text = icode_version_text()
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def run_icode(args: list[str], timeout: float | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    exe = icode_exe()
    if not exe:
        from . import config
        die(f"找不到 {config.ICODE_COMMAND} 命令。请先按 Lab 0 安装课程特供版 iCode：{config.ICODE_INSTALL}")
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    """结束进程及其全部子进程（iCode 会为 Python 节点、Shell 工具再起子进程）。"""
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=60)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
        proc.wait(timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_icode_long(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """长时间运行（workflow run）。输出写临时文件而不是管道，超时或 Ctrl-C 时结束整棵进程树：
    用管道时，Windows 上 subprocess 在超时后会一直等子孙进程关闭管道，可能卡住。超时抛出 TimeoutExpired。"""
    import tempfile
    exe = icode_exe()
    if not exe:
        from . import config
        die(f"找不到 {config.ICODE_COMMAND} 命令。请先按 Lab 0 安装课程特供版 iCode：{config.ICODE_INSTALL}")
    extra = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WINDOWS else {"start_new_session": True})
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([exe, *args], stdout=out, stderr=err, stdin=subprocess.DEVNULL, **extra)
        try:
            code = proc.wait(timeout=timeout)
        except BaseException:          # 超时或 KeyboardInterrupt：不留下孤儿进程
            _kill_tree(proc)
            raise
        out.seek(0)
        err.seek(0)
        dec = lambda f: f.read().decode("utf-8", errors="replace")
        return subprocess.CompletedProcess([exe, *args], code, dec(out), dec(err))


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
