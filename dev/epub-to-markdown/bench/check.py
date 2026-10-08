#!/usr/bin/env python3
"""Invariant checks for epub2md output. Exit 1 on any failure.

Usage: check.py OUT.md [...]

1. every toc entry [line, level, title] points at exactly that heading line
2. the front matter `lines:` equals the real line count
3. every internal link (#slug) resolves to a heading in the file
4. no raw HTML outside code fences
"""
import json
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from metrics import measure  # noqa: E402


def check(path):
    lines = open(path, encoding="utf8").read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    errors = []
    total = None
    for l in lines[1:]:
        if l == "---":
            break
        if l.startswith("lines: "):
            total = int(l[7:])
        m = re.match(r"  - \[(\d+), (\d), (\".*\")\]$", l)
        if m:
            n, lv, title = int(m[1]), int(m[2]), json.loads(m[3])
            want = "#" * lv + " " + title
            if n > len(lines) or lines[n - 1] != want:
                errors.append(f"toc line {n}: expected {want!r}, found {lines[n - 1] if n <= len(lines) else 'EOF'!r}")
    if total != len(lines):
        errors.append(f"front matter says lines: {total}, file has {len(lines)}")
    r = measure(path)
    if r["dead"]:
        errors.append(f"{r['dead']} of {r['links']} internal links do not resolve")
    if r["html"]:
        errors.append(f"{r['html']} raw HTML tags outside code fences")
    return errors


if __name__ == "__main__":
    bad = False
    for p in sys.argv[1:]:
        errs = check(p)
        print(f"{'FAIL' if errs else 'ok  '} {p}")
        for e in errs[:10]:
            print("     " + e)
        bad |= bool(errs)
    sys.exit(1 if bad else 0)
