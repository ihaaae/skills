# epub2md

把 ePub 转成**给 Agent 读**的单个 Markdown 文件，并作为 Claude Code skill 使用。

## 目标与取舍

- 读者是 Agent，不是人：追求 token 效率和可导航性，不追求版式还原。
- 只需要：标题、段落、列表、紧凑表格、带语言的围栏代码块、`$` / `$$` 公式。其余样式一律丢弃。
- 能按章读取比压缩率更重要：输出开头的 YAML `toc` 给出每个标题的绝对行号。
- 不自己写 HTML 解析器：pandoc 负责解析，我们只做 Lua filter + Python 前后处理。

## 目录

```
.claude/skills/epub-to-markdown/
  SKILL.md               skill 说明（给 Agent 看的使用和检查规则）
  scripts/epub2md.py     转换器本体：Python 前处理 + 内嵌 Lua filter + 后处理
bench/
  run.sh                 在 books/ 里所有书上跑我们和三个 baseline，输出对比表
  metrics.py             对比指标（见文件头注释）
  check.py               我们输出的不变量检查：toc 行号、lines 总数、内部链接、残留 HTML
  regress.sh             回归测试：按 epub 的 sha256 匹配参考书，比对输出哈希
  golden.tsv             参考输出哈希：epub sha256 / 标签 / pandoc 版本 / 输出 sha256
docs/experiments.md      完整实验记录、对比数据、发现的 bug 和已知缺陷
books/                   放测试用的 .epub（不进 git）
out/                     bench 输出（不进 git）
```

## epub2md.py 的流水线

1. `metadata()`：从 OPF 读 title / authors / language，检查 DRM。
2. `promote_headings()`：书里没有 `<h1>`–`<h6>` 时，用导航（EPUB3 nav 优先，退回 EPUB2 NCX）把目标 `<p>` 改成 `<hN>`，写一份临时 epub 交给 pandoc。只改「整个文件没有标题标签」的 spine 文件，且段落文本必须和导航标题互相包含、长度 ≤ 200。
3. pandoc：`-f epub -t gfm-raw_html+tex_math_dollars --wrap=none`，新版 pandoc 再加 `-tex_math_gfm`。
4. Lua filter（三遍）：
   - pass 1，按文档顺序：记录每个元素 id 属于哪个标题（slug），以及哪些 spine 文件有文字。
   - pass 2：代码块语言、`<tt>` 段落 → 代码块、`<aside>`/提示框 → 引用块、交叉链接改写成 `#slug`、bold/italic class → 强调、嵌套引用压平、无 alt 图片丢弃。
   - pass 3：删掉所有残留的 raw HTML 和空段落。
5. `postprocess()`：压缩表格、合并空行、统计、收集标题；`front_matter()` 计算行号偏移。

## 改动时的规则

- 每次改转换器后跑 `bench/regress.sh`。参考书的输出哈希应该不变；如果是有意的改进，先看 diff，确认后再 `bench/regress.sh --update`，并在 `docs/experiments.md` 里记一笔。
- 改动要对 pandoc 3.1.x 和 3.8+ 都成立：两者的 id 命名不同（`file.xhtml#frag` vs `file.xhtml_frag`），数学默认输出也不同。用 `PATH=/path/to/other/pandoc/bin:$PATH bench/regress.sh` 验证另一个版本。
- `bench/check.py` 对我们的输出必须全部 ok。
- 启发式规则（代码段落识别、导航提升标题）宁可漏判也不要误判：误判会把正文变成代码或标题，比漏判更伤。
- 参考书：Pro Git 中文版（有 `<pre class="language-*">`、`<aside>`、表格、大量交叉引用）和 The Practice of Programming（calibre 转换：无标题标签、代码是 `<tt>`+`<br>`、不间断空格缩进、纯图片页）。书本身不在仓库里，sha256 见 `bench/golden.tsv`。

## 已知缺陷 / 下一步

见 `docs/experiments.md` 末尾。
