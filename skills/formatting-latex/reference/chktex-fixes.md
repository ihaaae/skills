# chktex Warning Fix Patterns

Apply these in priority order. Only the warnings below are worth fixing in bulk; everything else is case-by-case.

| ID | Description | Fix |
| -- | ----------- | --- |
| 1 | Command terminated with space | End the macro definition with `%`, or call as `\macro{}`. Bulk regex: `s/\\macroname /\\macroname{}/g`. |
| 2 | Missing non-breaking space before reference | Replace the space before `\ref`, `\eqref`, `\cite`, `\citet`, `\cref` with `~`. |
| 8 | Wrong length of dash | Replace narrative `--` with `---` (em-dash). Keep `--` for numeric ranges. |
| 9 | Bracket/Paren mismatch | Usually false positives in math intervals like `[0, 1)`. Suppress per-line with trailing `% chktex 9`. |
| 12 | Interword spacing | Use `\ ` after abbreviations like `e.g.`, `i.e.`, `cf.` to keep interword spacing. |
| 13 | Intersentence spacing after capital | Sentences ending in acronyms need `\@.`, e.g. `reverse SDE\@.`, `GPU\@.`. |
| 24 | Delete space for page references | When the next line is just `\label{...}`, append `%` to the previous line so no spurious space leaks in. |
| 36 | Missing space before parenthesis | Add a space (or `~`) before `(` in text mode. |

## Snippets

Add `%` before bare `\label` lines:

```python
import re, sys, pathlib
path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines(keepends=True)
out = []
for i, line in enumerate(lines):
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    if re.match(r"^\s*\\label\{[^}]+\}\s*$", nxt):
        stripped = line.rstrip("\n")
        if stripped.strip() and not stripped.lstrip().startswith("%") and not stripped.endswith("%"):
            line = stripped + "%\n"
    out.append(line)
path.write_text("".join(out))
```

Em-dash and acronym fixes (run on a copy first, review the diff):

```bash
perl -i -pe 's/(?<=\w) -- (?=\w)/---/g' main.tex
perl -i -pe 's/\b(SDE|GPU|CPU|API|ODE|MLP|CNN|RNN)\.(?=\s|$)/$1\\@./g' main.tex
```
