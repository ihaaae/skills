#!/usr/bin/env python3
"""epub2md: convert an ePub into one agent-friendly Markdown file.

pandoc does the conversion; a Lua filter (epub2md.lua, next to this script)
fixes code-block languages, admonitions, cross-references and raw HTML; this
script then compacts tables and prepends a YAML front matter with a
line-numbered table of contents.

Usage: epub2md.py BOOK.epub [-o OUT.md] [--toc-depth N] [--media DIR]
Requires: pandoc on PATH.
"""
import argparse, html, json, os, posixpath, re, subprocess, sys, tempfile, zipfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET

LUA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "epub2md.lua")

DC = "{http://purl.org/dc/elements/1.1/}"
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


def metadata(path):
    """Title / authors / language from the OPF package document."""
    meta = {"title": "", "authors": [], "language": ""}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "META-INF/encryption.xml" in names:
                enc = z.read("META-INF/encryption.xml").decode("utf8", "replace")
                algos = set(re.findall(r'Algorithm="([^"]+)"', enc))
                if any("idpf.org/2008/embedding" not in a and "ns.adobe.com/pdf/enc" not in a for a in algos):
                    print("warning: this ePub has encrypted content (DRM?); output may be empty or garbled", file=sys.stderr)
            container = ET.fromstring(z.read("META-INF/container.xml"))
            opf = next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile"))
            root = ET.fromstring(z.read(opf))
        meta["title"] = (root.findtext(f".//{DC}title") or "").strip()
        meta["authors"] = [e.text.strip() for e in root.iter(f"{DC}creator") if e.text and e.text.strip()]
        meta["language"] = (root.findtext(f".//{DC}language") or "").strip()
    except Exception as e:  # metadata is nice-to-have
        print(f"warning: could not read ePub metadata: {e}", file=sys.stderr)
    return meta


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def nav_targets(z):
    """[(zip member, fragment, depth, title)] from the EPUB3 nav document or the EPUB2 NCX."""
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf = next(e.get("full-path") for e in container.iter() if local(e.tag) == "rootfile")
    items = [e for e in ET.fromstring(z.read(opf)).iter() if local(e.tag) == "item"]
    join = lambda base, href: posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href)))
    out = []

    def add(base, href, depth, title):
        path, _, frag = (href or "").partition("#")
        title = " ".join((title or "").split())
        if path and title:
            out.append((join(base, path), frag, min(depth, 6), title))

    def walk_nav(base, ol, depth):
        for li in ol:
            if local(li.tag) != "li":
                continue
            for c in li:
                if local(c.tag) == "a":
                    add(base, c.get("href"), depth, "".join(c.itertext()))
                elif local(c.tag) == "ol":
                    walk_nav(base, c, depth + 1)

    def walk_ncx(base, node, depth):
        for c in node:
            if local(c.tag) != "navPoint":
                continue
            label = next((t.text for t in c.iter() if local(t.tag) == "text"), "")
            src = next((t.get("src") for t in c if local(t.tag) == "content"), "")
            add(base, src, depth, label)
            walk_ncx(base, c, depth + 1)

    for it in items:
        if "nav" in (it.get("properties") or "").split():
            try:
                name = join(opf, it.get("href"))
                navs = [e for e in ET.fromstring(z.read(name)).iter() if local(e.tag) == "nav"]
                toc = next((n for n in navs if any(local(k) == "type" and "toc" in v for k, v in n.attrib.items())), navs[0])
                walk_nav(name, next(c for c in toc if local(c.tag) == "ol"), 1)
            except Exception:
                out.clear()
    if not out:
        for it in items:
            if it.get("media-type") == "application/x-dtbncx+xml":
                name = join(opf, it.get("href"))
                root = ET.fromstring(z.read(name))
                walk_ncx(name, next(e for e in root.iter() if local(e.tag) == "navMap"), 1)
    return out


def norm(t):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).lower().split())


