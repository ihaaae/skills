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
-- boxes whose own heading is a caption, not a section of the book
local CAPTIONED = {example=1, figure=1, table=1}
local stringify = pandoc.utils.stringify

-- HTMLBook / EPUB3 semantics survive as data-type / epub:type attributes
local function kinds(el)
  local out = {}
  for _, c in ipairs(el.classes) do out[c:lower()] = true end
  for _, k in ipairs({"data-type", "type", "epub:type"}) do
    for w in (el.attributes[k] or ""):gmatch("%S+") do out[w:lower()] = true end
  end
  return out
end

local function has_kind(el, set)
  if el.t ~= "Div" then return false end
  for k in pairs(kinds(el)) do if set[k] then return true end end
  return false
end

-- pass 1 (document order): map every element id to the slug of its enclosing heading
local id2slug, used, cur, pending = {}, {}, nil, {}
-- spine files seen, and which of them contain any text (image-only pages do not)
local curfile, seenfile, hastext, dropped = nil, {}, {}, 0

local function slugify(s)
  s = pandoc.text.lower(s):gsub("^%s+", ""):gsub("%s+$", "")
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

-- pass 0: books such as O'Reilly's HTMLBook use <h1> for every level and
-- encode the hierarchy as nested sections; take a heading's level from the
-- number of enclosing sections that open with a heading (only ever deeper than
-- the tag says, never shallower). A <section> and the
-- <div class="sect1"> right inside it count once (`chain`).
local SECTION = {section=1, part=1, chapter=1, preface=1, appendix=1, foreword=1,
  introduction=1, afterword=1, sect1=1, sect2=1, sect3=1, sect4=1, sect5=1}

local function leading_header(el)
  while el.t == "Div" and #el.content > 0 do el = el.content[1] end
  if el.t == "Header" then return el end
end

local function relevel(blocks, depth, chain)
  for i, b in ipairs(blocks) do
    if b.t == "Div" and not has_kind(b, ADMON) and not has_kind(b, CAPTIONED) then
      local link = chain and i == 1
      local h = has_kind(b, SECTION) and leading_header(b)
      if h and not link then
        relevel(b.content, depth + 1, true)
        h.level = math.min(math.max(h.level, depth + 1), 6)
      else
        relevel(b.content, depth, link)
      end
    end
  end
end

