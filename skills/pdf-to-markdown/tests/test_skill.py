import importlib.util
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pdf2md", SKILL / "scripts/pdf2md.py")
pdf2md = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pdf2md)

DASHES = "-" * 48
MD = f"""{{59}}{DASHES}

# Chapter 1

Text with $e^{{i\\theta}}$ and ![](_page_59_Picture_1.jpeg).

```
# not a heading
```

{{60}}{DASHES}

## 1.1 Introduction

$$z = x + iy$$
"""


def test_skill_metadata():
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: pdf-to-markdown\n")
    assert "scripts/pdf2md.py" in text


def test_build_marks_pages_and_points_toc_at_headings(tmp_path):
    out = tmp_path / "book.md"
    text, report = pdf2md.build(MD, title="Book", source="book.pdf", images={}, media=None, out=out)
    lines = text.split("\n")
    assert "<!-- PDF page 60 -->" in lines and "<!-- PDF page 61 -->" in lines
    assert report == {"pages": 2, "headings": 2, "math_spans": 2, "images": 0, "images_placeholder": 1}
    assert "[图: _page_59_Picture_1.jpeg]" in text
    toc = [l for l in lines if l.startswith("  - [")]
    for entry in toc:  # each toc line number points at its heading
        n, title = int(entry.split("[")[1].split(",")[0]), entry.split('"')[1]
        assert lines[n - 1].lstrip("# ") == title
    assert f"lines: {len(lines) - 1}" in lines


def test_build_links_extracted_images(tmp_path):
    media = tmp_path / "media"
    text, _ = pdf2md.build(MD, title="B", source="b.pdf", images={"_page_59_Picture_1.jpeg": ""},
                           media=media, out=tmp_path / "book.md")
    assert "![](media/_page_59_Picture_1.jpeg)" in text
