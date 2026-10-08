#!/usr/bin/env python3
"""epub2md: convert an ePub into one agent-friendly Markdown file.

pandoc does the conversion; an embedded Lua filter fixes code-block languages,
admonitions, cross-references and raw HTML; this script then compacts tables
and prepends a YAML front matter with a line-numbered table of contents.

Usage: epub2md.py BOOK.epub [-o OUT.md] [--toc-depth N] [--media DIR]
Requires: pandoc >= 3.0 on PATH (tested with 3.1.3 and 3.8).
"""
import argparse, html, json, os, posixpath, re, subprocess, sys, tempfile, zipfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET

LUA = r'''
local MEDIA = os.getenv("EPUB2MD_MEDIA") == "1"
local NOISE = {source=1, sourcecode=1, screen=1, programlisting=1, highlight=1,
  code=1, pre=1, literal=1, listing=1, listingblock=1, hljs=1, prettyprint=1,
  numberlines=1, numbersource=1, linenums=1}
local ADMON = {admonition=1, note=1, tip=1, warning=1, caution=1, important=1, sidebar=1}
local stringify = pandoc.utils.stringify

-- pass 1 (document order): map every element id to the slug of its enclosing heading
local id2slug, used, cur, pending = {}, {}, nil, {}
-- spine files seen, and which of them contain any text (image-only pages do not)
local curfile, seenfile, hastext, dropped = nil, {}, {}, 0

local function slugify(s)
  s = pandoc.text.lower(s)
  s = s:gsub("[!-,%./:-@%[%]\\%^`{-~]", ""):gsub("%s+", "-")
  if s == "" then s = "section" end
  local n = used[s]
  used[s] = (n or 0) + 1
  if n then s = s .. "-" .. n end
  return s
end

-- pandoc < 3.2 names ids "file.xhtml#frag", newer ones "file.xhtml_frag"
local function canon(id) return (id:gsub("#", "_", 1)) end

local function leads_with_header(el)
  while el.t == "Div" and #el.content > 0 do el = el.content[1] end
  return el.t == "Header"
end

local function record(el)
  if el.t == "Str" then
    if curfile then hastext[curfile] = true end
    return nil
  end
  if el.t == "Header" then
    cur = slugify(stringify(el.content))
    for _, id in ipairs(pending) do id2slug[id] = cur end
    pending = {}
  end
  local ok, id = pcall(function() return el.identifier end)
  if not ok or not id or id == "" then return nil end
  if id:match("%.x?html?$") then curfile = id; seenfile[id] = true end
  id = canon(id)
  -- an id at the start of a spine file, or on a <section> wrapping its own
  -- heading, belongs to the heading that follows
  if el.t ~= "Header" and (cur == nil or id:match("%.x?html?$") or leads_with_header(el)) then
    pending[#pending + 1] = id
  else
    id2slug[id] = cur
  end
  return nil
end

-- pass 2: structural clean-up
local function capitalize(s) return (s:gsub("^%l", string.upper)) end

local function admon_quote(blocks, title)
  while #blocks == 1 and blocks[1].t == "Div" do blocks = blocks[1].content end
  if title and title ~= "" then
    local label = pandoc.Strong{pandoc.Str(title .. ":")}
    local first = blocks[1]
    if first and (first.t == "Para" or first.t == "Plain") then
      first.content:insert(1, pandoc.Space())
      first.content:insert(1, label)
    else
      blocks:insert(1, pandoc.Para{label})
    end
  end
  return pandoc.BlockQuote(blocks)
end

local function class_title(classes)
  for _, c in ipairs(classes) do
    local k = c:lower()
    if ADMON[k] and k ~= "admonition" then return capitalize(k) end
  end
  return nil
end

local function is_raw(b, pat)
  return b.t == "RawBlock" and b.format == "html" and b.text:match(pat)
end

-- a paragraph whose every line starts with a <tt>/<code> run is a code listing
-- (calibre/Kindle conversions have no <pre>); a short non-alphanumeric string
-- before the code, such as a margin marker, is kept as part of the line
local function code_para(el)
  local lines, line, started, pure, ncode = {}, "", false, true, 0
  for _, x in ipairs(el.content) do
    if x.t == "Code" then line = line .. x.text; started = true; ncode = ncode + 1
    elseif x.t == "LineBreak" then lines[#lines + 1] = line; line, started = "", false
    elseif x.t == "SoftBreak" or x.t == "Space" then line = line .. " "
    elseif x.t == "Str" and #x.text <= 2 and not x.text:match("%w") then line = line .. x.text
    elseif started then line = line .. stringify(x); pure = false
    else return nil end
  end
  lines[#lines + 1] = line
  if ncode == 0 then return nil end
  for i, l in ipairs(lines) do lines[i] = l:gsub("\194\160", " ") end
  if #lines < 2 and not (pure and lines[1]:match("^%?*%s")) then return nil end
  local indent
  for _, l in ipairs(lines) do
    if l:match("%S") then
      local n = #l:match("^ *")
      if not indent or n < indent then indent = n end
    end
  end
  for i, l in ipairs(lines) do lines[i] = l:sub((indent or 0) + 1) end
  return pandoc.CodeBlock(table.concat(lines, "\n"), pandoc.Attr("", {"text"}))
end

local clean = {
  Code = function(el)
    el.text = el.text:gsub("\194\160", " ")
    el.attr = pandoc.Attr()
    return el
  end,

  Para = code_para,
  Plain = code_para,

  -- nested quotes used purely for indentation
  BlockQuote = function(el)
    if #el.content == 1 and el.content[1].t == "BlockQuote" then return el.content[1] end
  end,

  -- <aside> arrives as a pair of raw HTML blocks around the content
  Blocks = function(bs)
    local out, i, changed = pandoc.List(), 1, false
    while i <= #bs do
      local b = bs[i]
      local j, inner, depth = i + 1, pandoc.List(), 1
      if is_raw(b, "^<aside[%s>]") then
        while j <= #bs do
          local c = bs[j]
          if is_raw(c, "^<aside[%s>]") then depth = depth + 1
          elseif is_raw(c, "^</aside>") then
            depth = depth - 1
            if depth == 0 then break end
          end
          inner:insert(c)
          j = j + 1
        end
      end
      if depth == 0 then
        local title = b.text:match('title="([^"]*)"')
        if not title then
          local cls = b.text:match('class="([^"]*)"') or ""
          local list = {}
          for c in cls:gmatch("%S+") do list[#list + 1] = c end
          title = class_title(list)
        end
        out:insert(admon_quote(inner, title))
        i, changed = j + 1, true
      else
        out:insert(b)
        i = i + 1
      end
    end
    if changed then return out end
  end,

  Div = function(el)
    for _, c in ipairs(el.classes) do
      if ADMON[c:lower()] then
        return admon_quote(el.content, el.attributes.title or class_title(el.classes))
      end
    end
  end,

  CodeBlock = function(el)
    local lang
    for _, c in ipairs(el.classes) do
      local m = c:match("^language%-(.+)$") or c:match("^lang%-(.+)$")
      if m then lang = m break end
    end
    if not lang then
      for _, c in ipairs(el.classes) do
        local k = c:lower()
        if not NOISE[k] and not k:match("^lang") and k:match("^[%w+#.-]+$") then lang = c break end
      end
    end
    -- pandoc writes class-less blocks as indented code; "text" keeps them fenced
    el.attr = pandoc.Attr("", {lang or "text"})
    return el
  end,

  Header = function(el)
    el.attr = pandoc.Attr()
    el.content = el.content:walk({
      Strong = function(s) return s.content end,
      Emph = function(s) return s.content end,
    })
    return el
  end,

  Link = function(el)
    if #el.content == 0 then return {} end
    if el.target:sub(1, 1) == "#" then
      -- a link to an image-only page is useless once images are not extracted
      local file = el.target:match("^#(.-%.x?html?)")
      if not MEDIA and file and seenfile[file] and not hastext[file] then return {} end
      local slug = id2slug[canon(el.target:sub(2))]
      if not slug then return el.content end
      el.target = "#" .. slug
    end
    el.attr = pandoc.Attr()
    return el
  end,

  Table = function(el) el.attr = pandoc.Attr() return el end,
  Figure = function(el) el.attr = pandoc.Attr() return el end,

  Span = function(el)
    if #el.content == 0 then return {} end
    -- calibre expresses emphasis as CSS classes
    if el.classes:includes("bold") then return pandoc.Strong(el.content) end
    if el.classes:includes("italic") then return pandoc.Emph(el.content) end
  end,

  Image = function(el)
    if not MEDIA and stringify(el.caption) == "" then
      dropped = dropped + 1
      return {}
    end
    el.attr = pandoc.Attr()
    return el
  end,
}

-- pass 3: drop whatever raw HTML and empty paragraphs are left
local strip = {
  RawBlock = function(el) if el.format == "html" then return {} end end,
  RawInline = function(el) if el.format == "html" then return {} end end,
  Para = function(el) if #el.content == 0 then return {} end end,
  Plain = function(el) if #el.content == 0 then return {} end end,
}

function Pandoc(doc)
  doc:walk({traverse = "topdown", Block = record, Inline = record})
  doc = doc:walk(clean):walk(strip)
  io.stderr:write("epub2md:images_dropped=" .. dropped .. "\n")
  return doc
end
'''

