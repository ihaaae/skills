# epub2md

把 ePub 转成**给 Agent 读**的单个 Markdown 文件，并作为 Claude Code skill 使用。

## 目标与取舍

- 读者是 Agent，不是人：追求 token 效率和可导航性，不追求版式还原。
- 只需要：标题、段落、列表、紧凑表格、带语言的围栏代码块、`$` / `$$` 公式。其余样式一律丢弃。
- 能按章读取比压缩率更重要：输出开头的 YAML `toc` 给出每个标题的绝对行号。
- 不自己写 HTML 解析器：pandoc 负责解析，我们只做 Lua filter + Python 前后处理。

## 目录

路径相对于本目录 `dev/epub-to-markdown/`。

```
../../skills/epub-to-markdown/    （skill 本体，npx skills 安装的就是这个目录）
  SKILL.md               skill 说明（给 Agent 看的使用和检查规则）
  scripts/epub2md.py     转换器本体：Python 前处理 + 内嵌 Lua filter + 后处理
bench/
  run.sh                 在 books/ 里所有书上跑我们和三个 baseline，输出对比表
  metrics.py             对比指标（见文件头注释）
  check.py               我们输出的不变量检查：toc 行号、lines 总数、内部链接、残留 HTML
  regress.sh             回归测试：按 epub 的 sha256 匹配参考书，比对输出哈希
  golden.tsv             参考输出哈希：epub sha256 / 标签 / pandoc 版本 / 输出 sha256
docs/experiments.md      完整实验记录、对比数据、发现的 bug 和已知缺陷
books/                   放测试用的 .epub；只有允许再分发的 progit.epub 进 git（见 books/README.md）
samples/progit.md        Pro Git 的转换结果样例（pandoc 3.1.3）
out/                     bench 输出（不进 git）
```

## epub2md.py 的流水线

1. `metadata()`：从 OPF 读 title / authors / language，检查 DRM。
2. `patch_epub()`：在 pandoc 之前改写 spine 里的 xhtml，写一份临时 epub。
   - `listing_tables()`：第一列是连续行号（可以不从 1 开始）、每行 2–3 格的表格 → `<pre>`，缩进取 `css_margins()` 算出的首行缩进（`margin-left` + `text-indent`），级差取相邻缩进值的最小差。
   - `promote_headings()`：书里没有 `<h1>`–`<h6>` 时，用导航（EPUB3 nav 优先，退回 EPUB2 NCX）把目标 `<p>` 改成 `<hN>`。只改「整个文件没有标题标签」的 spine 文件，且段落文本必须和导航标题互相包含、长度 ≤ 200；导航只指向文件（没有 `#frag`）时，在文件开头前 3 个有文字的段落里找。
3. pandoc：`-f epub -t gfm-raw_html+tex_math_dollars --wrap=none`，新版 pandoc 再加 `-tex_math_gfm`。
4. Lua filter（先把 Str 里的不间断空格换成普通空格，再四遍）：
   - pass 0：按 `<section>` / `data-type` 章节的嵌套深度重定标题级别（只降不升；`<section>` 和紧挨着的 `<div class="sect1">` 只算一层）。
   - pass 1，按文档顺序：记录每个元素 id 属于哪个标题（slug），以及哪些 spine 文件有文字。提示框、侧栏、例子、插图里的标题不算节，里面的 id 归到外层的节。
   - pass 2：代码块语言（`data-code-language` 属性或 class）、`<tt>` 段落 → 代码块、`<aside>`/提示框/侧栏 → 引用块（框内标题并入标签）、例子/插图标题 → 粗体段落、交叉链接改写成 `#slug`、bold/italic class → 强调、嵌套引用压平、无 alt 图片丢弃。
   - pass 3：删掉所有残留的 raw HTML 和空段落。
5. `postprocess()`：压缩表格、合并空行、合并索引里的重复链接、合并标题里的连续空格、统计、收集标题；`front_matter()` 计算行号偏移。

## 改动时的规则

- 每次改转换器后跑 `bench/regress.sh`。它只重跑 golden 里有的书；`out/` 里其他书的输出不会更新，要用 `bench/run.sh BOOK` 重跑。参考书的输出哈希应该不变；如果是有意的改进，先看 diff，确认后再 `bench/regress.sh --update`，并在 `docs/experiments.md` 里记一笔。
- 改动要对 pandoc 3.1.x 和 3.8+ 都成立：两者的 id 命名不同（`file.xhtml#frag` vs `file.xhtml_frag`），数学默认输出也不同。用 `PATH=/path/to/other/pandoc/bin:$PATH bench/regress.sh` 验证另一个版本。
- `bench/check.py` 对我们的输出必须全部 ok。
- 启发式规则（代码段落识别、导航提升标题）宁可漏判也不要误判：误判会把正文变成代码或标题，比漏判更伤。
- 参考书：Pro Git 中文版（有 `<pre class="language-*">`、`<aside>`、表格、大量交叉引用；可从 progit2-zh 的 GitHub release 下载 `progit.epub`）、The Practice of Programming（calibre 转换：无标题标签、代码是 `<tt>`+`<br>`、不间断空格缩进、纯图片页）、Learning Go 第 2 版（O'Reilly HTMLBook：所有层级都用 `<h1>`、`data-code-language`、`data-type` 提示框、书末索引）和 Introduction to Algorithms 第 4 版（CLRS：没有标题标签、伪代码是带行号的表格、公式全是图片）。书本身不在仓库里，sha256 见 `bench/golden.tsv`。

## 已知缺陷 / 下一步

见 `docs/experiments.md` 末尾。
