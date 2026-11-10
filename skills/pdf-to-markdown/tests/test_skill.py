import importlib.util
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pdf2md", SKILL / "scripts/pdf2md.py")
pdf2md = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pdf2md)

def block(kind, md="", **kw):
    return {"block_type": kind, "markdown": md, **kw}


DOC = {"children": [
    {"id": "/page/59/Page/0", "block_type": "Page", "children": [
        block("PageHeader", "14 Geometry and Complex Arithmetic"),
        block("SectionHeader", "# Chapter 1"),
        block("Figure", "![](a.jpg)\n\nA diagram showing a unit circle.\n\n$\\theta$",
              images={"a.jpg": ""}),
        block("Text", "Text with $e^{i\\theta}$."),
        block("Code", "```\n# not a heading\n```"),
    ]},
    {"id": "/page/60/Page/1", "block_type": "Page", "children": [
        block("SectionHeader", "## 1.1 Introduction"),
        block("FigureGroup", "unused", children=[
            block("Picture", "![](b.jpg)\n\nA photo of a spiral.", images={"b.jpg": ""}),
            block("Caption", "**[1.1]** A spiral."),
        ]),
        block("Equation", "$$z = x + iy$$"),
    ]},
]}


def test_skill_metadata():
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: pdf-to-markdown\n")
    assert "scripts/pdf2md.py" in text


def test_build_marks_pages_and_points_toc_at_headings(tmp_path):
    out = tmp_path / "book.md"
    text, report = pdf2md.build(DOC, title="Book", source="book.pdf", images={}, media=None, out=out)
    lines = text.split("\n")
    assert "<!-- PDF page 60 -->" in lines and "<!-- PDF page 61 -->" in lines
    assert report == {"pages": 2, "headings": 2, "math_spans": 2, "images": 0, "images_placeholder": 2}
    assert "[图: a.jpg]" in lines and "[图: b.jpg]" in lines and "**[1.1]** A spiral." in lines
    toc = [l for l in lines if l.startswith("  - [")]
    for entry in toc:  # each toc line number points at its heading
        n, title = int(entry.split("[")[1].split(",")[0]), entry.split('"')[1]
        assert lines[n - 1].lstrip("# ") == title
    assert f"lines: {len(lines) - 1}" in lines


def test_build_links_extracted_images(tmp_path):
    media = tmp_path / "media"
    text, _ = pdf2md.build(DOC, title="B", source="b.pdf", images={"a.jpg": ""},
                           media=media, out=tmp_path / "book.md")
    assert "![](media/a.jpg)" in text.split("\n")


def test_build_drops_page_headers_and_figure_text(tmp_path):
    text, _ = pdf2md.build(DOC, title="B", source="b.pdf", images={}, media=None, out=tmp_path / "b.md")
    for gone in ("14 Geometry", "A diagram", "A photo", "$\\theta$", "unused"):
        assert gone not in text
