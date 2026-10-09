# 实验记录

## 0. 调研：已有工具（2026-10-07）

| 工具 | 形态 | 要点 |
|---|---|---|
| [books-for-bots](https://github.com/prime-radiant-inc/books-for-bots) | Rust CLI | 单文件 GFM，YAML frontmatter 列出每章的行号和字节偏移；本项目 toc 设计参考了它 |
| [epub2md](https://hn.svelte.dev/item/45951820) | CLI | 每章一个 Markdown 文件 |
| [librarian-cli](https://enterprisedna.co/directories/mcp/terobyte-librarian-cli) | Python CLI + MCP | 分章、带 token 计数；项目很小 |
| [epub skill (aliceisjustplaying)](https://tomevault.io/tome/aliceisjustplaying/claude-resources-monorepo) | Claude Code skill | jszip + turndown，metadata / toc / chapter / full 子命令 |
| [markdown-converter skill](https://gist.github.com/AbhimanyuAryan/2bf1336f51cbacfb238c00426857d760) | skill | 包装 `uvx markitdown` |
| [book-to-skill](https://github.com/virgiliojr94/book-to-skill/wiki) | skill | 把整本书做成一个 skill，目标不同 |
| [anydoc](https://github.com/codehornets/anydoc) | Rust 库 + skill | 多格式转 GFM |
| MarkItDown、pandoc | 通用转换器 | baseline |

结论：没有一个同时做对「代码块语言」和「章节索引」，公式处理都没提。决定用 pandoc + Lua filter + 薄后处理自己做。

对比时使用的版本：pandoc 3.1.3（另用 3.8 交叉验证）、markitdown 0.1.7、books-for-bots 0.1.1。

## 1. Pro Git 中文版（第一轮）

源：21 个 xhtml，870 个 `<pre class="source language-*">`（console 734、ruby 37、空语言 34……），62 个 `<aside class="admonition">`，8 张表，188 张图。

baseline 的问题：
- 三者都丢了代码语言；pandoc 把第一个 class `source` 当成语言写成 ```` ``` source ````。
- pandoc 默认 `-t gfm` 留下 9848 个 `<div>`/`<span>`，必须 `-raw_html`；即使这样 `<aside>` 仍作为 raw HTML 漏出来。
- pandoc 的 gfm 表格按列宽补空格（表格部分 57 KB vs 紧凑 25 KB）。
- 跨章链接：pandoc 是 `#ch10-git-internals.xhtml#_refspec`（失效），markitdown 是 `#_services_hooks`（失效），books-for-bots 把 76 处跨章引用误判成脚注 `[^c9-_git_reset]`，链接文字丢失且没有定义。
- books-for-bots 丢图片和图注。

我们的结果（`bench/metrics.py`）：

| file | bytes | est_tok | toc | headings | fences | lang | nbsp | inline | links | dead | html | images |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfb.md | 857525 | 267773 | 20 | 556 | 870 | 0 | 34 | 3037 | 204 | 76 | 0 | 0 |
| markitdown.md | 877872 | 273921 | 0 | 284 | 871 | 0 | 35 | 1086 | 83 | 83 | 12 | 104 |
| pandoc.md | 926392 | 287429 | 0 | 556 | 870 | 0 | 35 | 3101 | 283 | 283 | 126 | 189 |
| skill.md | 883767 | 275840 | 120 | 537 | 870 | 826 | 35 | 3101 | 227 | 0 | 0 | 188 |

（pandoc 行是 `-t gfm-raw_html`。体积和其他工具基本持平：多了语言标注和 toc，省了表格填充。源 XHTML 估算约 404k token，纯文本层面各工具只省约 30%，真正的收益是可以按章读。）

过程中修掉的 bug：
- pandoc 对没有 class 的代码块输出缩进式代码块 → 统一补 `text`，保持围栏。
- 用 `<section id>` 包住标题的书，链接会映射到前一个标题 → id 在「以标题开头的 Div」上时挂到后面的标题。
- pandoc 3.8 的 id 命名从 `file.xhtml#frag` 改成 `file.xhtml_frag`，而链接仍写 `#file.xhtml#frag` → 统一 canon（第一个 `#` 换成 `_`）。
- pandoc 3.8 的 gfm 默认 `tex_math_gfm`（`` $`x`$ `` 和 ```` ```math ````）→ 检测到该扩展时显式关掉。
- pandoc 3.8 会给表格标题输出 `{#id}` → 清掉 Table/Figure 的 attr。

公式只用一个自造的 MathML 小样本验证过（行内、`$$` 积分、矩阵、正文里的 `$5` 被转义），真实公式书还没测。

## 2. The Practice of Programming（第二轮）

源：calibre 从 Kindle 格式转出，370 个 html。没有任何 `<h1>`–`<h6>` 和 `<pre>`；标题是加粗的 `<p>`；代码是 `<p>` 里一行行 `<tt>` 加 `<br>`，缩进全是不间断空格；坏代码行首有 `?` 标记；每段代码前有 “Click here to view code image” 链接，指向书末 355 个纯图片页；粗体斜体是 `<span class="bold|italic">`；导航（NCX）有 106 个条目。

第一版 skill 在这本书上：toc 0、代码块 0，和裸 pandoc 一样，没有优势。改进：
1. `promote_headings()`：用 NCX 把导航目标段落提升为标题 → 104/106（缺 Title Page、Copyright Page）。
2. Lua `code_para`：每行都以 `<tt>` 开头的段落 → 代码块，NBSP 还原、去公共缩进、保留 `?` 标记；行内允许夹斜体等（伪代码里的占位符）。
3. 指向纯图片页的链接整个删除（不解压图片时）。
4. `bold` / `italic` class → 强调；只含一个引用块的引用块压平。

| file | bytes | est_tok | toc | headings | fences | lang | nbsp | inline | links | dead | html | images |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfb.md | 657175 | 182548 | 371 | 382 | 0 | 0 | 0 | 0 | 481 | 39 | 1 | 384 |
| markitdown.md | 767173 | 213103 | 0 | 0 | 0 | 0 | 24519 | 0 | 2857 | 2857 | 1 | 384 |
| pandoc.md | 785903 | 218306 | 0 | 0 | 0 | 0 | 24536 | 5369 | 2857 | 2857 | 2 | 385 |
| skill.md | 648702 | 180195 | 104 | 104 | 453 | 0 | 475 | 2364 | 1187 | 0 | 0 | 0 |

（bfb 的 toc 371 里有 353 条是同名的 “The Practice of Programming” 图片页；它的 headings 计数包含没进代码块的 `# 注释`。我们剩下的 475 个 NBSP 在版权页等正文里，不在代码中。）

这一轮的改动让 Pro Git 的输出逐字节不变；两本书在 pandoc 3.1.3 和 3.8 上都通过回归。

## 3. Learning Go 第 2 版（第三轮，2026-10-08）

源：O'Reilly HTMLBook，16 章 + 序言 + 索引。`<section data-type="chapter|sect1|sect2|sect3">` 嵌套，但章和 sect1 的标题都是 `<h1>`（sect2 是 `<h2>`，sect3 是 `<h3>`）；代码是 `<pre data-type="programlisting" data-code-language="go">`（618 个有语言，199 个是 shell 输出没有）；提示框是 `<div data-type="note|tip|warning">` 加 `<h6>Note</h6>`；侧栏是 `<aside data-type="sidebar"><div class="sidebar"><h1>…`；例子和插图的标题是 `<h5>` / `<h6>`；书末索引有约 3000 个指向 indexterm 锚点的链接。

改之前 skill 在这本书上的问题：
- 代码语言 13/827：pandoc 把 `data-code-language` 变成属性 `code-language`，脚本只看 class。
- 层级拍平：章和 sect1 都是 1 级，目录 326 条、混在一起。
- 770 个死链：提示框里的 `###### Note`、侧栏标题被 pass 1 当成节，索引锚点挂到了 “Note” 上；而这些标题最终在引用块里（`> ###### Note`），slug 计数和正文对不上。
- 侧栏变成两层引用（`> >`）；“Example 2-1.” 之类的标题占了 52 个 5 级标题。

改进：
1. CodeBlock 先看 `data-code-language` / `code-language` / `data-lang` / `lang` 属性 → 628/827。
2. pass 0 `relevel`：按 section 类容器（class `section` 或 `data-type`/`epub:type` 为 chapter、sect1… 等）的嵌套深度定级别。第一版直接覆盖级别，Pro Git 的 sect1（`<h2>`，外面没有可计数的章容器）被升成 1 级 → 改成只降不升。
3. 提示框 / 侧栏 / 例子 / 插图（按 class、`data-type`、`epub:type` 识别）在 pass 1 里整体跳过，内部 id 归到外层节；raw `<aside>` 对之间的标题同样跳过。框内首个标题并入 `**Note:**` 标签（标签已包含标题文字时直接丢掉），例子/插图标题改成粗体段落。
4. 后处理合并索引里的重复链接。

| file | bytes | est_tok | toc | headings | fences | lang | nbsp | inline | links | dead | html | images |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfb.md | 977329 | 271481 | 25 | 637 | 823 | 0 | 0 | 4156 | 3171 | 240 | 0 | 2 |
| markitdown.md | 1078502 | 299585 | 0 | 638 | 827 | 0 | 162 | 4154 | 3273 | 3272 | 6 | 20 |
| pandoc.md | 1083642 | 301013 | 0 | 637 | 827 | 14 | 184 | 4164 | 3273 | 3273 | 28 | 23 |
| skill.md（改前） | 1115024 | 309730 | 326 | 473 | 827 | 13 | 192 | 4164 | 3263 | 770 | 0 | 17 |
| skill.md（改后） | 1098368 | 305103 | 195 | 363 | 827 | 628 | 208 | 4164 | 2974 | 0 | 0 | 17 |

（headings 比 baseline 少是有意的：187 个提示框标题和 52 个例子标题不再是标题。toc 195 条 = 章 + sect1，层级 1/2/3/4 分别是 26/171/155/13 个标题。体积比 pandoc 多 1.4%，主要是 toc；索引从 224 KB 降到 184 KB。）

对 Pro Git 的影响：正文只少了 19 处 `> ## 标题`——`<aside title="Note: X">` 里重复的 X 标题，toc、链接不变。TPOP 手头没有，没能重跑；它没有 `<section>`、提示框也不是这些 class，预计不受影响，但 golden 行未经本轮验证。三本书中可得的两本在 pandoc 3.1.3 和 3.8 上都通过 `check.py` 和回归。

## 4. Introduction to Algorithms 第 4 版 + TPOP 复测（第四轮，2026-10-08）

TPOP 拿到了（sha256 与 golden 一致）：第三轮的改动对它逐字节无影响。

CLRS 源：35 章 + 8 个 Part + 附录，没有任何 `<h1>`–`<h6>`（只有 3 个 `<h2>`）；NCX 257 项，三级：Part → 章（指向文件本身，无 `#frag`）→ 节（`<p class="level1" id="h1-N">`）；章文件开头是 `<a id="p17"/>` 和空的 `<p class="line-c"/>`，然后才是章标题段落；伪代码是两三列的表格，第一列是行号，代码缩进只靠 class `p2`–`p7`（`margin-left: 40–140pt; text-indent: -20pt`）；公式全是 `<img alt="art">`，没有 MathML；正文和标题里大量不间断空格（“2.1&nbsp;&nbsp;&nbsp;&nbsp;Insertion sort”）。

改之前 skill 在 CLRS 上的问题：
- 章标题没被提升（无 frag 的导航只看紧跟 `<body>` 的第一个 `<p>`，被锚点和空 `<p/>` 挡住）→ toc 只有 22 条，其中 8 条是同名的 “Introduction”。
- 伪代码表格变成管道表格，缩进全丢；CLRS 的伪代码没有 end，缩进就是块结构。
- 28438 个不间断空格；更糟的是标题 slug 里带着 NBSP（`#134    deletion`），这种链接在 Markdown 里不是合法链接，metrics 也没把它们算进 links（所以 dead 显示 0，其实是坏的）。Learning Go 也有 13 个这样的隐藏坏链（`[if](#if-  )`）。

改进：
1. 导航只指向文件时，在开头前 3 个有文字的段落里找标题（跳过自闭合的 `<p/>`）→ headings_from_nav 157 → 207。
2. `listing_tables()` 预处理：第一列是连续行号的 2–3 列表格 → `<pre>`；缩进 = `margin-left` + `text-indent`（第一版只看 margin-left，级差算成 40pt，p3、p4 缩成同一级）。172 张表全部是伪代码，逐个看过没有误判。
3. Lua 先把 Str 里的 NBSP 换成空格；slug 去掉首尾空白；后处理合并标题里的连续空格。

| file | bytes | est_tok | toc | headings | fences | lang | nbsp | inline | links | dead | html | images |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfb.md | 2904381 | 806772 | 56 | 56 | 0 | 0 | 0 | 0 | 1718 | 41 | 0 | 1987 |
| markitdown.md | 3007376 | 835382 | 0 | 0 | 0 | 0 | 5457 | 0 | 7435 | 7435 | 0 | 1987 |
| pandoc.md | 3210662 | 891850 | 0 | 0 | 0 | 0 | 6464 | 0 | 7435 | 7435 | 0 | 1988 |
| skill.md（改前） | 3082828 | 856341 | 22 | 157 | 0 | 0 | 28438 | 0 | 778 | 0* | 0 | 1987 |
| skill.md（改后） | 3018581 | 838494 | 72 | 207 | 172 | 0 | 0 | 0 | 5921 | 0 | 0 | 1955 |

（* 改前大部分链接因 slug 含 NBSP 没被计入。toc 72 = Part + 章 + Part 导言；节是 3 级标题（`--toc-depth 3` 可以收进 toc）；更细的 “2.3.2 …” 小标题不在导航里，仍是粗体段落。1955 张图几乎都是 `alt="art"` 的公式图片，无法还原。）

对其他书：Pro Git、TPOP 只有 NBSP → 空格（TPOP nbsp 475 → 0）；Learning Go 另外修好了 13 个 `#if` 链接。四本书在 pandoc 3.1.3 和 3.8 上都通过 `check.py` 和回归（3.8 下 CLRS 少 27 张管道表格，是 pandoc 本身的差异）。

## 5. 占位符、console、脚注、按句断行（第五轮，2026-10-09）

按上一轮「已知缺陷」的讨论做了四件事（按内容猜 TPOP 代码语言不做：误判代价大于收益）：

1. 无 alt 图片：不解压时，插图留成 `[图: 文件名]` 占位符；纯图片页（所在 spine 文件没有文字）和 pandoc 放在最前面的封面仍丢弃。Lua 先用 topdown walk 给每张图记下所在文件。报告里 `images_dropped` 的含义随之变成「丢弃的纯图片页和封面」，新增 `images_placeholder`。
2. 未标语言的代码块以 `$ ` 开头时记为 `console`（Learning Go 的 shell 示例），其余仍是 `text`。
3. 脚注：`<sup><a href="#n1">1</a></sup>` 或 `<a><sup>1</sup></a>`，编号是 1–3 位数字、单个小写字母或 `* † ‡ § ¶`，目标在别的块里，且目标块链回引用所在块或以同一编号开头 → 把目标块移出正文，引用换成 `pandoc.Note`；pandoc 加 `--reference-location=section`，定义写在所在章节末尾。`x<sup>2</sup>`、上标形式的章节链接等不满足条件的保持原样。
4. 按句子断行（semantic line breaks）：`. ! ?` 后接空格和大写/引号/非 ASCII 字符，或 `。！？` 后（可带收尾引号括号）断开。不断的地方：行内代码、公式、链接、脚注引用内部；下一行会开启新块（`#`、`-`、`1.`、`>`、`|` 等）；缩写（`Mr.`、`e.g.` …）之后；下一行以 `*` / `_` 开头（否则行首的收尾 `**` 不再闭合强调，Pro Git 里第一版就出了 3 处）。引用块和列表项的续行保留 `>` 前缀 / 缩进。拿不准就不断 —— 宁漏不错。

不按体积自动拆分：四本书都在 18 万–84 万 token，任何阈值都会把它们全拆开，而单文件 + toc 行号本来就是为按行读取设计的。真正的问题是 `--wrap=none` 让一段成一行，长行会被 Read 截断 —— 按句断行解决的正是这个。

验证：
- 合成 epub（`<a><sup>` 脚注、`<a id>` / `<div id>` 脚注、`x<sup>2</sup>` 和上标章节链接两个诱饵、带图注的无 alt 插图、纯图片页、`$ ` 块 / 纯输出块 / `language-go` 块）：两个脚注转成 `[^1]` `[^2]`，诱饵不动，插图 → `[图: fig1.gif]`，纯图片页丢弃，只有 `$ ` 块变 `console`。
- Pro Git（pandoc 3.1.3）：把改前改后的输出都用 `gfm+footnotes+east_asian_line_breaks` 读回 AST，把 SoftBreak 视同 Space 后 4253 个块逐一相同；15747 → 18774 行，最长行 1107 → 592 字符，超过 300 字符的行 698 → 28（剩下的是表格、标题和没有句末标点的长段）。`check.py` 通过。
- TPOP、Learning Go、CLRS 这轮手头没有；pandoc 3.8 也没有。golden 只更新了 progit 3.1.3，其余七行需要拿到书后在两个 pandoc 版本上复跑、看 diff、再 `--update`。

## 6. Absolute OpenBSD 第 2 版（第六轮，2026-10-09）

No Starch 的 DocBook 导出：有 `<h1>`–`<h3>`，toc 200 条；745 个 `<pre>` 都没标语言；48 个脚注是 `<sup>[<a href="#ftn.X" epub:type="noteref">3</a>]</sup>`，注释放在每章末尾的 `<div class="footnotes">`（`<br/><hr/>` + 每条一个 `<div class="footnote">`，开头再重复一次 `<sup>[3]</sup>`）；每章第一段前有同一张装饰图（无 alt）。

第五轮的改动在这本书上暴露的问题：
- 24 个 `[图: …1616079.png]` 占位符全是那张章首装饰图 → 无 alt 图片同一个文件出现 3 次及以上就当装饰丢弃。改后占位符 0。
- pandoc 自己就会把 `epub:type="noteref"` 转成脚注，但方括号和注释开头的编号留着：正文 `^(\[[^2]\])`、定义 `[^1]: ^(\[1\]) …`（main 上也是这样）→ 去掉只包着一个 Note 的上标，以及注释开头的编号。`noteref()` 也接受上标里方括号包着的链接，所以去掉 `epub:type` 后走我们自己的路径，输出逐字节相同（注释容器里剩下的 `<hr>` 一并删除）。

结果：48 个脚注都是干净的 `[^n]`；71 个块（68 个 `$ ` + 3 个本来就是 `console` 风格）标成 `console`；19624 → 25756 行，最长行 1084 → 529，超过 300 字符的行 1257 → 17；读回 AST（SoftBreak≡Space）与 main 的输出相比，去掉占位符和脚注两处有意的改动后 7553 个块逐一相同。`check.py` 通过，golden 加了 openbsd（pandoc 3.1.3）。

没做的：210 个块以 `# ` 开头，其中 208 个是 root 提示符（`# cd /usr/src`、`# pfctl …`），另外 2 个是配置文件注释（`# $OpenBSD: …`、`# Default …`）。按「宁漏不错」暂不标 `console`，见下。

## 已知缺陷 / 下一步

- TPOP 的 453 个代码块全是 `text`：源里没有语言信息。按内容猜（C / Java / awk / Perl）误判代价大，决定不做。
- 代码段落识别只抽查过若干处，没有逐个核对 453 个块。
- CLRS 的公式是图片（`alt="art"`），只能保留图片引用；伪代码里的上下标（`c<sub>ij</sub>`）在代码块里变成 `cij`。
- 脚注的目标是 `<p id="n1">` 时（calibre 常见）不转：pandoc 3.1.3 丢掉 `<p>` 的 id，目标找不到（这种链接以前就是死链）。`<a id>` 和 `<div id>` 形式可以转。
- 按句断行：中文句子之间的换行，用不带 `east_asian_line_breaks` 的渲染器看会多一个空格；以小写字母、数字开头的下一句不断；缩写表是手写的。
- 第五轮的占位符、console、脚注在 TPOP、Learning Go、CLRS 上未验证（书不在手边）。
- `# ` 开头的 root 会话（Absolute OpenBSD 有 208 个）仍是 `text`：和脚本 / 配置文件里的注释分不开。可选规则：`# ` 后第一个词是小写字母、`.`、`/` 开头且不以 `:` 结尾——在这本书上 208/210 全中、0 误判，但脚本里的小写注释（`# set up the jail`）会误判。
- 导航提升标题只处理 `<p>`；`<div>` 或 `<span>` 充当标题的书还没遇到。
- 公式需要一本真实的 MathML 书来验证；公式是图片的书无解。
- 只输出单文件，不按体积自动拆分（理由见第五轮）；真需要时可以加 `--split` 按章写多个文件（跨文件锚点要重写）。
