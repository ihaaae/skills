---
name: epub-to-markdown
description: 把 ePub 电子书转成单个给 Agent 读的 Markdown 文件（带行号目录、代码块语言、$ 公式）。用户要转换、阅读、检索或引用 .epub 内容时使用。
---

# ePub → Markdown

把一本 ePub 转成**一个** Markdown 文件，目标读者是 Agent：样式从简，只保留标题、段落、列表、表格、代码块、公式，开头附带行号目录，方便按章节读取而不是整本读入。

依赖：`pandoc` ≥ 3.0（已在 3.1.3 和 3.8 上验证）和 `python3`（只用标准库）。没有 pandoc 时先安装：macOS `brew install pandoc`，Debian/Ubuntu `apt install pandoc`。

## 步骤

1. 运行本 skill 目录下的脚本：

   ```bash
   python3 <本 skill 目录>/scripts/epub2md.py BOOK.epub -o BOOK.md
   ```

   可选参数：
   - `--toc-depth N`：目录收录到第几级标题，默认 2。
   - `--media DIR`：同时把图片解压到 DIR。默认不解压，只保留 `![alt](路径)` 引用，没有 alt 的图片直接丢弃。
2. 看 stderr 输出的 JSON 报告，按下面「检查」一节确认结果，然后把输出文件交给用户，或继续用它回答问题。

## 输出格式

- YAML front matter：`title`、`authors`、`language`、`source`、`lines`（总行数）和 `toc`。
- `toc` 每项是 `[行号, 标题级别, 标题]`，行号是输出文件里的绝对行号。一节的范围是从它的行号到下一项的行号。
- 标题：源文件有 `<h1>`–`<h6>` 时直接使用；章节用嵌套 `<section>` / `data-type="chapter|sect1|…"` 表达层级、标签却一律是 `<h1>` 的书（O'Reilly HTMLBook 常见），按嵌套深度把标题降到正确级别（只降不升）。没有标题标签时（calibre / Kindle 转出来的书常见），把书自带导航（EPUB3 nav 或 EPUB2 NCX）指向的段落提升为标题，级别取导航的层级。
- 代码块一律是围栏代码块，语言取自源文件的 `data-code-language` 属性或 `language-xxx` / `lang-xxx` class；源文件没标语言的记为 `text`。
- 没有 `<pre>` 的书：每一行都以 `<tt>` / `<code>` 开头的段落会被识别为代码清单，转成 `text` 代码块，不间断空格还原成普通空格并去掉公共缩进；行首的 `?` 之类的页边标记原样保留。
- 用表格排版的伪代码（第一列是连续行号，如 CLRS）转成 `text` 代码块：`行号  代码  注释`，缩进按 CSS 的 `margin-left` + `text-indent` 还原成每级 4 个空格。
- class 为 `bold` / `italic` 的 span 转成粗体 / 斜体。
- 正文里的不间断空格换成普通空格；标题里连续的空格（模仿制表位的 “2.1      Insertion sort”）合并成一个。
- 公式是 `$...$` 和 `$$...$$`（由 MathML 转成 TeX）。
- 提示框和侧栏（note / tip / warning / sidebar，按 class、`data-type` 或 `epub:type` 识别）变成 `> **Note:** ...` 引用块；框内自带的小标题并入这个标签，不再单独成为标题。
- 例子、插图的标题（“Example 2-1. …”、“Figure 1-1. …”）变成粗体段落，不进标题和目录。
- 书内交叉引用改写成 `[文字](#slug)`，slug 是目标所在标题的 GitHub 风格锚点（小写、去掉 ASCII 标点、空格换成 `-`）；找不到目标的链接只保留文字；不解压图片时，指向纯图片页的链接（如 “Click here to view code image”）整个删除。
- 书末索引里指向同一节的重复链接（`[A](#a)-[A](#a)`、`, [A](#a), [A](#a)`）合并成一个。
- 表格是紧凑的管道表格；其余原始 HTML 全部丢弃。

## 读取转换结果

不要整本读入。先读 front matter（文件开头到第二个 `---`），在 `toc` 里找到相关章节，再用行号范围读取那一段（Read 的 offset/limit，或 `sed -n 'A,Bp'`）。需要跨章查找时对整个文件做 grep。

## 检查

报告里的字段：

- `leftover_html_tags` 应为 0。不为 0 通常是含多段内容的复杂表格被 pandoc 降级，grep 出来看是否丢了信息，并告诉用户。
- `code_with_lang` 明显小于 `code_blocks` 说明这本书的代码块没有语言标注，或用了脚本不认识的 class，属正常情况，不必修。
- `headings_from_nav` 大于 0：这本书没有标题标签，标题是从导航还原的，属正常情况。导航只列到小节为止的书，更细的小标题会是粗体段落，用 grep 找。
- `listing_tables` 大于 0：这么多张行号表格被转成了伪代码块，属正常情况。
- `toc_entries` 为 0 或极少：这本书既没有标题标签，导航也对不上正文，目录不可用，照实告诉用户，改用 grep 定位。
- `images_dropped` 是因为没有 alt 文字而丢弃的图片数。数量大且用户关心图表时，加 `--media DIR` 重跑并告诉用户图片在哪。
- `code_blocks` 为 0 而书里明显有代码：这本书的代码既不是 `<pre>` 也不是等宽标签，无法识别，告诉用户。
- 书里有公式而 `math_spans` 为 0：公式是图片而非 MathML（输出里是一串 `![art](images/...)` 之类的图片引用），本工具无法还原，告诉用户，不要自己编造公式。
- stderr 出现加密（DRM）警告：内容无法读取，直接告诉用户，不要尝试绕过。
