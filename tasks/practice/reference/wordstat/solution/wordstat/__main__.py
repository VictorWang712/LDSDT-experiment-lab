import argparse
import re
import sys
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[^\W_]+")


def read(name):
    p = Path(name)
    if not p.is_file():
        print(f"error: {name}: not found", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def stats(text):
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return lines, len(WORD.findall(text)), len(text)


def main():
    p = argparse.ArgumentParser(prog="wordstat", description="文本统计")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count"); c.add_argument("files", nargs="+")
    t = sub.add_parser("top"); t.add_argument("file"); t.add_argument("-k", type=int, default=5)
    t.add_argument("--min-length", type=int, default=0)
    args = p.parse_args()
    if args.cmd == "count":
        texts = [read(f) for f in args.files]
        if len(texts) == 1:
            l, w, ch = stats(texts[0])
            print(f"lines: {l}\nwords: {w}\nchars: {ch}")
        else:
            tot = [0, 0, 0]
            for f, text in zip(args.files, texts):
                s = stats(text)
                tot = [a + b for a, b in zip(tot, s)]
                print("\t".join([f, *map(str, s)]))
            print("\t".join(["total", *map(str, tot)]))
    else:
        words = [w.lower() for w in WORD.findall(read(args.file)) if len(w) >= args.min_length]
        for w, n in sorted(Counter(words).items(), key=lambda x: (-x[1], x[0]))[: args.k]:
            print(f"{w} {n}")


if __name__ == "__main__":
    main()
