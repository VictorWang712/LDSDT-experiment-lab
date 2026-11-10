"""课程统一常量。学生不得修改本目录下的任何文件（官方复评使用课程组自己的副本）。"""

from __future__ import annotations

import hashlib

KIT_VERSION = "0.3.3"
MIN_ICODE_VERSION = (0, 35, 2)
# 课程统一使用浙大课程特供版 iCode（命令名 icode-zju，版本号带 +zju 后缀）。
ICODE_COMMAND = "icode-zju"
ICODE_INSTALL = "uv tool install --python 3.14 --index-url https://1.92.199.78/pypi/simple icode-zju"
PYTHON_MAJOR_MINOR = (3, 12)

# ---- 系统内部模型：Qwen3.8-27B（浙大课程网关）----
# 每位学生一个课程网关 Key，同一个 Key 也用于 B 的辅助开发模型 DS-4.1-flash。
API_KEY_ENV_VAR = "LDSDT_API_KEY"
QWEN_MODEL_ID = "qwen3.8-27b"
# 课程网关（OpenAI 兼容）。所有 Key 都走同一个地址，且每个请求都必须带下面两个请求头，否则返回 HTTP 403。
GATEWAY_BASE_URL = "https://1.92.199.78/v1"
GATEWAY_HEADERS = {"X-iCode-Client": "icode", "X-iCode-Tenant": "zju"}
QWEN_MAX_CONTEXT_TOKENS = 1_000_000
# 单次回复的输出上限与思考预算。实测（2026-11-03）不加限制时 Qwen 在大需求上一次回复可思考 10 分钟以上，
# 连接中断后整轮重来，30 分钟内一次工具调用都没有；统一限制后各组条件相同。
QWEN_MAX_OUTPUT_TOKENS = 32_000
QWEN_CHAT_OPTIONS = {"extra_body": {"thinking_budget": 4096}}
MODEL_PROFILE_NAME = "ldsdt-qwen"

# ---- 学生系统 ----
WORKFLOW_ID = "ldsdt"
AGENT_PREFIX = "ldsdt-"

# 子任务：Lab 0 环境与热身工作流；Lab 1–4 依次为需求分析、设计、实现、测试模块。
LABS = (0, 1, 2, 3, 4)
# 每个 Lab 单次运行（单份需求）的时长上限，秒。超时不判 0，按已有产物评分。
LAB_TIMEOUTS = {0: 10 * 60, 1: 15 * 60, 2: 25 * 60, 3: 45 * 60, 4: 90 * 60}
TRY_TIMEOUT = 90 * 60
# Lab 0 的计分需求（tasks/practice/ 下）；Lab 1–4 的计分需求是 tasks/public/ 下的全部需求。
LAB0_TASKS = ("todo-cli", "wordstat")
# 各 Lab 在 design-choices.yaml 中要填写的维度
DESIGN_DIMENSIONS = {
    1: ["D1.1", "D1.2", "D1.3", "D1.4", "D1.5"],
    2: ["D2.1", "D2.2", "D2.3", "D2.4", "D2.5", "D2.6"],
    3: ["D3.1", "D3.2", "D3.3", "D3.4", "D3.5"],
    4: ["D4.1", "D4.2", "D4.3", "D4.4", "D4.5"],
}
# 课程组的参考实现与变异体所在目录（只在助教机器上设置）
REFERENCE_ENV_VAR = "LDSDT_REFERENCE_DIR"

# 目标仓库验收
INSTALL_TIMEOUT = 300
STEP_TIMEOUT = 30


def stable_id(kind: str, name: str) -> str:
    """iCode 配置用的固定 12 位十六进制 ID。iCode 按 ID 绑定模型，且带 ID 的文件不会被改写。"""
    return hashlib.sha256(f"ldsdt:{kind}:{name}".encode()).hexdigest()[:12]


MODEL_PROFILE_ID = stable_id("model", MODEL_PROFILE_NAME)
