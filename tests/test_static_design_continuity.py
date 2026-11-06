"""Synthetic-only regression tests for immutable record continuity."""
import pytest

from scripts.static_design_continuity import verify_static_design_continuity


def row(batch="b1", request="r1", digest="a" * 64):
    return {"batch_id": batch, "request_id": request, "payload_sha256": digest}


@pytest.mark.parametrize("before,after,expected", [
    ([row()], [row()], (True, 0, 0, 0)),
    ([row()], [row(), row(request="r2")], (True, 0, 0, 1)),
    ([row()], [], (False, 1, 0, 0)),
    ([row()], [row(digest="b" * 64)], (False, 0, 1, 0)),
    ([row()], [row(request="r2")], (False, 1, 0, 1)),
    ([row(), row(request="r2")], [row(request="r2"), row()], (True, 0, 0, 0)),
])
def test_continuity_classifies_record_changes(before, after, expected):
    result = verify_static_design_continuity(before, after)
    assert (result["continuity_preserved"], result["removed"],
            result["modified"], result["added"]) == expected
    assert result["review_required"] is any(expected[1:])
    assert result["execution_authorized"] is False
    assert result["results_verified"] is False
    assert result["jobs_created"] == 0


@pytest.mark.parametrize("bad", [
    None, {}, "bad", [1], [{"batch_id": "b"}],
    [dict(row(), extra=1)], [row(), row()],
    [row(batch="")], [row(request="")], [row(digest="A" * 64)],
    [row(digest="abc")], [row(batch=1)], [row(request=True)],
    [row(batch="x" * 129)],
])
def test_rejects_malformed_or_duplicate_records(bad):
    with pytest.raises(ValueError):
        verify_static_design_continuity([row()], bad)


def test_rejects_oversized_manifest():
    with pytest.raises(ValueError):
        verify_static_design_continuity([], [row(request=str(i)) for i in range(10001)])


def test_does_not_mutate_inputs():
    old, new = [row()], [row(request="r2")]
    verify_static_design_continuity(old, new)
    assert old == [row()] and new == [row(request="r2")]


@pytest.mark.parametrize("invalid", [
    " leading", "trailing ", "line\\nbreak", "nul\\x00byte",
    "tab\\tvalue", "e\\u0301", "zero\\u200bwidth",
])
@pytest.mark.parametrize("field", ["batch_id", "request_id"])
def test_rejects_ambiguous_or_noncanonical_identities(invalid, field):
    bad = row()
    bad[field] = invalid
    with pytest.raises(ValueError, match="Invalid manifest identity"):
        verify_static_design_continuity([row()], [bad])


def test_reordering_does_not_trigger_review():
    first, second = row(request="a"), row(request="b")
    result = verify_static_design_continuity([first, second], [second, first])
    assert result["continuity_preserved"] is True
    assert result["review_required"] is False
