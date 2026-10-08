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

## 已知缺陷 / 下一步

- TPOP 的 453 个代码块全是 `text`：源里没有语言信息。可以考虑按内容猜（C / Java / awk / Perl），但误判代价不小。
- TPOP 385 张图全部没有 alt，默认丢弃；其中约 25 张是真插图。可以考虑：不解压时把无 alt 的插图保留成占位符（`[图: 文件名]`），纯图片页仍丢弃。
- 代码段落识别只抽查过若干处，没有逐个核对 453 个块。
- 导航提升标题只处理 `<p>`；`<div>` 或 `<span>` 充当标题的书还没遇到。
- 公式需要一本真实的 MathML 书来验证；公式是图片的书无解。
- 只输出单文件；需要时可以加 `--split` 按章写多个文件（跨文件锚点要重写）。
