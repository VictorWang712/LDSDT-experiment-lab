import argparse
import datetime as dt
import json
import sys
from pathlib import Path

DATA = Path("todo.json")


def load():
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"next_id": 1, "tasks": []}


def save(d):
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def valid_date(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date().isoformat() == s
    except ValueError:
        return False


def main():
    p = argparse.ArgumentParser(prog="todo", description="待办事项命令行工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("title"); a.add_argument("--due")
    l = sub.add_parser("list"); l.add_argument("--pending", action="store_true")
    for name in ("done", "remove"):
        sub.add_parser(name).add_argument("id", type=int)
    args = p.parse_args()
    d = load()
    if args.cmd == "add":
        if args.due is not None and not valid_date(args.due):
            fail(f"invalid date: {args.due}")
        tid = d["next_id"]
        d["tasks"].append({"id": tid, "title": args.title, "due": args.due, "done": False})
        d["next_id"] += 1
        save(d)
        print(f"Added #{tid}")
    elif args.cmd == "list":
        tasks = [t for t in d["tasks"] if not (args.pending and t["done"])]
        if not tasks:
            print("No tasks")
        for t in sorted(tasks, key=lambda t: t["id"]):
            due = f" (due {t['due']})" if t["due"] else ""
            print(f"#{t['id']} [{'x' if t['done'] else ' '}] {t['title']}{due}")
    else:
        t = next((t for t in d["tasks"] if t["id"] == args.id), None)
        if t is None:
            fail(f"no such task: #{args.id}")
        if args.cmd == "done":
            t["done"] = True
            print(f"Completed #{args.id}")
        else:
            d["tasks"].remove(t)
            print(f"Removed #{args.id}")
        save(d)


if __name__ == "__main__":
    main()
