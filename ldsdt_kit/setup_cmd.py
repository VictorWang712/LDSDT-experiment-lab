"""ldsdt setup：生成 iCode 模型配置 ldsdt-qwen，同步智能体，然后运行 doctor。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from . import config
from .common import chrys_dir, info, ok, warn, die


def models_dir() -> Path:
    return chrys_dir() / "models"


def load_model_profiles() -> list[tuple[Path, dict]]:
    out = []
    d = models_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict):
            out.append((p, data))
    return out


def expected_profile() -> dict:
    return {
        "id": config.MODEL_PROFILE_ID,
        "name": config.MODEL_PROFILE_NAME,
        "model_id": config.QWEN_MODEL_ID,
        "max_context_tokens": config.QWEN_MAX_CONTEXT_TOKENS,
        "max_output_tokens": config.QWEN_MAX_OUTPUT_TOKENS,
        "base_url": config.GATEWAY_BASE_URL,
        "http_headers": json.dumps(config.GATEWAY_HEADERS),
        "chat_options": json.dumps(config.QWEN_CHAT_OPTIONS),
        # 只写占位符，密钥本身从环境变量读取，不落盘。
        "api_key": "{{%s}}" % config.API_KEY_ENV_VAR,
    }


def write_model_profile(replace: bool) -> None:
    d = models_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{config.MODEL_PROFILE_ID}.yaml"
    for path, data in load_model_profiles():
        same_name = str(data.get("name", "")).strip().lower() == config.MODEL_PROFILE_NAME
        if same_name and path.resolve() != target.resolve():
            if not replace:
                die(
                    f"已有另一份名为 {config.MODEL_PROFILE_NAME} 的模型配置：{path}\n"
                    "iCode 不允许重名。请在 iCode 中删除它，或运行 `uv run ldsdt setup --replace`"
                    "（会把它改名为 .ldsdt-backup 备份）。"
                )
            backup = path.with_name(path.name + ".ldsdt-backup")
            path.rename(backup)
            warn(f"已把同名模型配置备份为 {backup}")
    text = "# 由 ldsdt setup 生成，请勿手工修改；重新运行 setup 会覆盖。\n"
    text += yaml.safe_dump(expected_profile(), allow_unicode=True, sort_keys=False)
    target.write_text(text, encoding="utf-8")
    ok(f"已写入模型配置 {config.MODEL_PROFILE_NAME}（{target}）")


def run(args) -> int:
    from . import doctor, sync

    info("== 1/3 模型配置")
    write_model_profile(args.replace)
    if not os.environ.get(config.API_KEY_ENV_VAR):
        warn(f"环境变量 {config.API_KEY_ENV_VAR} 还没有设置。按 Lab 0 设置后重新打开终端，再运行 `uv run ldsdt doctor`。")
    info("\n== 2/3 同步智能体")
    sync.sync_agents(verbose=True)
    info("\n== 3/3 环境检查")
    return doctor.run(args)
