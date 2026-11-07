"""Security regression for GitHub Actions dependencies and least privilege.

No runner privileges, market data or network access are required by these tests.
Source SHA strings are exact verified official action v4/v5 commit objects; do
not silently roll forward a tag. A workflow dependency lockfile could replace
this per-ref guard if introduced and independently checked.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES = re.compile(r"^\s*-\s*uses:\s*(\S+)\s*$", re.M)
SHA = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})$")
DENIED = re.compile(r"^\s*pull_request_target\s*:", re.M)
READ = re.compile(r"^\s*contents\s*:\s*read\s*(?:#.*)?$", re.M)


def test_every_external_action_is_exact_commit_pinned():
    workflows = sorted(WORKFLOWS.glob("*.yml"))
    assert len(workflows) >= 3
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        for item in USES.findall(text):
            if item.startswith("./"):
                continue
            match = SHA.fullmatch(item)
            assert match is not None, f"{path.name}: unpinned GitHub Action {item}"
            assert match.group(2) != "0" * 40


def test_no_privileged_pull_request_trigger_or_unscoped_github_token():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert DENIED.search(text) is None, f"{path.name}: unsafe pull_request_target"
        assert READ.search(text), f"{path.name}: missing read-only repository permission"
        # In this project CI is source/testing only: no workflow needs write.
        assert not re.search(r"^\s*(?:contents|actions|packages|id-token)\s*:\s*write\s*$", text, re.M)