def promote_headings(z, texts):
    """Books without <h1>..<h6> (calibre/Kindle conversions) style plain <p> as
    headings. Turn the paragraphs that the book's own navigation points at into
    real headings; edits `texts` (zip member -> xhtml) in place, returns the count."""
    byfile, count = {}, 0
    for name, frag, depth, title in nav_targets(z):
        if name in texts:
            byfile.setdefault(name, []).append((frag, depth, title))
    for name, entries in byfile.items():
        text = texts[name]
        if re.search(r"<h[1-6]\b", text):
            continue  # this file already has real headings
        for frag, depth, title in entries:
            b = norm(title)
            if frag:
                pat = r"(?P<p><p\b(?P<a>[^>]*\bid=[\"']%s[\"'][^>]*)>(?P<i>.*?)</p>)" % re.escape(frag)
                m = re.search(pat, text, re.S)
            else:
                # the file itself is the target: one of its first paragraphs
                # with text (anchors and empty <p/> may come before it)
                body = re.search(r"<body\b[^>]*>", text)
                para = re.compile(r"(?P<p><p\b(?P<a>[^>]*?)(?<!/)>(?P<i>.*?)</p>)", re.S)
                cands = [x for x in para.finditer(text, body.end() if body else 0) if norm(x.group("i"))][:3]
                m = next((x for x in cands if norm(x.group("i")) in b or b in norm(x.group("i"))), None)
            if not m:
                continue
            a = norm(m.group("i"))
            if not a or len(a) > 200 or not (a in b or b in a):
                continue
            text = f"{text[:m.start('p')]}<h{depth}{m.group('a')}>{m.group('i')}</h{depth}>{text[m.end('p'):]}"
            count += 1
        texts[name] = text
    return count


def css_margins(z):
    """class -> first-line indent in pt (margin-left + text-indent), from the
    book's stylesheets; hanging indents put the first line left of the margin."""
    unit = {"pt": 1, "px": 0.75, "em": 12, "rem": 12}
    out = {}
    for name in z.namelist():
        if name.lower().endswith(".css"):
            css = z.read(name).decode("utf8", "replace")
            for cls, body in re.findall(r"\.([\w-]+)\s*\{([^}]*)\}", css):
                pt = lambda m: float(m.group(1)) * unit[m.group(2)] if m else 0
                m = re.search(r"margin-left\s*:\s*(-?[\d.]+)(pt|px|em|rem)", body)
                t = re.search(r"text-indent\s*:\s*(-?[\d.]+)(pt|px|em|rem)", body)
                if m or t:
                    out[cls] = pt(m) + pt(t)
    return out


def listing_tables(text, margins):
    """Pseudocode typeset as a table whose first column is consecutive line
    numbers (CLRS and similar): turn it into a <pre>, keeping the nesting that
    the code cells express only through CSS margin-left classes."""
    def cell_text(c):
        c = re.sub(r"<br\s*/?>", " ", c)
        return " ".join(html.unescape(re.sub(r"<[^>]+>", "", c)).split())

    def convert(m):
        rows = re.findall(r"<tr\b.*?</tr>", m.group(0), re.S)
        cells = [re.findall(r"<td\b[^>]*>(.*?)</td>", r, re.S) for r in rows]
        if len(rows) < 2 or any(not 2 <= len(cs) <= 3 for cs in cells):
            return m.group(0)
        nums = [cell_text(cs[0]) for cs in cells]
        if not all(n.isdigit() for n in nums) or any(int(b) != int(a) + 1 for a, b in zip(nums, nums[1:])):
            return m.group(0)
        indent = []
        for cs in cells:
            cls = re.findall(r'class="([^"]*)"', cs[1])
            indent.append(max([margins.get(c, 0) for k in cls for c in k.split()] or [0]))
        lo = min(indent)
        levels = sorted({round(i, 1) for i in indent})
        step = min([b - a for a, b in zip(levels, levels[1:])] or [1])
        width = len(nums[-1])
        lines = []
        for n, cs, i in zip(nums, cells, indent):
            line = n.rjust(width) + "  " + "    " * round((i - lo) / step) + cell_text(cs[1])
            if len(cs) == 3 and cell_text(cs[2]):
                line += "  " + cell_text(cs[2])
            lines.append(line.rstrip())
        return "<pre>" + html.escape("\n".join(lines), quote=False) + "</pre>"

    return re.sub(r"<table\b.*?</table>", convert, text, flags=re.S)


MONO_FONT = re.compile(r"font-family\s*:[^;}]*(?:mono|courier|consolas|menlo|monaco|inconsolata)", re.I)
SPAN = re.compile(r"<span\b([^>]*)>([^<]*)</span>")
PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
GDOCS_SPAN = re.compile(r"""<span\s+class=["'](?:c|calibre)\d+(?:\s+(?:c|calibre)\d+)*["']\s*>""")

