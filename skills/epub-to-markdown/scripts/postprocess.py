"""epub2md, step 5: clean up pandoc's Markdown and build the front matter."""
import json, os, re

FENCE = re.compile(r"^(\s*(?:>\s*)*)(`{3,}|~{3,})\s*(.*)$")
HEADING = re.compile(r"^(#{1,6}) +(.*?)\s*#*\s*$")
SEP_CELL = re.compile(r"^\s*(:?)-+(:?)\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
INLINE_CODE = re.compile(r"`+[^`]*`+")
IMAGE = re.compile(r"!\[[^\]]*\]\(")
MATH = re.compile(r"\$\$|(?<![\\$\w])\$[^$\s](?:[^$]*[^$\s])?\$(?![\w$])")
# a back-of-book index points at many anchors inside one section; once every
# anchor is rewritten to its section, "[A](#a)-[A](#a)" and repeats are noise
LOCATOR = re.compile(r"\[[^\]]*\]\(#[^)\s]*\)")
# one sentence per line: a paragraph stays one paragraph, but no line runs to
# thousands of characters (line-based readers truncate them). A break goes after
# . ! ? before a capital, quote or CJK character, or after 。！？; never inside
# code, math or a link, never before * or _ (a closing ** at the start of a line
# no longer closes), and never where the next line would open a new block.
SENT_END = re.compile(r"[.!?][\"')\]”’]* +(?=[A-Z\"“‘(\[`$]|[^\x00-\x7f])|[。！？][”’」』）]* *(?=[^\s”’」』）*_])")
ABBREV = re.compile(r"(?:^|[\s(])(?:Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|vs|etc|e\.g|i\.e|cf|Fig|No|Vol|Ch|Sec|Eq|al)\.$", re.I)
UNSPLIT = re.compile(r"`+[^`]*`+|\$\$.*?\$\$|\$[^$]+\$|!?\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)]*\)|\[\^[^\]]+\]"
                     r"|(?<![\\*])\*\*[^*\s](?:[^*]|\\\*)*?(?<![\\\s])\*\*(?!\*)")
BLOCK_START = re.compile(r"(?:#{1,6}|[-*+]|\d{1,9}[.)])(?:\s|$)|[>|<]|`{3}|~{3}|[=-]+\s*$|\[[^\]]*\]:")
# quote markers and indentation repeat on every line; a list marker or a
# footnote label becomes the same width of spaces
LINE_PREFIX = re.compile(r"((?:\s*>)*\s*)((?:[-*+]|\d{1,9}[.)]|\[\^[^\]]+\]:)\s+)?")
HTML_TAG = re.compile(r"</?(?:div|span|aside|section|figure|table|tr|td|th|img|math|svg|p|a|pre|code)\b[^>]*>")


def dedupe_locators(line):
    if line.count("](#") < 2:
        return line
    line = re.sub(r"(%s)[-–]\1(?!\w)" % LOCATOR.pattern, r"\1", line)
    seen = set()

    def once(m):
        if m.group(1) in seen:
            return ""
        seen.add(m.group(1))
        return m.group(0)
    return re.sub(r", (%s)(?=,|$)" % LOCATOR.pattern, once, line)


def split_sentences(line):
    m = LINE_PREFIX.match(line)
    head, body = m.group(0), line[m.end():]
    if not body or HEADING.match(body):
        return [line]
    cont = m.group(1) + " " * len(m.group(2) or "")
    guard = [(g.start(), g.end()) for g in UNSPLIT.finditer(body)]
    parts, start = [], 0
    for s in SENT_END.finditer(body):
        cut = s.end()
        if (any(a < s.start() < b or a < cut < b for a, b in guard) or BLOCK_START.match(body, cut)
                or ABBREV.search(body, 0, s.start() + 1)):
            continue
        parts.append(body[start:cut].rstrip())
        start = cut
    parts.append(body[start:])
    return [head + parts[0]] + [cont + p for p in parts[1:]]


def compact_row(line):
    cells = CELL_SPLIT.split(line.strip())
    if len(cells) < 3 or cells[0].strip() or cells[-1].strip():
        return line
    cells = cells[1:-1]
    if all(SEP_CELL.match(c) for c in cells):
        cells = [(SEP_CELL.match(c).group(1) or "-") + "-" + (SEP_CELL.match(c).group(2) or "-") for c in cells]
        return "|" + "|".join(cells) + "|"
    return "| " + " | ".join(c.strip() for c in cells) + " |"


def postprocess(text, depth):
    out, toc = [], []
    stats = {"code_blocks": 0, "code_with_lang": 0, "tables": 0, "images": 0, "math_spans": 0, "leftover_html_tags": 0}
    fence, blanks = None, 0
    for line in text.split("\n"):
        line = line.rstrip()
        m = FENCE.match(line)
        if fence:
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not m.group(3):
                fence = None
            out.append(line)
            continue
        if m:
            fence = m.group(2)
            lang = m.group(3).strip()
            stats["code_blocks"] += 1
            stats["code_with_lang"] += lang not in ("", "text")
            out.append(f"{m.group(1)}{m.group(2)}{lang}")
            blanks = 0
            continue
        if not line:
            blanks += 1
            if blanks > 1:
                continue
            out.append(line)
            continue
        blanks = 0
        if line.startswith("|"):
            new = compact_row(line)
            stats["tables"] += new.startswith("|-") or new.startswith("|:")
            line = new
        else:
            line = dedupe_locators(line)
            h = HEADING.match(line)
            if h:  # "2.1      Insertion sort": spacing that imitated a tab stop
                line = h.group(1) + " " + re.sub(r"  +", " ", h.group(2))
                h = HEADING.match(line)
            if h and len(h.group(1)) <= depth:
                toc.append((len(out) + 1, len(h.group(1)), h.group(2)))
        prose = INLINE_CODE.sub("", line)
        stats["images"] += len(IMAGE.findall(prose))
        stats["math_spans"] += len(MATH.findall(prose))
        stats["leftover_html_tags"] += len(HTML_TAG.findall(prose))
        if line.startswith("|") or HEADING.match(line):
            out.append(line)
        else:
            out.extend(split_sentences(line))
    while out and not out[0]:
        out.pop(0)
        toc = [(n - 1, lv, t) for n, lv, t in toc]
    while out and not out[-1]:
        out.pop()
    return out, toc, stats


def front_matter(meta, src, toc, body_lines):
    q = lambda s: json.dumps(s, ensure_ascii=False)
    head = ["---", f"title: {q(meta['title'])}",
            "authors: [" + ", ".join(q(a) for a in meta["authors"]) + "]",
            f"language: {q(meta['language'])}", f"source: {q(os.path.basename(src))}",
            "lines: 0",
            "# toc entries are [line, heading level, title]; a section runs from its line to the next entry's line"]
    head.append("toc:" if toc else "toc: []")
    offset = len(head) + len(toc) + 2  # closing '---' and one blank line
    head[5] = f"lines: {body_lines + offset}"
    head += [f"  - [{n + offset}, {lv}, {q(t)}]" for n, lv, t in toc]
    return head + ["---", ""]