local aside = 0
local function record(el)
  -- headings inside a raw <aside> pair are box titles, not sections
  if el.t == "RawBlock" and el.format == "html" then
    if el.text:match("^<aside[%s>]") then aside = aside + 1
    elseif el.text:match("^</aside>") and aside > 0 then aside = aside - 1 end
  end
  if el.t == "Header" and aside > 0 then return nil end
  if el.t == "Str" then
    if curfile then hastext[curfile] = true end
    return nil
  end
  -- a note, sidebar or captioned example is not a section: its own heading is
  -- not a link target, and ids inside it belong to the surrounding section
  if has_kind(el, ADMON) or has_kind(el, CAPTIONED) then
    if curfile then hastext[curfile] = true end
    local function grab(x)
      local ok, id = pcall(function() return x.identifier end)
      if ok and id and id ~= "" then
        id = canon(id)
        if cur then id2slug[id] = cur else pending[#pending + 1] = id end
      end
    end
    grab(el)
    el:walk({Block = grab, Inline = grab})
    return nil, false
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

-- footnotes: a superscript that is nothing but a short internal link ("1",
-- "*", "†") whose target is a block elsewhere that links back or opens with the
-- same mark; the block becomes a real footnote and leaves its old place
local NOTEMARK = {["*"]=1, ["**"]=1, ["***"]=1, ["†"]=1, ["‡"]=1, ["§"]=1, ["¶"]=1}

local function note_mark(s)
  s = s:gsub("[%[%]%(%)%.%s]", "")
  if s:match("^%d%d?%d?$") or s:match("^%l$") or NOTEMARK[s] then return s end
end

-- the one element inside <sup>, ignoring brackets around it: <sup>[<a>1</a>]</sup>
local function sup_only(el, t)
  local found
  for _, x in ipairs(el.content) do
    if x.t == t and not found then found = x
    elseif not (x.t == "Space" or (x.t == "Str" and x.text:match("^[%[%]%(%)]+$"))) then return nil end
  end
  return found
end

-- the target and mark of <sup><a href="#x">1</a></sup> or <a href="#x"><sup>1</sup></a>
local function noteref(el)
  local link
  if el.t == "Superscript" then
    link = sup_only(el, "Link")
  elseif el.t == "Link" and #el.content == 1 and el.content[1].t == "Superscript" then
    link = el
  end
  if not link or link.target:sub(1, 1) ~= "#" then return nil end
  local mark = note_mark(stringify(link.content))
  if mark then return canon(link.target:sub(2)), mark end
end

local function is_anchor(x)
  return x.t == "Space" or x.t == "SoftBreak" or (x.t == "Span" and #x.content == 0)
end

-- the note's text without its leading anchors and mark (often a backlink)
local function note_body(inlines, mark)
  local out = pandoc.List(inlines)
  while out[1] and is_anchor(out[1]) do out:remove(1) end
  if out[1] and note_mark(stringify(out[1])) == mark then out:remove(1) end
  while out[1] and is_anchor(out[1]) do out:remove(1) end
  return out
end

local function footnotes(doc)
  local function info(b)
    local ids, links = {}, {}
    b:walk({Inline = function(x)
      local ok, id = pcall(function() return x.identifier end)
      if ok and id and id ~= "" then ids[canon(id)] = true end
      if x.t == "Link" and x.target:sub(1, 1) == "#" then links[#links + 1] = canon(x.target:sub(2)) end
    end})
    return ids, links
  end
  -- every id's holder: the paragraph it sits in, or a Div carrying it
  local holder, refs = {}, {}
  local function leaf(b)
    local ids, links = info(b)
    local h = {ids = ids, links = links, inlines = b.content}
    for id in pairs(ids) do holder[id] = holder[id] or h end
    b:walk({Inline = function(x)
      local t, m = noteref(x)
      if t then refs[#refs + 1] = {target = t, mark = m, ids = ids} end
    end})
  end
  doc:walk({
    Para = leaf, Plain = leaf,
    Div = function(d)
      if d.identifier ~= "" and d.content[1] and (d.content[1].t == "Para" or d.content[1].t == "Plain") then
        local ids, links = info(d)
        holder[canon(d.identifier)] = {ids = ids, links = links, inlines = d.content[1].content, div = d}
      end
    end,
  })
  local notes, gone, n = {}, {}, 0
  for _, r in ipairs(refs) do
    local h = holder[r.target]
    if h and not notes[r.target] and not r.ids[r.target] then
      local back = false
      for _, l in ipairs(h.links) do if r.ids[l] then back = true end end
      local lead
      for _, x in ipairs(h.inlines) do
        if not is_anchor(x) then lead = note_mark(stringify(x)) break end
      end
      if back or lead == r.mark then
        local first = note_body(h.inlines, r.mark)
        local body = pandoc.List{pandoc.Para(first)}
        if h.div then body:extend({table.unpack(h.div.content, 2)}) end
        notes[r.target] = body
        gone[h] = true
        n = n + 1
      end
    end
  end
  -- notes pandoc made itself (epub:type="noteref") keep their brackets and
  -- their own copy of the mark: "^([^1])" and "[^1]: ^([1]) text"
  local tidy = {
    Superscript = function(el)
      local note = sup_only(el, "Note")
      if note then return note end
    end,
    Note = function(el)
      local b = el.content[1]
      if b and (b.t == "Para" or b.t == "Plain") and b.content[1] then
        local mark = note_mark(stringify(b.content[1]))
        if mark then b.content = note_body(b.content, mark) return el end
      end
    end,
  }
  local native = 0
  doc:walk({Note = function() native = native + 1 end})
  if n == 0 then return doc:walk(tidy), native end
  local function drop_leaf(b)
    local ids = info(b)
    for id in pairs(ids) do
      local h = holder[id]
      if h and gone[h] and not h.div then return {} end
    end
  end
  local function is_gone(b)
    if b.t == "Para" or b.t == "Plain" then return drop_leaf(b) ~= nil end
    local h = b.t == "Div" and b.identifier ~= "" and holder[canon(b.identifier)]
    return h and gone[h] and h.div ~= nil
  end
  -- a notes section's own rule goes with the notes it held
  doc = doc:walk({traverse = "topdown", Div = function(d)
    local any = false
    for _, b in ipairs(d.content) do
      if is_gone(b) then any = true
      elseif b.t ~= "HorizontalRule" and stringify(b):match("%S") then return nil end
    end
    if any then return {}, false end
  end})
  doc = doc:walk({
    Para = drop_leaf, Plain = drop_leaf,
    Div = function(d)
      local h = d.identifier ~= "" and holder[canon(d.identifier)]
      if h and gone[h] and h.div then return {} end
    end,
  })
  local used = {}
  local function swap(el)
    local t = noteref(el)
    if t and notes[t] and not used[t] then
      used[t] = true
      return pandoc.Note(notes[t])
    end
  end
  return doc:walk(tidy):walk({Superscript = swap, Link = swap}), native + n
end

-- which spine file each image sits on, in document order and inside boxes too;
-- also how often each picture is used (a chapter ornament repeats, a figure doesn't)
local imgfile, imguses = nil, {}
local function tag_image(el)
  local ok, id = pcall(function() return el.identifier end)
  if ok and id and id:match("%.x?html?$") then imgfile = id end
  if el.t == "Image" then
    el.attributes["epub2md-file"] = imgfile or ""
    imguses[el.src] = (imguses[el.src] or 0) + 1
    return el
  end
end

-- shell sessions are rarely labelled; a block that opens with a "$ " prompt is
-- one, and so is a "# " root prompt followed by a command ("# cd /usr/src") --
-- a lowercase word, ./ or / path, not a "# $OpenBSD:" or "# Default" comment
local function guess_lang(text)
  if text:match("^%s*%$ ") then return "console" end
  local cmd = text:match("^%s*# ([%l%./]%S*)")
  return cmd and not cmd:match(":$") and "console" or "text"
end

-- pass 2: structural clean-up
local placeholders = 0
local function capitalize(s) return (s:gsub("^%l", string.upper)) end

local function admon_quote(blocks, title)
  while #blocks == 1 and blocks[1].t == "Div" do blocks = blocks[1].content end
  -- <aside><div class="sidebar">: the inner box is already a quote
  if #blocks == 1 and blocks[1].t == "BlockQuote" and not title then return blocks[1] end
  -- the box's own heading ("Note", or a sidebar's title) becomes its label
  if blocks[1] and blocks[1].t == "Header" then
    local h = stringify(blocks[1].content)
    blocks = pandoc.List({table.unpack(blocks, 2)})
    if not title or title == "" then
      title = h
    elseif not title:lower():find(h:lower(), 1, true) then
      title = title .. ": " .. h
    end
  end
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
    if ADMON[k] and k ~= "admonition" and k ~= "sidebar" then return capitalize(k) end
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
  local text = table.concat(lines, "\n")
  return pandoc.CodeBlock(text, pandoc.Attr("", {guess_lang(text)}))
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
    if has_kind(el, ADMON) then
      local list = {}
      for k in pairs(kinds(el)) do list[#list + 1] = k end
      table.sort(list)
      return admon_quote(el.content, el.attributes.title or class_title(list))
    end
    -- "Example 2-1. ..." / "Figure 1-1. ..." captions: bold text, not headings
    if has_kind(el, CAPTIONED) then
      return el.content:walk({
        Header = function(h) return pandoc.Para{pandoc.Strong(h.content)} end,
      })
    end
  end,

  CodeBlock = function(el)
    local lang
    for _, k in ipairs({"data-code-language", "code-language", "data-lang", "lang", "language"}) do
      local v = el.attributes[k]
      if v and v:match("^[%w+#.-]+$") then lang = v break end
    end
    for _, c in ipairs(lang and {} or el.classes) do
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
    el.attr = pandoc.Attr("", {lang or guess_lang(el.text)})
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
    local file = el.attributes["epub2md-file"]
    el.attr = pandoc.Attr()
    if MEDIA or stringify(el.caption) ~= "" then return el end
    -- an image-only page (a scanned code listing, a cover) repeats the text,
    -- pandoc puts the metadata cover before the first spine file, and a picture
    -- used three times or more is decoration; a figure among text leaves a
    -- marker so the reader knows to use --media
    if file == "" or (seenfile[file] and not hastext[file]) or imguses[el.src] >= 3 then
      dropped = dropped + 1
      return {}
    end
    placeholders = placeholders + 1
    return pandoc.RawInline("gfm", "[图: " .. el.src:match("[^/]*$") .. "]")
  end,
}

-- pass 3: drop whatever raw HTML and empty paragraphs are left
local strip = {
  RawBlock = function(el) if el.format == "html" then return {} end end,
  RawInline = function(el) if el.format == "html" then return {} end end,
  Para = function(el) if #el.content == 0 then return {} end end,
  Plain = function(el) if #el.content == 0 then return {} end end,
}

-- non-breaking spaces in prose (spaced-out section numbers, "Proof   We")
-- would end up inside heading slugs and break links; code keeps its own
local nbsp = {
  Str = function(el)
    if el.text:find("\194\160") then el.text = el.text:gsub("\194\160+", " ") return el end
  end,
}

function Pandoc(doc)
  doc = doc:walk(nbsp)
  local nnotes
  doc, nnotes = footnotes(doc)
  doc = doc:walk({traverse = "topdown", Block = tag_image, Inline = tag_image})
  relevel(doc.blocks, 0, false)
  doc:walk({traverse = "topdown", Block = record, Inline = record})
  doc = doc:walk(clean):walk(strip)
  io.stderr:write("epub2md:images_dropped=" .. dropped .. "\n")
  io.stderr:write("epub2md:images_placeholder=" .. placeholders .. "\n")
  io.stderr:write("epub2md:footnotes=" .. nnotes .. "\n")
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
UNSPLIT = re.compile(r"`+[^`]*`+|\$\$.*?\$\$|\$[^$]+\$|!?\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)]*\)|\[\^[^\]]+\]")
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


def patch_epub(src, tmp):
    """Rewrite the spine documents before pandoc sees them; return the path of
    a patched copy (or src if nothing changed) and a few counts."""
    stats = {"headings_from_nav": 0, "listing_tables": 0}
    try:
        with zipfile.ZipFile(src) as z:
            docs = {n: z.read(n).decode("utf8", "replace") for n in z.namelist()
                    if re.search(r"\.x?html?$", n, re.I)}
            texts = dict(docs)
            try:
                stats["headings_from_nav"] = promote_headings(z, texts)
            except Exception as e:  # navigation is nice-to-have
                print(f"warning: could not use the ePub's navigation for headings: {e}", file=sys.stderr)
            margins = css_margins(z)
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
               "--wrap=none", "--reference-location=section", "--lua-filter", lua, src]
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
