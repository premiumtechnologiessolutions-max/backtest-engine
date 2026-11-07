"""Synthetic filesystem regressions for private offline terminal export."""
import os

import pytest
from scripts.research_terminal_export import write_private_html


def test_atomic_export_creates_owner_only_file(tmp_path):
    out = tmp_path / "reports" / "quant.html"
    write_private_html(out, "<html>queue-private</html>")
    assert out.read_text() == "<html>queue-private</html>"
    if os.name == "posix":
        assert out.stat().st_mode & 0o077 == 0
    write_private_html(out, "<html>updated</html>")
    assert out.read_text() == "<html>updated</html>"
    assert not list(out.parent.glob(".nrfx-terminal-*"))


def test_existing_symlink_cannot_overwrite_target(tmp_path):
    target = tmp_path / "private.txt"
    target.write_text("KEEP")
    link = tmp_path / "terminal.html"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlinked export destination"):
        write_private_html(link, "leak")
    assert target.read_text() == "KEEP"


def test_symlinked_parent_is_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked export parent"):
        write_private_html(link / "terminal.html", "leak")
    assert not list(target.iterdir())


def test_existing_hardlink_is_rejected(tmp_path):
    target = tmp_path / "original.html"
    target.write_text("KEEP")
    out = tmp_path / "terminal.html"
    os.link(target, out)
    with pytest.raises(ValueError, match="hardlinked"):
        write_private_html(out, "leak")
    assert target.read_text() == "KEEP"


def test_atomic_failure_preserves_previous_file(tmp_path, monkeypatch):
    from scripts import research_terminal_export as export
    out = tmp_path / "terminal.html"
    out.write_text("PREVIOUS")

    def fail_replace(*args):
        raise OSError("synthetic rename failure")

    monkeypatch.setattr(export.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic"):
        write_private_html(out, "NEW")
    assert out.read_text() == "PREVIOUS"
    assert not list(tmp_path.glob(".nrfx-terminal-*"))


@pytest.mark.parametrize("name", ["registry.json", "results.csv", "report", "README.md"])
def test_non_html_destination_rejected(tmp_path, name):
    with pytest.raises(ValueError, match=".html"):
        write_private_html(tmp_path / name, "html")
    assert not (tmp_path / name).exists()


def test_terminal_cli_exports_private_html(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    monkeypatch.setattr(terminal, "dashboard_model", lambda _: {
        "rows": [], "specifications": 0, "passing_24_of_24": 0,
    })
    monkeypatch.setattr(terminal, "render_html", lambda _: "<html>safe</html>")
    out = tmp_path / "terminal.html"
    assert terminal.main(["--registry", str(registry), "--out", str(out)]) == 0
    assert out.read_text() == "<html>safe</html>"
    if os.name == "posix":
        assert out.stat().st_mode & 0o077 == 0