def gdocs_spans(inner):
    """True when every span has only Google Docs classes and all the text is
    inside spans (links may sit inside a span)."""
    depth, spans = 0, 0
    for tok in re.split(r"(<[^>]+>)", inner):
        if tok.startswith("<span"):
            if not GDOCS_SPAN.fullmatch(tok):
                return False
            depth += 1; spans += 1
        elif tok == "</span>":
            depth -= 1
        elif not tok.startswith("<") and tok.strip() and depth <= 0:
            return False
    return spans > 1


def css_monospace(z):
    """Classes whose font is monospace, from the book's stylesheets: only rules
    whose selectors are all plain classes (`.c32`, `span.c32`, `.a, .b`)."""
    out = set()
    for name in z.namelist():
        if name.lower().endswith(".css"):
            css = z.read(name).decode("utf8", "replace")
            for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
                parts = [re.fullmatch(r"\s*[\w-]*\.([\w-]+)\s*", x) for x in sel.split(",")]
                if MONO_FONT.search(body) and all(parts):
                    out.update(m.group(1) for m in parts)
    return out


def monospace_code(text, mono):
    """Google Docs exports (via calibre) have no <pre>, <code> or <tt>: code is
    plain <p>/<span> whose class sets a monospace font, one <p> per line. A run of
    paragraphs whose text is all in such spans becomes one <pre>; such a span in
    running text becomes <code>. Returns the new text, the number of <pre>, and
    the characters of text in code lines and in all paragraphs."""
    def is_mono(attrs):
        m = re.search(r"\bclass=[\"']([^\"']*)[\"']", attrs)
        return bool(m and mono & set(m.group(1).split()))

    def code_line(inner):
        """The line of code a paragraph holds, or None: every tag in it is a
        <span> without nested tags, and every span with text is monospace."""
        if SPAN.sub("", inner).strip():
            return None
        spans = SPAN.findall(inner)
        if not any(t.strip() for _, t in spans) or any(t.strip() and not is_mono(a) for a, t in spans):
            return None
        return "".join(t for _, t in spans)

    def prose(p, inner):
        # calibre puts each Google Docs span (classes c0, c1, ..., some renamed
        # calibre3) on its own line; when all the text is in such spans, the words
        # carry their own spaces and the newlines between tags are layout
        if gdocs_spans(inner):
            p = re.sub(r">\s*\n\s*<", "><", p)
        if re.search(r"<(?:code|tt|kbd|samp|pre)\b", p):
            return p  # the book marks code itself
        return SPAN.sub(lambda m: f"<code>{m.group(2)}</code>" if is_mono(m.group(1)) and m.group(2).strip() else m.group(0), p)

    out, pos, run, count, code_chars, chars = [], 0, [], 0, 0, 0
    def flush():
        nonlocal count
        if run:
            out.append("<pre>" + "\n".join(run) + "</pre>")
            run.clear(); count += 1
    for m in PARA.finditer(text):
        gap, line = text[pos:m.start()], code_line(m.group(1))
        n = len(norm(m.group(1)))
        chars += n
        code_chars += n if line is not None else 0
        if line is None or gap.strip():
            flush(); out.append(gap)
        if line is None:
            out.append(prose(m.group(0), m.group(1)))
        else:
            run.append(line)
        pos = m.end()
    flush()
    out.append(text[pos:])
    return "".join(out), count, code_chars, chars


NOTE_REF = re.compile(r"<sup\b[^>]*>\s*\[?\s*<a\b[^>]*\bhref=[\"'][^\"'#]*#([^\"']+)[\"']"
                      r"|<a\b[^>]*\bhref=[\"'][^\"'#]*#([^\"']+)[\"'][^>]*>\s*<sup\b")


def footnote_anchors(texts):
    """pandoc drops the id of a <p>, so a footnote kept as <p id="n1"> (O'Reilly
    HTMLBook, calibre) can't be found by its reference. Move the id of every
    paragraph that a superscript link points at onto an <a id> at its start;
    edits `texts` in place."""
    targets = {a or b for t in texts.values() for a, b in NOTE_REF.findall(t)}

    def move(m):
        if m.group(2) not in targets:
            return m.group(0)
        return f'<p{m.group(1)}{m.group(3)}><a id="{m.group(2)}"></a>'
    for name, text in texts.items():
        texts[name] = re.sub(r"<p\b([^>]*?)\s+id=[\"']([^\"']+)[\"']([^>]*)>", move, text)


