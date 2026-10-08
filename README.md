# epub2md

把 ePub 转成给 Agent 读的单个 Markdown 文件：带行号目录的 YAML front matter、带语言的围栏代码块、`$` 公式、紧凑表格、可解析的书内链接，其余样式全部丢弃。

## 安装

依赖 `pandoc` ≥ 3.0 和 `python3`（只用标准库）：

```bash
brew install pandoc
```

skill 在 `.claude/skills/epub-to-markdown/`。在这个目录里打开 Claude Code 就能用（项目级 skill）。想在所有项目里用，链接到个人 skill 目录：

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/.claude/skills/epub-to-markdown" ~/.claude/skills/epub-to-markdown
```

## 直接用脚本

```bash
python3 .claude/skills/epub-to-markdown/scripts/epub2md.py BOOK.epub -o BOOK.md [--toc-depth N] [--media DIR]
```

stderr 输出一份 JSON 报告，字段含义见 SKILL.md 的「检查」一节。

## 实验

```bash
cp your-books/*.epub books/
bench/run.sh          # 我们 vs pandoc / markitdown / books-for-bots 的对比表 + 不变量检查
bench/regress.sh      # 参考书的输出哈希回归
```

实验记录和结论在 `docs/experiments.md`，给 Claude Code 的项目说明在 `CLAUDE.md`。
