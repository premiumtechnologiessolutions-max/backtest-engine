"""Synthetic prepublication evidence allowlist: never package incidental inputs.

No private Gold data, market quotes, or historical trade results.
"""
import pytest

from scripts.frozen_evidence_manifest import (
    ANNUAL_FILES, MANIFEST_NAME, write_evidence_manifest,
)

SOURCE_SHA = "a" * 64


def _staged(root):
    (root / "2012").mkdir(parents=True)
    (root / "frozen_sensitivity_summary.json").write_text('{"synthetic": true}')
    for name in ANNUAL_FILES:
        (root / "2012" / name).write_text(f"synthetic:{name}")
    return root


@pytest.mark.parametrize("extra_path", [
    "Gold data.zip",               # Accidental private raw input
    "2012/raw_ticks.csv",          # Incidental raw quote export
    "2017/summary.json",          # Year not in frozen selection
    "notes.txt",                  # Unreviewed extra artifact
    ".hidden/source_copy.json",  # Hidden nested evidence
])
def test_prepublication_rejects_every_unexpected_file(tmp_path, extra_path):
    root = _staged(tmp_path / "reports")
    extra = root / extra_path
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("SYNTHETIC_ONLY")
    with pytest.raises(ValueError, match="unexpected files"):
        write_evidence_manifest(root, [2012], SOURCE_SHA)
    assert not (root / MANIFEST_NAME).exists()


def test_allowlisted_reports_still_publish(tmp_path):
    root = _staged(tmp_path / "reports")
    manifest = write_evidence_manifest(root, [2012], SOURCE_SHA)
    assert len(manifest["files"]) == len(ANNUAL_FILES) + 1
    assert (root / MANIFEST_NAME).is_file()
