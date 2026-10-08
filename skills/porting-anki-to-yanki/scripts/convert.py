#!/usr/bin/env python3
"""Convert an Anki text export into a folder of yanki-compatible Markdown notes.

Usage:
    convert.py <source.txt> <dest_dir>

Source: an Anki "Notes in Plain Text (.txt)" export with header lines like
    #separator:tab
    #html:true
    #tags column:3
and tab-separated rows of (front, back, tags).

Dest: a folder inside an Obsidian vault (typically the leaf deck folder under
the yanki-watched Flashcards root).
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from pathlib import Path

CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", re.S)


def clean_html(s: str) -> str:
    """Strip HTML tags; convert <strong>/<b>/<em>/<i>/<br> to Markdown equivalents."""
    s = re.sub(r"<\s*(?:strong|b)\s*>(.*?)<\s*/\s*(?:strong|b)\s*>", r"**\1**", s, flags=re.I | re.S)
    s = re.sub(r"<\s*(?:em|i)\s*>(.*?)<\s*/\s*(?:em|i)\s*>", r"*\1*", s, flags=re.I | re.S)
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def convert_latex(s: str) -> str:
    r"""Convert Anki-style \( ... \) and \[ ... \] to GitHub-style $...$ / $$...$$."""
    s = re.sub(r"\\\((.+?)\\\)", lambda m: f"${m.group(1).strip()}$", s, flags=re.S)
    s = re.sub(r"\\\[(.+?)\\\]", lambda m: f"$$\n{m.group(1).strip()}\n$$", s, flags=re.S)
    return s


def has_cloze(s: str) -> bool:
    return bool(CLOZE_RE.search(s))


def convert_cloze(s: str) -> str:
    """Convert {{c1::text}} or {{c1::text::hint}} to yanki ~~text~~ syntax."""
    return CLOZE_RE.sub(lambda m: f"~~{m.group(1).strip()}~~", s)


def sanitize_filename(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[\\/:*?\"<>|]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s or "card"


def parse_anki_export(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (front, back, tags) tuples. Skips header lines starting with '#'."""
    with path.open(encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    reader = csv.reader(lines, delimiter="\t", quotechar='"')
    rows: list[tuple[str, str, str]] = []
    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue
        front = row[0] if len(row) > 0 else ""
        back = row[1] if len(row) > 1 else ""
        tags = row[2] if len(row) > 2 else ""
        rows.append((front, back, tags))
    return rows


def build_note(front: str, back: str, tags: str) -> str:
    front_md = convert_latex(clean_html(front))
    back_md = convert_latex(clean_html(back))
    tag_list = [t for t in re.split(r"\s+", tags.strip()) if t]

    cloze = has_cloze(front_md) or has_cloze(back_md)
    if cloze:
        front_md = convert_cloze(front_md)
        back_md = convert_cloze(back_md)

    if back_md:
        body = f"{front_md}\n\n---\n\n{back_md}"
    else:
        body = front_md

    if tag_list:
        # yanki reads tags from YAML frontmatter `tags:` list
        frontmatter = "---\ntags:\n" + "".join(f"  - {t}\n" for t in tag_list) + "---\n\n"
        body = frontmatter + body

    return body.rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert an Anki text export to yanki Markdown notes.")
    ap.add_argument("source", type=Path, help="Anki .txt export file")
    ap.add_argument("dest", type=Path, help="Destination folder (created if missing)")
    ap.add_argument(
        "--dry-run", action="store_true", help="Parse and report counts without writing files"
    )
    args = ap.parse_args()

    if not args.source.exists():
        print(f"source not found: {args.source}", file=sys.stderr)
        return 1

    rows = parse_anki_export(args.source)
    cloze_count = sum(1 for f, b, _ in rows if has_cloze(f) or has_cloze(b))
    basic_count = len(rows) - cloze_count
    print(f"parsed {len(rows)} rows ({basic_count} basic, {cloze_count} cloze)")

    if args.dry_run:
        return 0

    args.dest.mkdir(parents=True, exist_ok=True)
    used: dict[str, int] = {}
    for front, back, tags in rows:
        body = build_note(front, back, tags)
        first_line = next(
            (ln for ln in body.splitlines() if ln.strip() and not ln.startswith("---")),
            "card",
        )
        name = sanitize_filename(first_line)
        if name in used:
            used[name] += 1
            fname = f"{name} ({used[name]}).md"
        else:
            used[name] = 1
            fname = f"{name}.md"
        (args.dest / fname).write_text(body, encoding="utf-8")
    print(f"wrote {len(rows)} notes to {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
