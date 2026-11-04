"""密钥识别：提交前检查与数据收集时脱敏共用。"""

from __future__ import annotations

import os
import re

from . import config
from .common import agentix_dir

PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|secret)([\"']?\s*[:=]\s*[\"']?)([A-Za-z0-9._\-]{16,})"),
]


def known_values() -> list[str]:
    """本机上已知的密钥值：环境变量、iCode 模型配置中的明文密钥、AiWork .env 中的密钥。"""
    vals = set()
    for name, v in os.environ.items():
        if (name == config.QWEN_ENV_VAR or re.search(r"(KEY|TOKEN|SECRET)$", name)) and len(v) >= 12:
            vals.add(v)
    try:
        from .setup_cmd import load_model_profiles
        for _, d in load_model_profiles():
            k = str(d.get("api_key") or "")
            if len(k) >= 12 and not k.startswith("{{"):
                vals.add(k)
    except Exception:
        pass
    env_file = agentix_dir() / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                v = v.strip().strip("'\"")
                if re.search(r"(KEY|TOKEN|SECRET)", k) and len(v) >= 12:
                    vals.add(v)
    return sorted(vals, key=len, reverse=True)


def find(text: str, values: list[str]) -> list[str]:
    hits = [f"已知密钥（…{v[-4:]}）" for v in values if v in text]
    for p in PATTERNS:
        for m in p.finditer(text):
            hits.append(f"疑似密钥 {m.group(0)[:12]}…")
    return hits


def redact(text: str, values: list[str]) -> str:
    for v in values:
        text = text.replace(v, "[REDACTED]")
    text = PATTERNS[0].sub("[REDACTED]", text)
    text = PATTERNS[1].sub("Bearer [REDACTED]", text)
    return PATTERNS[2].sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
