# skills

My personal agent skills, installable with [`npx skills`](https://github.com/vercel-labs/skills).

## Install

```bash
# list available skills
npx skills add ihaaae/skills --list

# install all skills globally for Claude Code
npx skills add ihaaae/skills -a claude-code -g -y

# install specific skills
npx skills add ihaaae/skills --skill finding-feeds --skill formatting-latex -g
```

Update / remove:

```bash
npx skills update -g -y
npx skills remove ihaaae/skills -g
```

## Skills

| Skill | Description |
| --- | --- |
| [anki-review](skills/anki-review) | Batch Anki review workflow |
| [book-graph](skills/book-graph) | 以一本书为骨架建学习图谱：章节 → 节点映射、覆盖检查、深度、切分规则 |
| [comparing-tables](skills/comparing-tables) | Diff Excel/CSV/TSV tables with a deterministic CLI |
| [decoding-barthez](skills/decoding-barthez) | 解读「巴特兹」篮球评论中的谐音暗语与类比论证 |
| [epub-to-markdown](skills/epub-to-markdown) | 把 ePub 转成带行号目录、给 Agent 读的单个 Markdown 文件 |
| [finding-feeds](skills/finding-feeds) | Discover and verify RSS/Atom/JSON Feed URLs |
| [fleet-ocr](skills/fleet-ocr) | 通过私有 HTTP OCR API 将 PDF 识别为 Markdown/JSON/图片并渐进读取 |
| [formatting-latex](skills/formatting-latex) | Compile, lint, and reformat LaTeX sources |
| [porting-anki-to-yanki](skills/porting-anki-to-yanki) | Convert Anki plain-text exports into yanki Markdown notes |
| [progressive-learning](skills/progressive-learning) | 把一个 25 分钟的知识点写成 topic 文档（分层示例 + 同构练习），再按文档逐轮教会 |
| [spaced-repetition](skills/spaced-repetition) | 把学过的知识写成 atom，用 Anki 的 collection 格式和 FSRS 调度做间隔重复（不用 Anki 软件） |
| [syncing-notes-to-anki](skills/syncing-notes-to-anki) | Author Markdown flashcards and sync them to Anki via yanki |
| [topic-graph](skills/topic-graph) | Plan and track learning a subject as a prerequisite graph of small nodes |
| [using-nowledge-mem](skills/using-nowledge-mem) | Use Nowledge Mem via remote MCP |

## Layout

```
skills/
  <skill-name>/
    SKILL.md        # required: frontmatter with `name` and `description`
    scripts/        # optional helper scripts
    references/     # optional reference docs
dev/
  <skill-name>/     # optional dev-only files (benchmarks, experiment logs); not installed
```

To add a skill, create `skills/<name>/SKILL.md` where `name` in the frontmatter matches the folder name (lowercase, hyphens).
