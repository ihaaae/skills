#!/usr/bin/env python3
"""Discover and verify possible RSS, Atom, RDF, and JSON Feed URLs for a page."""

from __future__ import annotations

import argparse
import concurrent.futures
import html.parser
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Iterable


USER_AGENT = "Mozilla/5.0 (compatible; feed-discovery/1.0)"
MAX_BODY = 2_000_000


@dataclass
class Result:
    url: str
    source: str
    ok: bool
    status: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    format: str | None = None
    title: str | None = None
    error: str | None = None


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attr = {k.lower(): v or "" for k, v in attrs}
        rel = attr.get("rel", "").lower()
        typ = attr.get("type", "").lower()
        href = attr.get("href")
        title = attr.get("title", "").lower()
        if not href:
            return
        feed_type = any(x in typ for x in ("rss", "atom", "jsonfeed", "feed+json"))
        feed_hint = any(x in (href + " " + title).lower() for x in ("rss", "atom", "feed", "jsonfeed"))
        if "feed" in rel or feed_type or ("alternate" in rel and feed_hint):
            self.links.append(attr)


def fetch(url: str, timeout: float) -> tuple[int, str | None, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(MAX_BODY)
        return response.status, response.headers.get("content-type"), response.geturl(), body


def text_preview(body: bytes) -> str:
    return body[:4096].decode("utf-8", "replace").lstrip("\ufeff\t\r\n ")


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def parse_feed(body: bytes, content_type: str | None) -> tuple[str | None, str | None]:
    preview = text_preview(body)
    ctype = (content_type or "").lower()

    if "json" in ctype or preview.startswith("{"):
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            pass
        else:
            version = str(data.get("version", "")) if isinstance(data, dict) else ""
            if version.startswith("https://jsonfeed.org/version/"):
                return "JSON Feed", data.get("title") if isinstance(data.get("title"), str) else None

    if not (preview.startswith("<") or "xml" in ctype or "rss" in ctype or "atom" in ctype):
        return None, None

    try:
        root = ET.fromstring(body)
    except Exception:
        return None, None

    name = local_name(root.tag).lower()
    if name == "rss":
        channel = root.find("channel")
        title = channel.findtext("title") if channel is not None else None
        return "RSS", title
    if name == "feed":
        title = root.findtext("{http://www.w3.org/2005/Atom}title") or root.findtext("title")
        return "Atom", title
    if name == "rdf":
        title = None
        for elem in root.iter():
            if local_name(elem.tag).lower() == "title" and elem.text:
                title = elem.text
                break
        return "RDF/RSS", title

    return None, None


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) else "https://" + url)
    if not parsed.path:
        parsed = parsed._replace(path="/")
    return urllib.parse.urlunparse(parsed)


def html_feed_links(page_url: str, html_text: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(html_text)
    out: list[tuple[str, str]] = []
    for link in parser.links:
        href = urllib.parse.urljoin(page_url, link["href"])
        typ = link.get("type", "")
        title = link.get("title", "")
        source = "advertised"
        if title or typ:
            source += f" ({'; '.join(x for x in [typ, title] if x)})"
        out.append((href, source))
    return out


def candidate_urls(page_url: str) -> list[tuple[str, str]]:
    parsed = urllib.parse.urlparse(page_url)
    root = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))
    path = parsed.path if parsed.path.endswith("/") else parsed.path.rsplit("/", 1)[0] + "/"
    path_base = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    names = ["feed.xml", "rss.xml", "atom.xml", "index.xml", "feed/", "rss/", "atom/", "rss.rdf", "feed"]
    candidates: list[tuple[str, str]] = []
    for base, label in ((path_base, "path guess"), (root, "site guess")):
        for name in names:
            candidates.append((urllib.parse.urljoin(base, name), label))
    candidates.extend([
        (urllib.parse.urljoin(root, "feed/?type=rss"), "site guess"),
        (urllib.parse.urljoin(root, "feed.xml?type=rss"), "site guess"),
    ])
    return candidates


def unique(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for url, source in items:
        if url in seen:
            continue
        seen.add(url)
        out.append((url, source))
    return out


def check(url: str, source: str, timeout: float) -> Result:
    try:
        status, content_type, final_url, body = fetch(url, timeout)
    except urllib.error.HTTPError as e:
        return Result(url=url, source=source, ok=False, status=e.code, error=str(e))
    except Exception as e:
        return Result(url=url, source=source, ok=False, error=f"{type(e).__name__}: {e}")

    fmt, title = parse_feed(body, content_type)
    return Result(
        url=url,
        source=source,
        ok=fmt is not None,
        status=status,
        content_type=content_type,
        final_url=final_url,
        format=fmt,
        title=title,
        error=None if fmt else "Fetched, but body did not parse as a feed",
    )


def discover(url: str, timeout: float) -> tuple[Result, list[Result]]:
    page_url = normalize_url(url)
    page = check(page_url, "page", timeout)
    links: list[tuple[str, str]] = []
    if page.status and page.status < 400:
        try:
            _, _, final_url, body = fetch(page_url, timeout)
            html_text = body.decode("utf-8", "replace")
            links.extend(html_feed_links(final_url, html_text))
            page.final_url = final_url
        except Exception:
            pass

    candidates = unique(links + candidate_urls(page.final_url or page_url))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(check, candidate, source, timeout) for candidate, source in candidates]
        results = [future.result() for future in futures]
    return page, results


def print_text(page: Result, results: list[Result]) -> None:
    print(f"Page: {page.url}")
    if page.final_url and page.final_url != page.url:
        print(f"Final page URL: {page.final_url}")
    print()

    valid = [r for r in results if r.ok]
    if valid:
        print("Valid feeds:")
        for r in valid:
            print(f"- {r.url}")
            print(f"  source: {r.source}")
            print(f"  status: {r.status}")
            print(f"  content-type: {r.content_type}")
            print(f"  format: {r.format}")
            if r.title:
                print(f"  title: {r.title}")
            if r.final_url and r.final_url != r.url:
                print(f"  final-url: {r.final_url}")
    else:
        print("No valid feeds found.")

    advertised = [r for r in results if r.source.startswith("advertised") and not r.ok]
    if advertised:
        print("\nAdvertised but invalid/unreachable:")
        for r in advertised:
            detail = f"status {r.status}" if r.status is not None else r.error
            print(f"- {r.url} ({detail})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Page URL to inspect")
    parser.add_argument("--timeout", type=float, default=8.0, help="Network timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    page, results = discover(args.url, args.timeout)
    if args.json:
        print(json.dumps({"page": asdict(page), "results": [asdict(r) for r in results]}, indent=2, ensure_ascii=False))
    else:
        print_text(page, results)
    return 0 if any(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
