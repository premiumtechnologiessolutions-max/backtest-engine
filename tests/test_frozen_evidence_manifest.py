"""Synthetic file inventory tests; no raw XAUUSD quotes or trade records."""
import json

import pytest

from scripts.frozen_evidence_manifest import (
    ANNUAL_FILES, MANIFEST_NAME, verify_evidence_manifest, write_evidence_manifest,
)

SHA = "a" * 64


def _evidence(root):
    (root / "2012").mkdir(parents=True)
    (root / "frozen_sensitivity_summary.json").write_text('{"synthetic":true}')
    for name in ANNUAL_FILES:
        (root / "2012" / name).write_text(f"synthetic:{name}")
    return root


def test_manifest_roundtrip_and_canonical_file_order(tmp_path):
    root = _evidence(tmp_path / "reports")
    written = write_evidence_manifest(root, [2012], SHA)
    assert written == verify_evidence_manifest(
        root, expected_years=[2012], expected_source_sha=SHA)
    assert len(written["files"]) == 7
    assert [row["path"] for row in written["files"]] == sorted(
        row["path"] for row in written["files"])


def test_same_size_tampering_is_detected(tmp_path):
    root = _evidence(tmp_path / "reports")
    write_evidence_manifest(root, [2012], SHA)
    path = root / "2012" / "trades.csv"
    original = path.read_text()
    path.write_text(original.replace("synthetic", "SYNTHETIC"))
    with pytest.raises(ValueError, match="changed after publication"):
        verify_evidence_manifest(root)


def test_unlisted_extra_file_is_detected(tmp_path):
    root = _evidence(tmp_path / "reports")
    write_evidence_manifest(root, [2012], SHA)
    (root / "2012" / "extra.csv").write_text("surprise")
    with pytest.raises(ValueError, match="inventory differs"):
        verify_evidence_manifest(root)


def test_missing_required_report_is_detected_before_publication(tmp_path):
    root = _evidence(tmp_path / "reports")
    (root / "2012" / "weekly.csv").unlink()
    with pytest.raises(ValueError, match="missing required"):
        write_evidence_manifest(root, [2012], SHA)
    assert not (root / MANIFEST_NAME).exists()


def test_symlink_in_evidence_is_rejected(tmp_path):
    root = _evidence(tmp_path / "reports")
    (root / "2012" / "alias.csv").symlink_to(root / "2012" / "trades.csv")
    with pytest.raises(ValueError, match="symlinks"):
        write_evidence_manifest(root, [2012], SHA)


def test_manifest_path_traversal_rejected(tmp_path):
    root = _evidence(tmp_path / "reports")
    write_evidence_manifest(root, [2012], SHA)
    path = root / MANIFEST_NAME
    data = json.loads(path.read_text())
    data["files"][0]["path"] = "../outside.txt"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unsafe path"):
        verify_evidence_manifest(root)


def test_manifest_wrong_source_and_year_rejected(tmp_path):
    root = _evidence(tmp_path / "reports")
    write_evidence_manifest(root, [2012], SHA)
    with pytest.raises(ValueError, match="source identity"):
        verify_evidence_manifest(root, expected_source_sha="b" * 64)
    with pytest.raises(ValueError, match="selected years"):
        verify_evidence_manifest(root, expected_years=[2013])


@pytest.mark.parametrize("bad_years", [[2012, 2012], [True], [2012.0], []])
def test_invalid_year_selection_rejected(tmp_path, bad_years):
    root = _evidence(tmp_path / "reports")
    with pytest.raises(ValueError, match="distinct integer"):
        write_evidence_manifest(root, bad_years, SHA)
