"""命令入口：uv run ldsdt <命令>。"""

from __future__ import annotations

import argparse

from . import config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ldsdt", description=f"LDSDT 课程工具包 {config.KIT_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="生成 iCode 模型配置 ldsdt-qwen、同步智能体并检查环境")
    s.add_argument("--base-url", help="Qwen OpenAI 兼容接口地址（默认读环境变量 LDSDT_QWEN_BASE_URL）")
    s.add_argument("--replace", action="store_true", help="把同名的已有模型配置改名备份")
    s.add_argument("--offline", action="store_true", help="不检查 Qwen 接口连通性")

    s = sub.add_parser("doctor", help="检查环境")
    s.add_argument("--offline", action="store_true", help="不检查 Qwen 接口连通性")

    sub.add_parser("sync", help="把 agents/ 同步到 iCode 用户目录")

    s = sub.add_parser("grade", help="在本 Lab 的计分需求上运行系统并打分")
    s.add_argument("lab", help="lab0、lab1 …… lab4")
    s.add_argument("--no-run", action="store_true", help="不运行系统，只对 runs/ 中已有产物打分")
    s.add_argument("--task", action="append", help="只评测指定 id 的需求（可重复）")
    s.add_argument("--timeout", type=int, help="单份需求的运行时长上限（秒），默认按子任务规定")
    s.add_argument("-v", "--verbose", action="store_true", help="显示失败场景的原因")

    s = sub.add_parser("try", help="在任意一份需求（如 tasks/practice/ 下的练习需求）上运行系统并检查，不计分")
    s.add_argument("requirement", help="需求文档路径")
    s.add_argument("--lab", type=int, default=4, help="按哪个 Lab 的要求运行和检查（默认 4，即完整系统）")
    s.add_argument("--no-run", action="store_true", help="不运行系统，只检查 runs/try/<id>/ 中已有产物")
    s.add_argument("--timeout", type=int, help="运行时长上限（秒），默认按 --lab 的规定")
    s.add_argument("-v", "--verbose", action="store_true", help="显示失败场景的原因")

    s = sub.add_parser("submit", help="提交运行产物并打标签 lab<N>-submit")
    s.add_argument("lab")
    s.add_argument("--no-push", action="store_true", help="只提交和打标签，不推送")

    s = sub.add_parser("collect", help="打包本周的本地会话记录（研究用）")
    s.add_argument("--week", type=int, required=True)
    s.add_argument("--pseudonym", help="课程分配的研究编号")
    s.add_argument("--yes", action="store_true", help="不询问，打包全部（AiWork 默认项目中的会话除外）")

    args = p.parse_args(argv)
    from . import collect, doctor, grade, setup_cmd, submit, sync

    handler = {"setup": setup_cmd.run, "doctor": doctor.run, "sync": sync.run, "grade": grade.run, "try": grade.try_run,
               "submit": submit.run, "collect": collect.run}[args.command]
    try:
        return handler(args) or 0
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
