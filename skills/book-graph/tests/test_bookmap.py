import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "bookmap.py"
spec = importlib.util.spec_from_file_location("bookmap", SCRIPT)
bookmap = importlib.util.module_from_spec(spec)
sys.modules["bookmap"] = bookmap
spec.loader.exec_module(bookmap)

BOOK = """---
title: t
---
# Chapter 1. One
## Alpha
text about alpha
## Beta
See [“Alpha”](#alpha) and [“Gamma”](#gamma).
```go
## not a heading
x := 1
```
## Exercises
do things
# Chapter 2. Two
## Gamma
gamma text
"""


def write(tmp, book_map):
    b, m = tmp / "book.md", tmp / "map.md"
    b.write_text(BOOK)
    m.write_text(book_map)
    return str(b), str(m)


def test_check_complete(tmp_path, capsys):
    b, m = write(tmp_path, "| A1 alpha | 5–6 | write |\n| A2 beta | 7–12 | read |\n| — n/a | 16–17 |\n")
    assert bookmap.main(["check", b, m, "--ignore", "Exercises"]) == 0
    assert "覆盖完整" in capsys.readouterr().out


def test_check_reports_gap_and_overlap(tmp_path, capsys):
    b, m = write(tmp_path, "| A1 alpha | 5–8 | write |\n| A2 beta | 7–12 | read |\n")
    assert bookmap.main(["check", b, m]) == 1
    out = capsys.readouterr().out
    assert "重复覆盖：7: Beta" in out
    assert "未覆盖：13: Exercises" in out
    assert "未覆盖：16: Gamma" in out
    assert "not a heading" not in out


def test_stats_skips_code(tmp_path, capsys):
    b, m = write(tmp_path, "| A2 beta | 7–12 | read |\n")
    bookmap.main(["stats", b, m, "--small", "0"])
    assert "prose=   1 code=   4" in capsys.readouterr().out


def test_refs_back_and_forward(tmp_path, capsys):
    b, m = write(tmp_path, "| A1 alpha | 5–6 |\n| A2 beta | 7–12 |\n| B1 gamma | 16–17 |\n")
    bookmap.main(["refs", b, m])
    out = capsys.readouterr().out
    assert "A2    前置候选=['A1'] 前向引用=['B1']" in out
