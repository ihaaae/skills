-- Lua filter for epub2md.py, which passes it to pandoc with --lua-filter.
-- Fixes code-block languages, admonitions, cross-references and raw HTML;
-- reports counts on stderr as epub2md:<name>=<n> lines.
local MEDIA = os.getenv("EPUB2MD_MEDIA") == "1"
local NOISE = {source=1, sourcecode=1, screen=1, programlisting=1, highlight=1,
  code=1, pre=1, literal=1, listing=1, listingblock=1, hljs=1, prettyprint=1,
  numberlines=1, numbersource=1, linenums=1}
-- layout classes that sit on a <pre> without naming a language
-- (O'Reilly: "less_space pagebreak-before", "no-indent small")
local LAYOUT = {"break", "space", "indent", "small", "large", "width", "margin",
  "center", "left", "right", "float", "clear", "keep", "widow", "orphan", "wrap"}

local function is_layout(k)
  if k:find("_", 1, true) then return true end
  for _, w in ipairs(LAYOUT) do if k:find(w, 1, true) then return true end end
  return false
end
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
  -- a note's own backlink ("<sup><a href=#ref>1</a></sup> text") looks like a
  -- reference too; once its block has become a note it refers to nothing
  local function in_note(ids)
    for id in pairs(ids) do
      if holder[id] and gone[holder[id]] then return true end
    end
  end
  for _, r in ipairs(refs) do
    local h = holder[r.target]
    if h and not notes[r.target] and not r.ids[r.target] and not in_note(r.ids) then
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

-- gfm writes a table as a pipe table only when it has a header row and every
-- cell is one line; anything else would be HTML, which gfm-raw_html prints as
-- "[TABLE]". Google Docs tables have no <th> and cells of several paragraphs
-- or code lines: take the first row as the header and join a cell's lines with
-- <br>, the one piece of HTML a pipe-table cell can hold
local BR = pandoc.RawInline("gfm", "<br>")

local function cell_line(blocks)
  local out = pandoc.List()
  local function add(inlines)
    if #out > 0 and #inlines > 0 then out:insert(BR) end
    out:extend(inlines)
  end
  for _, b in ipairs(blocks) do
    if b.t == "Para" or b.t == "Plain" then
      local line = pandoc.List()
      for _, x in ipairs(b.content) do
        if x.t == "LineBreak" then add(line); line = pandoc.List()
        else line:insert(x) end
      end
      add(line)
    elseif b.t == "CodeBlock" then
      for l in (b.text .. "\n"):gmatch("(.-)\n") do
        -- a code cell's indentation would collapse in Markdown; keep it as nbsp
        local lead, rest = l:match("^( *)(.*)$")
        if rest ~= "" then add({pandoc.Code(("\194\160"):rep(#lead) .. rest)}) end
      end
    elseif b.t == "BulletList" or b.t == "OrderedList" then
      for i, item in ipairs(b.content) do
        local mark = b.t == "BulletList" and "- " or (i .. ". ")
        local l = cell_line(item)
        if #l > 0 then add(pandoc.List({pandoc.Str(mark)}) .. l) end
      end
    elseif b.t == "Div" or b.t == "BlockQuote" then
      add(cell_line(b.content))
    else
      local s = stringify(b)
      if s:match("%S") then add({pandoc.Str(s)}) end
    end
  end
  return out
end

local function one_line(c)
  local bs = c.contents
  return c.row_span == 1 and c.col_span == 1 and (#bs == 0 or (#bs == 1
    and (bs[1].t == "Plain" or bs[1].t == "Para")
    and not bs[1].content:find_if(function(x) return x.t == "LineBreak" end)))
end

local function pipe_table(el)
  el.attr = pandoc.Attr()
  local rows = pandoc.List()  -- pandoc.List(x) would extend x itself
  rows:extend(el.head.rows)
  for _, b in ipairs(el.bodies) do rows:extend(b.head); rows:extend(b.body) end
  rows:extend(el.foot.rows)
  local simple = true
  for _, r in ipairs(rows) do
    for _, c in ipairs(r.cells) do simple = simple and one_line(c) end
  end
  -- tables pandoc can already write stay exactly as they were
  if simple then return el end
  for _, r in ipairs(rows) do
    for _, c in ipairs(r.cells) do
      if not one_line(c) then c.contents = pandoc.Blocks{pandoc.Plain(cell_line(c.contents))} end
      c.row_span, c.col_span = 1, 1
    end
  end
  local body = el.bodies[1]
  if #el.head.rows == 0 and #el.bodies == 1 and #body.head == 0 and #body.body > 1 then
    el.head.rows = {body.body[1]}
    body.body = pandoc.List({table.unpack(body.body, 2)})
    el.bodies = {body}
  end
  return el
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
        if not NOISE[k] and not k:match("^lang") and not is_layout(k) and k:match("^[%w+#.-]+$") then
          lang = c break
        end
      end
    end
    -- the newline right after <pre> is not part of the code (HTML drops it)
    el.text = el.text:gsub("^[ \t]*\n", "")
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

  Table = pipe_table,
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
    -- pandoc's copy of the metadata cover, when the book has a cover page too
    if MEDIA and file == "" and imguses[el.src] >= 2 then
      dropped = dropped + 1
      return {}
    end
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

-- pass 3: drop whatever raw HTML and empty paragraphs and headings are left
local strip = {
  -- Google Docs page breaks are empty headings
  Header = function(el) if not stringify(el):match("%S") then return {} end end,
  RawBlock = function(el) if el.format == "html" then return {} end end,
  RawInline = function(el) if el.format == "html" then return {} end end,
  Para = function(el) if #el.content == 0 then return {} end end,
  Plain = function(el) if #el.content == 0 then return {} end end,
  -- gfm drops the Div itself anyway; unwrapped, the chapter headings are at the
  -- top level, where --reference-location=section looks for section ends
  Div = function(el) return el.content end,
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
