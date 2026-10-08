---
name: finding-feeds
description: Finds possible RSS, Atom, and JSON Feed URLs for a website or blog URL. Use when asked whether a page has a feed, to discover feeds, or to verify feed URLs.
---

# Finding Feeds

Find and verify RSS, Atom, and JSON Feed URLs for a given website, blog, essay index, or author page.

## Workflow

1. Run the bundled finder against the user-provided URL:
   ```sh
   python3 ~/.config/agents/skills/finding-feeds/scripts/find-feeds.py 'https://example.com/blog/'
   ```

2. Prefer feeds advertised by the page with `<link rel="alternate">` over guessed candidates.

3. Verify candidates by fetching them and checking both:
   - HTTP status and content type.
   - Body shape: RSS `<rss>`, Atom `<feed xmlns="http://www.w3.org/2005/Atom">`, RDF/RSS `<rdf:RDF>`, or JSON Feed `version: https://jsonfeed.org/version/...`.

4. Report the best feed URLs with status, content type, and format. Mention broken or misleading advertised feeds only if relevant.

## Script

Run:

```sh
python3 ~/.config/agents/skills/finding-feeds/scripts/find-feeds.py <url>
```

Useful options:

```sh
# Print JSON for easier downstream parsing
python3 ~/.config/agents/skills/finding-feeds/scripts/find-feeds.py --json <url>

# Increase network timeout
python3 ~/.config/agents/skills/finding-feeds/scripts/find-feeds.py --timeout 20 <url>
```

The script checks:

- Feeds explicitly advertised in page HTML.
- Common site-level and path-level aliases such as `feed.xml`, `rss.xml`, `atom.xml`, `index.xml`, `feed/`, `rss/`, and `atom/`.
- Query variants such as `?type=rss` on discovered `/feed/` endpoints.

## Reporting style

For a simple user question like “does this URL have a feed?”, answer directly:

```markdown
Yes. `<page>` advertises an Atom feed:

- Feed: <feed-url>
- HTTP status: `200`
- Content-Type: `<content-type>`
- Format: Atom

It also has an RSS alias: <rss-url>
```

If no valid feed is found, say what was checked briefly:

```markdown
I did not find a valid feed. The page does not advertise RSS/Atom/JSON Feed links, and common paths like `/feed.xml`, `/rss.xml`, and `/atom.xml` returned 404 or HTML pages.
```

## Notes

- Some sites advertise an Atom feed with `type="application/rss+xml"` or serve feeds as `text/xml`; trust the parsed body more than the declared MIME type.
- Some pretty URLs like `/feed` or `/rss` return HTML fallback pages; do not count them unless the body parses as a feed.
- Preserve the exact discovered feed URL, including query strings and unusual hosted-feed paths.
