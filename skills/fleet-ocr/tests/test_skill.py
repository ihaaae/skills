from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ocr_skill", SKILL / "scripts/ocr.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
RUN = "run_" + "a" * 32


@pytest.fixture(autouse=True)
def credential(monkeypatch):
    monkeypatch.setenv("OCR_BASE_URL", "https://example.test/ocr/" + "t" * 43)


def test_skill_metadata():
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: fleet-ocr\n")
    assert "description:" in text.split("---")[1]
    assert len(text.splitlines()) < 500
    assert "scripts/ocr.py" in text


def test_read_bounds_unicode_without_network(tmp_path, monkeypatch, capsys):
    path = tmp_path / "text.md"
    path.write_text("中文abcdef", encoding="utf-8")
    monkeypatch.delenv("OCR_BASE_URL")
    monkeypatch.setattr(sys, "argv", ["ocr", "read", str(path), "--offset", "1", "--limit", "3"])
    client.main()
    assert capsys.readouterr().out == "文ab"


def test_rejects_insecure_base(monkeypatch):
    monkeypatch.setenv("OCR_BASE_URL", "http://example.test/ocr/" + "t" * 43)
    with pytest.raises(SystemExit, match="expected HTTPS"):
        client.base_url()


def test_reads_base_url_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OCR_BASE_URL")
    path = tmp_path / "base-url"
    path.write_text("https://example.test/ocr/" + "f" * 43 + "\n")
    monkeypatch.setenv("OCR_BASE_URL_FILE", str(path))
    assert client.base_url() == "https://example.test/ocr/" + "f" * 43


@pytest.mark.parametrize("incomplete", [False, True])
def test_download_atomic_and_file_only(tmp_path, monkeypatch, capsys, incomplete):
    response = io.BytesIO(b"Recognized document body")
    response.headers = {"Content-Length": str(len(response.getvalue()) + int(incomplete))}

    class Opener:
        def open(self, *args, **kwargs):
            return response

    monkeypatch.setattr(client, "build_opener", lambda *args: Opener())
    output = tmp_path / "output.md"
    monkeypatch.setattr(sys, "argv", ["ocr", "download", RUN, "document.md", str(output)])
    if incomplete:
        with pytest.raises(SystemExit, match="Incomplete download"):
            client.main()
        assert not list(tmp_path.iterdir())
    else:
        client.main()
        assert output.read_bytes() == b"Recognized document body"
        printed = capsys.readouterr().out
        assert "Recognized" not in printed
        assert json.loads(printed)["bytes"] == output.stat().st_size
        with pytest.raises(SystemExit, match="already exists"):
            client.main()


def test_submit_existing_document_does_not_upload(monkeypatch, capsys):
    requests = []

    class Opener:
        def open(self, req, **kwargs):
            requests.append(req)
            return io.BytesIO(json.dumps({"run_id": RUN, "status": "queued"}).encode())

    monkeypatch.setattr(client, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(sys, "argv", ["ocr", "submit", "--document-id", "existing", "--pages", "8"])
    client.main()
    assert len(requests) == 1
    assert json.loads(requests[0].data) == {"document_id": "existing", "pages": "8", "force": False}
    assert "https://" not in capsys.readouterr().out