DC = "{http://purl.org/dc/elements/1.1/}"
FENCE = re.compile(r"^(\s*(?:>\s*)*)(`{3,}|~{3,})\s*(.*)$")
HEADING = re.compile(r"^(#{1,6}) +(.*?)\s*#*\s*$")
SEP_CELL = re.compile(r"^\s*(:?)-+(:?)\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
INLINE_CODE = re.compile(r"`+[^`]*`+")
IMAGE = re.compile(r"!\[[^\]]*\]\(")
MATH = re.compile(r"\$\$|(?<![\\$\w])\$[^$\s](?:[^$]*[^$\s])?\$(?![\w$])")
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


def promote_headings(src, tmp):
    """Books without <h1>..<h6> (calibre/Kindle conversions) style plain <p> as
    headings. Turn the paragraphs that the book's own navigation points at into
    real headings and return the path of a patched copy (or src if unchanged)."""
    norm = lambda t: " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).lower().split())
    try:
        with zipfile.ZipFile(src) as z:
            members = set(z.namelist())
            byfile = {}
            for name, frag, depth, title in nav_targets(z):
                if name in members:
                    byfile.setdefault(name, []).append((frag, depth, title))
            changed, count = {}, 0
            for name, entries in byfile.items():
                text = z.read(name).decode("utf8", "replace")
                if re.search(r"<h[1-6]\b", text):
                    continue  # this file already has real headings
                before = count
                for frag, depth, title in entries:
                    if frag:
                        pat = r"(?P<p><p\b(?P<a>[^>]*\bid=[\"']%s[\"'][^>]*)>(?P<i>.*?)</p>)" % re.escape(frag)
                    else:  # the file itself is the target: its first paragraph is the candidate
                        pat = r"<body\b[^>]*>\s*(?:<(?:div|section)\b[^>]*>\s*)*(?P<p><p\b(?P<a>[^>]*)>(?P<i>.*?)</p>)"
                    m = re.search(pat, text, re.S)
                    if not m:
                        continue
                    a, b = norm(m.group("i")), norm(title)
                    if not a or len(a) > 200 or not (a in b or b in a):
                        continue
                    text = f"{text[:m.start('p')]}<h{depth}{m.group('a')}>{m.group('i')}</h{depth}>{text[m.end('p'):]}"
                    count += 1
                if count > before:
                    changed[name] = text.encode("utf8")
            if not changed:
                return src, 0
            patched = os.path.join(tmp, "patched.epub")
            with zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as out:
                for info in z.infolist():
                    out.writestr(info, changed.get(info.filename) or z.read(info.filename))
            return patched, count
    except Exception as e:  # navigation is nice-to-have
        print(f"warning: could not use the ePub's navigation for headings: {e}", file=sys.stderr)
        return src, 0


def run_pandoc(src, media):
    with tempfile.TemporaryDirectory() as tmp:
        src, promoted = promote_headings(src, tmp)
        lua = os.path.join(tmp, "epub2md.lua")
        with open(lua, "w", encoding="utf8") as f:
            f.write(LUA)
        try:
            exts = subprocess.run(["pandoc", "--list-extensions=gfm"], capture_output=True, text=True).stdout
        except FileNotFoundError:
            sys.exit("error: pandoc not found. Install it first (macOS: brew install pandoc; Debian/Ubuntu: apt install pandoc).")
        # newer pandoc defaults to GitHub's $`x`$ / ```math; force plain $x$ and $$x$$
        fmt = "gfm-raw_html+tex_math_dollars" + ("-tex_math_gfm" if "tex_math_gfm" in exts else "")
        cmd = ["pandoc", "-f", "epub", "-t", fmt,
               "--wrap=none", "--lua-filter", lua, src]
        if media:
            cmd += ["--extract-media", media]
        env = dict(os.environ, EPUB2MD_MEDIA="1" if media else "0")
        r = subprocess.run(cmd, capture_output=True, env=env)
        if r.returncode != 0:
            sys.exit("pandoc failed:\n" + r.stderr.decode("utf8", "replace"))
        err = r.stderr.decode("utf8", "replace")
        m = re.search(r"^epub2md:images_dropped=(\d+)\n", err, re.M)
        err = re.sub(r"^epub2md:.*\n", "", err, flags=re.M).strip()
        if err:
            print(err, file=sys.stderr)
        extra = {"headings_from_nav": promoted, "images_dropped": int(m.group(1)) if m else 0}
        return r.stdout.decode("utf8"), extra


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
            h = HEADING.match(line)
            if h and len(h.group(1)) <= depth:
                toc.append((len(out) + 1, len(h.group(1)), h.group(2)))
        prose = INLINE_CODE.sub("", line)
        stats["images"] += len(IMAGE.findall(prose))
        stats["math_spans"] += len(MATH.findall(prose))
        stats["leftover_html_tags"] += len(HTML_TAG.findall(prose))
        out.append(line)
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
    text, extra = run_pandoc(a.epub, a.media)
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
