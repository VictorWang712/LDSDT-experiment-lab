"""LDSDT 课程工具包。学生不得修改本目录（官方复评使用课程组副本）。

学生系统（工作流 ldsdt 及其智能体、脚本）不得导入或调用本工具包：评测运行时，runner 为 iCode 设置环境变量
LDSDT_SYSTEM_RUN=1（见 config.SYSTEM_RUN_ENV），此时导入本包直接失败。
"""

import os as _os

if _os.environ.get("LDSDT_SYSTEM_RUN") == "1":
    raise ImportError(
        "LDSDT：学生系统不得导入或调用评测工具 ldsdt_kit（包括运行 `ldsdt` 命令）。"
        "请在自己的工作流中实现需要的功能。"
    )

from .config import KIT_VERSION as __version__  # noqa: E402,F401
