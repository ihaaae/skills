#!/usr/bin/env python3
"""Convert a PDF into one Markdown file for an agent to read, with Datalab's hosted Marker API.

    pdf2md.py BOOK.pdf -o BOOK.md [--pages 0-9,20] [--mode accurate|balanced|fast] [--media DIR]

The API key comes from $DATALAB_API_KEY or $DATALAB (the name of the Amp secret), or the file ~/.config/datalab/api-key (one line, mode 0600).
It is sent only in the X-API-Key header and never printed. Standard library only.

Output: YAML front matter (title, source, pages, lines, toc of [line, level, title]), then the
Markdown, with a `<!-- PDF page N -->` line (1-based PDF page) before each page. A JSON report goes
to stderr.

The Markdown is joined from Datalab's JSON blocks, so that each figure keeps only its image: Datalab
writes its own description of every figure (not the book's caption, which is a separate block) and
lists the figure's labels as loose lines. Page headers and footers are dropped.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://www.datalab.to/api/v1/convert"
KEY_FILE = Path.home() / ".config" / "datalab" / "api-key"
POLL_SECONDS, POLL_LIMIT = 3, 1200  # up to an hour

SKIP_BLOCKS = {"PageHeader", "PageFooter"}
GROUP_BLOCKS = {"FigureGroup", "PictureGroup"}  # a figure with its caption; keep the caption
FIGURE_BLOCKS = {"Figure", "Picture"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$\n]+\$", re.S)


def api_key() -> str:
    key = (os.environ.get("DATALAB_API_KEY") or os.environ.get("DATALAB") or "").strip()
    if not key and KEY_FILE.is_file():
        key = KEY_FILE.read_text().strip()
    if not key:
        raise SystemExit(f"no Datalab API key: set DATALAB_API_KEY (or DATALAB) or write it to {KEY_FILE}")
    return key


def multipart(fields: dict[str, str], file: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
               f"Content-Type: application/pdf\r\n\r\n".encode())
    out.append(file.read_bytes())
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def request(url: str, key: str | None, data: bytes | None = None, ctype: str | None = None) -> dict:
    # Datalab is behind Cloudflare, which rejects urllib's default User-Agent (HTTP 403, error code 1010).
    headers = {"User-Agent": "pdf-to-markdown/1.0"} | ({"X-API-Key": key} if key else {})
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data, headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # Retry rate limits and server errors on polls; never replay a submission.
            if data is not None or e.code not in (429, 500, 502, 503, 504) or attempt == 4:
                body = e.read().decode(errors="replace")[:500]
                raise SystemExit(f"Datalab returned HTTP {e.code}: {body}")
            time.sleep(2**attempt * 3)


def convert(pdf: Path, key: str, mode: str, pages: str | None) -> dict:
    fields = {"output_format": "json", "include_markdown_in_chunks": "true", "mode": mode,
              "disable_image_captions": "true"}
    if pages:
        fields["page_range"] = pages
    body, ctype = multipart(fields, pdf)
    sub = request(API, key, body, ctype)
    if sub.get("success") is False:
        raise SystemExit(f"Datalab refused the request: {sub.get('error')}")
    check = sub["request_check_url"]
    for _ in range(POLL_LIMIT):
        time.sleep(POLL_SECONDS)
        res = request(check, key)
        if res.get("status") == "failed":
            raise SystemExit(f"conversion failed: {res.get('error')}")
        if res.get("status") == "complete":
            if res.get("result_url"):  # EU results: download without the key, keep the poll's non-null fields
                res = {**request(res["result_url"], None), **{k: v for k, v in res.items() if v is not None}}
            if res.get("success") is False:
                raise SystemExit(f"conversion failed: {res.get('error')}")
            return res
    raise SystemExit(f"still processing after {POLL_SECONDS * POLL_LIMIT} s; poll {check} later")


def block_markdown(block: dict) -> list[str]:
    kind = block["block_type"]
    if kind in SKIP_BLOCKS:
        return []
    if kind in GROUP_BLOCKS and block.get("children"):
        return [s for child in block["children"] for s in block_markdown(child)]
    if kind in FIGURE_BLOCKS:
        return [f"![]({name})" for name in block.get("images") or {}]
    md = (block.get("markdown") or "").strip()
    return [md] if md else []


def build(doc: dict, *, title: str, source: str, images: dict[str, str], media: Path | None,
          out: Path) -> tuple[str, dict]:
    """The output file and the report, from the API's JSON document (one child block per page)."""
    parts = []
    for page in doc["children"]:
        parts.append(f"<!-- PDF page {int(page['id'].split('/')[2]) + 1} -->")  # id: /page/<0-based>/Page/...
        parts += [s for block in page.get("children") or [] for s in block_markdown(block)]
    body = "\n\n".join(parts)
    pages = len(doc["children"])

    def image(m):
        name = Path(m.group(2)).name
        if media is not None and name in images:
            return f"![{m.group(1)}]({os.path.relpath(media / name, out.parent)})"
        return f"[图: {name}]"
    body = IMAGE_RE.sub(image, body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"

    lines = body.split("\n")
    toc, fenced = [], False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced and (m := HEADING_RE.match(line)):
            toc.append((i, len(m.group(1)), m.group(2)))
    # The front matter has a fixed number of lines (one per toc entry), so body line numbers can be shifted by it.
    head_len = 7 + len(toc)
    total = head_len + len(lines) - 1
    head = ["---", f"title: {json.dumps(title, ensure_ascii=False)}", f"source: {json.dumps(source, ensure_ascii=False)}",
            f"pages: {pages}", f"lines: {total}", "toc:" if toc else "toc: []"]
    head += [f"  - [{head_len + i + 1}, {lv}, {json.dumps(t, ensure_ascii=False)}]" for i, lv, t in toc]
    head.append("---")
    assert len(head) == head_len
    report = {"pages": pages, "headings": len(toc), "math_spans": len(MATH_RE.findall(body)),
              "images": len(images), "images_placeholder": body.count("[图: ")}
    return "\n".join(head) + "\n" + body, report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdf", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--pages", help="0-based PDF pages, e.g. 0-9,20 (default: all)")
    p.add_argument("--mode", choices=["fast", "balanced", "accurate"], default="accurate",
                   help="Datalab mode; accurate suits scanned books and formulas (default)")
    p.add_argument("--media", type=Path, help="also write the extracted images to DIR")
    args = p.parse_args(argv)
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; not overwriting")
    res = convert(args.pdf, api_key(), args.mode, args.pages)
    images = res.get("images") or {}
    if args.media:
        args.media.mkdir(parents=True, exist_ok=True)
        for name, data in images.items():
            (args.media / Path(name).name).write_bytes(base64.b64decode(data))
    text, report = build(res.get("json") or {"children": []}, title=args.pdf.stem, source=args.pdf.name,
                         images=images, media=args.media, out=args.output)
    args.output.write_text(text, encoding="utf-8")
    meta = res.get("metadata") or {}
    report |= {"mode": args.mode, "parse_quality_score": res.get("parse_quality_score"),
               "failed_pages": meta.get("failed_pages"), "cost": res.get("cost_breakdown"),
               "output": str(args.output)}
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
