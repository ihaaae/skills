---
name: formatting-latex
description: Formats and lints LaTeX (.tex) source files via a four-stage pipeline (latexmk compile check, chktex lint, latexindent one-sentence-per-line, tex-fmt 80-column wrap). Use when asked to format, lint, clean up, fix warnings in, or pretty-print LaTeX manuscripts.
---

# Formatting LaTeX

A four-stage pipeline that compiles, lints, and reformats `.tex` files. Run the stages in order; each one assumes the previous succeeded.

## Prerequisites

Verify the required tools are on `PATH` before starting; if any are missing, stop and tell the user.

```bash
command -v latexmk pdflatex chktex latexindent tex-fmt
```

## Pipeline

Always work on the main `.tex` file the user points at (e.g. `main.tex`). Make a one-shot backup before any in-place edits:

```bash
cp main.tex main.tex.bak
```

### Stage 1 — Compile-time errors and warnings (latexmk / pdflatex)

Run the LaTeX engine and fix anything that prevents a clean build before touching style.

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

- Read the trailing summary and the `.log` file. Address every `! LaTeX Error`, `! Undefined control sequence`, `! Missing ... inserted`, and unresolved `Reference ... undefined` / `Citation ... undefined`.
- Treat the following as informational; only fix when the user asks:
  - `Package hyperref Warning: Token not allowed in a PDF string` — wrap macros in section titles with `\texorpdfstring{...}{...}`.
  - `LaTeX Warning: Float too large for page` — adjust figure/table sizing.
  - `LaTeX Warning: 'h' float specifier changed to 'ht'` — harmless.
- Re-run until `latexmk` exits 0. Do not proceed to later stages while the build is broken.

### Stage 2 — Lint with chktex

```bash
chktex main.tex 2>&1 | tee /tmp/chktex.txt
chktex main.tex 2>&1 | grep -E "^Warning" | awk -F'Warning ' '{print $2}' \
  | awk -F':' '{print $1}' | sort | uniq -c | sort -rn
```

Fix the high-signal warnings listed in [reference/chktex-fixes.md](reference/chktex-fixes.md). Skip purely stylistic noise (e.g. Warning 9 false positives in math intervals — silence individual lines with `% chktex 9`). Re-run `chktex` after edits and confirm the warning count drops.

### Stage 3 — Sentence wrapping with latexindent

Use the project-local config if present (`.latexindent-osp.yaml`), otherwise drop in [reference/latexindent-osp.yaml](reference/latexindent-osp.yaml):

```bash
test -f .latexindent-osp.yaml || cp ~/.config/agents/skills/formatting-latex/reference/latexindent-osp.yaml .latexindent-osp.yaml
latexindent -m -l=.latexindent-osp.yaml -s -w main.tex
```

- `-m` enables line-break manipulation, `-l` loads the local config, `-s` is silent, `-w` writes in place.
- After this stage every sentence sits on its own line, which makes diffs and Stage 4 wrapping deterministic.
- `latexindent` may re-indent environment bodies; if the user wants original indentation preserved, ask before continuing.

### Stage 4 — 80-column wrap with tex-fmt

```bash
tex-fmt -l 80 main.tex
```

- Lines flagged `WARN: Line cannot be wrapped` are typically atomic tokens (`\url{...}`, `\includegraphics{...}`, long `\footnote{...}`). They are safe to leave; do not break them by hand.
- If the user wants no wrapping, use `tex-fmt --nowrap main.tex`. For check-only use `tex-fmt --check main.tex`.

## Final verification

Re-compile to make sure formatting did not introduce regressions:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Report to the user: number of chktex warnings before/after, whether the final `latexmk` exited 0, and any `tex-fmt` lines that could not be wrapped.
