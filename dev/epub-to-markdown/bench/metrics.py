#!/usr/bin/env python3
"""Compare Markdown outputs of different ePub converters.

Usage: metrics.py OUT1.md [OUT2.md ...]      (prints a Markdown table)

Columns
  bytes / est_tok   size; tokens estimated as CJK chars + other bytes / 3.6
                    (rough, but consistent across converters)
  toc               entries in our front matter toc, or books-for-bots' chapters
  headings          ATX headings outside code fences
  fences / lang     fenced code blocks / those with a real language (not text,
                    and not pandoc's copied CSS class such as "source")
  nbsp              non-breaking spaces left anywhere (should be ~0 inside code)
  inline            `inline code` spans outside fences
  links / dead      internal links (#... or relative *.html) / those whose
                    target is not a heading slug in the same file
  html              raw HTML tags outside fences
  images            ![..](..) references
"""
import re
import sys

CJK = re.compile(r"[　-鿿＀-￯]")
FENCE = re.compile(r"^\s*(?:>\s*)*(`{3,}|~{3,})\s*(.*)$")
# fence info strings that are not languages (pandoc copies the first CSS class)
NOT_A_LANG = {"", "text", "source", "sourcecode", "screen", "programlisting"}
HTML = re.compile(r"</?(?:div|span|aside|section|figure|table|tr|td|th|img|math|svg|p|a|pre|code)\b[^>]*>")


def slug(text, used):
    s = re.sub(r"\\(.)", r"\1", text).lower()
    s = re.sub(r"[!-,./:-@\[\]\\^`{-~]", "", s)
    s = re.sub(r"\s+", "-", s) or "section"
    n = used.get(s)
    used[s] = (n or 0) + 1
    return s if n is None else f"{s}-{n}"


def measure(path):
    text = open(path, encoding="utf8").read()
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") else text
    head = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
    # our [line, level, title] entries, or books-for-bots' "- title:" chapters
    toc = len(re.findall(r"^  - (?:\[\d+, \d, |title: )", head, re.M))
    r = dict(file=path, bytes=len(text.encode()), toc=toc, headings=0, fences=0, lang=0,
             nbsp=text.count("\xa0"), inline=0, links=0, dead=0, html=0, images=0)
    cjk = len(CJK.findall(text))
    r["est_tok"] = int(cjk + (len(text.encode()) - 3 * cjk) / 3.6)
    slugs, used, links, fence = set(), {}, [], None
    for line in body.split("\n"):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            continue
        if m:
            fence = m.group(1)
            r["fences"] += 1
            r["lang"] += m.group(2).strip().lower() not in NOT_A_LANG
            continue
        h = re.match(r"(#{1,6}) +(.*?)\s*$", line)
        if h:
            r["headings"] += 1
            slugs.add(slug(h.group(2), used))
        prose = re.sub(r"`+[^`]*`+", "", line)
        r["inline"] += len(re.findall(r"`[^`]+`", line))
        r["html"] += len(HTML.findall(prose))
        r["images"] += len(re.findall(r"!\[[^\]]*\]\(", prose))
        links += re.findall(r"\]\(([^)\s]*)\)", prose)
    local_html = lambda l: "://" not in l and re.search(r"\.x?html?(#|$)", l)
    internal = [l for l in links if l.startswith("#") or local_html(l)]
    r["links"] = len(internal)
    r["dead"] = sum(1 for l in internal if local_html(l) or l[1:] not in slugs)
    return r


COLS = ["bytes", "est_tok", "toc", "headings", "fences", "lang", "nbsp", "inline", "links", "dead", "html", "images"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print("| file | " + " | ".join(COLS) + " |")
    print("|---" * (len(COLS) + 1) + "|")
    for p in sys.argv[1:]:
        r = measure(p)
        print(f"| {p} | " + " | ".join(str(r[c]) for c in COLS) + " |")
