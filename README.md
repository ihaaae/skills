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
| [formatting-latex](skills/formatting-latex) | Compile, lint, and reformat LaTeX sources |
| [progressive-learning](skills/progressive-learning) | 分层示例 + 同构练习 + 复测，逐层教会单个知识点 |
| [porting-anki-to-yanki](skills/porting-anki-to-yanki) | Convert Anki plain-text exports into yanki Markdown notes |
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
```

To add a skill, create `skills/<name>/SKILL.md` where `name` in the frontmatter matches the folder name (lowercase, hyphens).
