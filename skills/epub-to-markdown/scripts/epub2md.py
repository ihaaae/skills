#!/usr/bin/env python3
"""epub2md: convert an ePub into one agent-friendly Markdown file.

The pipeline, with the file for each step (all next to this script):
  1. preprocess.py   metadata(): title, authors, language from the OPF
  2. preprocess.py   patch_epub(): rewrite the spine documents (headings from
                     the navigation, footnote anchors, code from CSS, nested
                     lists, listings)
  3. this script     run pandoc -f epub -t gfm
  4. epub2md.lua     pandoc's Lua filter: code-block languages, admonitions,
                     cross-references, multi-line table cells, raw HTML
  5. postprocess.py  compact tables, split sentences, and prepend a YAML front
                     matter with a line-numbered table of contents

Usage: epub2md.py BOOK.epub [-o OUT.md] [--toc-depth N] [--media DIR]
Requires: pandoc on PATH.
"""
import argparse, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python3 -I leaves the script directory off sys.path
sys.dont_write_bytecode = True  # keep the installed skill directory as installed
from preprocess import metadata, patch_epub
from postprocess import postprocess, front_matter

LUA = os.path.join(HERE, "epub2md.lua")


def run_pandoc(src, media):
    with tempfile.TemporaryDirectory() as tmp:
        src, patched = patch_epub(src, tmp)
        try:
            exts = subprocess.run(["pandoc", "--list-extensions=gfm"], capture_output=True, text=True).stdout
        except FileNotFoundError:
            sys.exit("error: pandoc not found. Install it first (macOS: brew install pandoc; Debian/Ubuntu: apt install pandoc).")
        # newer pandoc defaults to GitHub's $`x`$ / ```math; force plain $x$ and $$x$$
        fmt = "gfm-raw_html+tex_math_dollars" + ("-tex_math_gfm" if "tex_math_gfm" in exts else "")
        cmd = ["pandoc", "-f", "epub", "-t", fmt,
               "--wrap=none", "--reference-location=section", "--lua-filter", LUA, src]
        if media:
            cmd += ["--extract-media", media]
        env = dict(os.environ, EPUB2MD_MEDIA="1" if media else "0")
        r = subprocess.run(cmd, capture_output=True, env=env)
        if r.returncode != 0:
            sys.exit("pandoc failed:\n" + r.stderr.decode("utf8", "replace"))
        err = r.stderr.decode("utf8", "replace")
        counts = dict(re.findall(r"^epub2md:(\w+)=(\d+)\n", err, re.M))
        err = re.sub(r"^epub2md:.*\n", "", err, flags=re.M).strip()
        if err:
            print(err, file=sys.stderr)
        extra = {**patched, **{k: int(counts.get(k, 0)) for k in ("images_dropped", "images_placeholder", "footnotes")}}
        return r.stdout.decode("utf8"), extra


def main():
    ap = argparse.ArgumentParser(description="Convert an ePub to one agent-friendly Markdown file.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="output .md path (default: next to the ePub)")
    ap.add_argument("--toc-depth", type=int, default=2, help="deepest heading level listed in the toc (default 2)")
    ap.add_argument("--media", metavar="DIR", help="also extract images into DIR (default: images are not extracted)")
    a = ap.parse_args()

    out_path = a.output or os.path.splitext(a.epub)[0] + ".md"
    meta = metadata(a.epub)
    media = a.media and os.path.abspath(a.media)
    text, extra = run_pandoc(a.epub, media)
    if media:  # image links relative to the output file, so the pair can move together
        rel = os.path.relpath(media, os.path.dirname(os.path.abspath(out_path)))
        text = text.replace("](" + media + "/", "](" + rel + "/").replace("](<" + media + "/", "](<" + rel + "/")
    body, toc, stats = postprocess(text, a.toc_depth)
    stats.update(extra)
    lines = front_matter(meta, a.epub, toc, len(body)) + body
    with open(out_path, "w", encoding="utf8") as f:
        f.write("\n".join(lines) + "\n")

    report = {"output": out_path, "bytes": os.path.getsize(out_path), "lines": len(lines),
              "toc_entries": len(toc), **stats}
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