def patch_epub(src, tmp):
    """Rewrite the spine documents before pandoc sees them; return the path of
    a patched copy (or src if nothing changed) and a few counts."""
    stats = {"headings_from_nav": 0, "listing_tables": 0, "code_from_css": 0}
    try:
        with zipfile.ZipFile(src) as z:
            docs = {n: z.read(n).decode("utf8", "replace") for n in z.namelist()
                    if re.search(r"\.x?html?$", n, re.I)}
            texts = dict(docs)
            try:
                stats["headings_from_nav"] = promote_headings(z, texts)
            except Exception as e:  # navigation is nice-to-have
                print(f"warning: could not use the ePub's navigation for headings: {e}", file=sys.stderr)
            footnote_anchors(texts)
            margins = css_margins(z)
            mono = css_monospace(z)
            if mono:
                done = {n: monospace_code(t, mono) for n, t in texts.items() if "<pre" not in t}
                # a book set in a monospace body font: most of its text would become code
                if 2 * sum(x[2] for x in done.values()) < sum(x[3] for x in done.values()):
                    for name, (text, n, _, _) in done.items():
                        texts[name] = text
                        stats["code_from_css"] += n
            for name, text in texts.items():
                if "<table" in text:
                    new = listing_tables(text, margins)
                    stats["listing_tables"] += new.count("<pre>") - text.count("<pre>")
                    texts[name] = new
            changed = {n: t.encode("utf8") for n, t in texts.items() if t != docs[n]}
            if not changed:
                return src, stats
            patched = os.path.join(tmp, "patched.epub")
            with zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as out:
                for info in z.infolist():
                    out.writestr(info, changed.get(info.filename) or z.read(info.filename))
            return patched, stats
    except Exception as e:
        print(f"warning: could not pre-process the ePub: {e}", file=sys.stderr)
        return src, stats


def run_pandoc(src, media):
    with tempfile.TemporaryDirectory() as tmp:
        src, patched = patch_epub(src, tmp)
        try:
            exts = subprocess.run(["pandoc", "--list-extensions=gfm"], capture_output=True, text=True).stdout
        except FileNotFoundError:
            sys.exit("error: pandoc not found. Install it first (macOS: brew install pandoc; Debian/Ubuntu: apt install pandoc).")
        # newer pandoc defaults to GitHub's $`x`$ / ```math; force plain $x$ and $$x$$
        fmt = "gfm-raw_html+tex_math_dollars" + ("-tex_math_gfm" if "tex_math_gfm" in exts else "")
        cmd = ["pandoc", "-f", "epub", "-t", fmt,
               "--wrap=none", "--reference-location=section", "--lua-filter", LUA, src]
        if media:
            cmd += ["--extract-media", media]
        env = dict(os.environ, EPUB2MD_MEDIA="1" if media else "0")
        r = subprocess.run(cmd, capture_output=True, env=env)
        if r.returncode != 0:
            sys.exit("pandoc failed:\n" + r.stderr.decode("utf8", "replace"))
        err = r.stderr.decode("utf8", "replace")
        counts = dict(re.findall(r"^epub2md:(\w+)=(\d+)\n", err, re.M))
        err = re.sub(r"^epub2md:.*\n", "", err, flags=re.M).strip()
        if err:
            print(err, file=sys.stderr)
        extra = {**patched, **{k: int(counts.get(k, 0)) for k in ("images_dropped", "images_placeholder", "footnotes")}}
        return r.stdout.decode("utf8"), extra


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


def main():
    ap = argparse.ArgumentParser(description="Convert an ePub to one agent-friendly Markdown file.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="output .md path (default: next to the ePub)")
    ap.add_argument("--toc-depth", type=int, default=2, help="deepest heading level listed in the toc (default 2)")
    ap.add_argument("--media", metavar="DIR", help="also extract images into DIR (default: images are not extracted)")
    a = ap.parse_args()

    out_path = a.output or os.path.splitext(a.epub)[0] + ".md"
    meta = metadata(a.epub)
    media = a.media and os.path.abspath(a.media)
    text, extra = run_pandoc(a.epub, media)
    if media:  # image links relative to the output file, so the pair can move together
        rel = os.path.relpath(media, os.path.dirname(os.path.abspath(out_path)))
        text = text.replace("](" + media + "/", "](" + rel + "/").replace("](<" + media + "/", "](<" + rel + "/")
    body, toc, stats = postprocess(text, a.toc_depth)
    stats.update(extra)
    lines = front_matter(meta, a.epub, toc, len(body)) + body
    with open(out_path, "w", encoding="utf8") as f:
        f.write("\n".join(lines) + "\n")

    report = {"output": out_path, "bytes": os.path.getsize(out_path), "lines": len(lines),
              "toc_entries": len(toc), **stats}
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
