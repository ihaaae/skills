"""Standalone file-first OCR API client, using only Python's standard library."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward uploads or capability credentials to a redirected endpoint.
        return None


def base_url() -> str:
    base = os.environ.get("OCR_BASE_URL")
    if not base:
        path = Path(
            os.environ.get("OCR_BASE_URL_FILE", "~/.config/ocr-service/base-url")
        ).expanduser()
        try:
            base = path.read_text().strip()
        except OSError:
            raise SystemExit(
                "Configure OCR_BASE_URL or a private OCR_BASE_URL_FILE first"
            ) from None
    parts = urlsplit(base)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not re.fullmatch(r"/ocr/[A-Za-z0-9_-]{43,128}/?", parts.path)
    ):
        raise SystemExit("Invalid API base: expected HTTPS /ocr/<secret>, without /v1 suffix")
    return base.rstrip("/")


def summary(run: dict) -> dict:
    return {
        key: run[key]
        for key in ("run_id", "status", "progress", "error", "reused", "artifacts")
        if key in run
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    source = submit.add_mutually_exclusive_group(required=True)
    source.add_argument("pdf", nargs="?", type=Path)
    source.add_argument("--document-id")
    submit.add_argument("--pages", default="")
    submit.add_argument("--force", action="store_true")
    for name in ("status", "wait", "cancel", "download"):
        cmd = sub.add_parser(name)
        cmd.add_argument("run_id")
    sub.choices["wait"].add_argument("--timeout", type=int, default=120)
    download = sub.choices["download"]
    download.add_argument("artifact")
    download.add_argument("output", type=Path)
    read = sub.add_parser("read")
    read.add_argument("file", type=Path)
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--limit", type=int, default=6000)
    args = parser.parse_args()
    if args.command == "read":
        if args.offset < 0 or not 1 <= args.limit <= 12000:
            parser.error("offset >= 0 and limit within 1-12000 required")
        with args.file.open(encoding="utf-8") as file:
            remaining = args.offset
            while remaining:
                chunk = file.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
            sys.stdout.write(file.read(args.limit))
        return
    if hasattr(args, "run_id") and not re.fullmatch(r"run_[0-9a-f]{32}", args.run_id):
        parser.error("Invalid run_id")
    if args.command == "wait" and not 0 <= args.timeout <= 3600:
        parser.error("timeout must be within 0-3600 seconds")
    base = base_url()
    opener = build_opener(NoRedirects())

    def request(path, payload=None, method="GET"):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            base + "/" + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with opener.open(req, timeout=60) as response:
            # These are only metadata responses; refuse unexpectedly huge responses.
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise SystemExit("Metadata response too large; no body displayed")
            return json.loads(data)

    if args.command == "submit":
        document_id = args.document_id
        if args.pdf:
            size = args.pdf.stat().st_size
            if not 0 < size <= 100 * 1024 * 1024:
                parser.error("PDF must be nonempty and <= 100 MiB")
            with args.pdf.open("rb") as pdf:
                req = Request(
                    base + "/v1/documents?" + urlencode({"filename": args.pdf.name}),
                    data=iter(lambda: pdf.read(65536), b""),
                    method="POST",
                    headers={"Content-Type": "application/pdf", "Content-Length": str(size)},
                )
                with opener.open(req, timeout=120) as response:
                    document_id = json.loads(response.read(65536))["document_id"]
            print(json.dumps({"document_id": document_id}), flush=True)
        result = request(
            "v1/ocr", {"document_id": document_id, "pages": args.pages, "force": args.force}, "POST"
        )
    elif args.command == "download":
        name = args.artifact
        if name.startswith("/") or ".." in name.split("/") or "\\" in name:
            parser.error("artifact must be a relative artifact path")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise SystemExit("Output file already exists; choose another name")
        temporary = None
        try:
            with (
                opener.open(
                    base + f"/v1/runs/{args.run_id}/" + quote(name, safe="/"), timeout=120
                ) as response,
                tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as file,
            ):
                temporary = Path(file.name)
                size = 0
                while chunk := response.read(65536):
                    file.write(chunk)
                    size += len(chunk)
                expected = response.headers.get("Content-Length")
                if expected is not None and size != int(expected):
                    raise SystemExit("Incomplete download; output not published")
            # Publish only complete downloads; do not overwrite a concurrent writer.
            os.link(temporary, args.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(json.dumps({"file": str(args.output), "bytes": size}, ensure_ascii=False))
        return
    elif args.command == "cancel":
        result = request(f"v1/runs/{args.run_id}/cancel", method="POST")
    else:
        deadline = time.monotonic() + (args.timeout if args.command == "wait" else 0)
        while True:
            result = request(f"v1/runs/{args.run_id}")
            if (
                result["status"] in {"succeeded", "failed", "cancelled"}
                or time.monotonic() >= deadline
            ):
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    print(json.dumps(summary(result), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except HTTPError as exc:
        raise SystemExit(f"OCR HTTP {exc.code}; no response body or credential displayed") from None
    except (URLError, OSError, HTTPException, ValueError, KeyError):
        raise SystemExit(
            "OCR request/file operation failed; check configuration, status and paths"
        ) from None
