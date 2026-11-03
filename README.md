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
| [comparing-tables](skills/comparing-tables) | Diff Excel/CSV/TSV tables with a deterministic CLI |
| [decoding-barthez](skills/decoding-barthez) | 解读「巴特兹」篮球评论中的谐音暗语与类比论证 |
| [finding-feeds](skills/finding-feeds) | Discover and verify RSS/Atom/JSON Feed URLs |
| [fleet-ocr](skills/fleet-ocr) | 通过私有 HTTP OCR API 将 PDF 识别为 Markdown/JSON/图片并渐进读取 |
| [formatting-latex](skills/formatting-latex) | Compile, lint, and reformat LaTeX sources |
| [porting-anki-to-yanki](skills/porting-anki-to-yanki) | Convert Anki plain-text exports into yanki Markdown notes |
| [spaced-repetition](skills/spaced-repetition) | 把学过的知识点映射成 Anki 卡片：atom 写在 YAML 里，同步进 collection，用 FSRS 调度；复习在 Anki 桌面版里做，被 flag 的卡片回到 YAML 修改 |
| [syncing-notes-to-anki](skills/syncing-notes-to-anki) | Author Markdown flashcards and sync them to Anki via yanki |
| [using-nowledge-mem](skills/using-nowledge-mem) | Use Nowledge Mem via remote MCP |

The learning skills (topic-graph, progressive-learning, book-graph, epub-to-markdown, writing-for-learners, writing-anki-cards) moved to [ihaaae/Learn](https://github.com/ihaaae/Learn) (`.agents/skills/`) in November 2026; their history before the move is here.

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
