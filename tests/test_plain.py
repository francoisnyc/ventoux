"""The semantic diff in plain language, and readings of every entry (layer 13c; brief, D55 and
D56, D45 as amended).

See docs/layers/13-diff.md (13c) and docs/guides/releases.md, "What changed: the diff".
"""

from test_diff import packed
from test_diff_people import fresh

from ventoux.case.diff import diff
from ventoux.case.releases import changed
from ventoux.testing import CATALOG

# --- Slice 0: written otherwise, the same decisions ----------------------------------------------


def test_an_age_written_otherwise_is_no_verdict() -> None:
    # From the review of #48: 1d and 24h decide the same for every case, so nothing suggests a
    # loosening; the history words the age as written, and the line says so (13c, choice 38).
    found = diff(packed(fresh("1d")), packed(fresh("24h")), CATALOG)
    assert found.changes == ()
    assert [str(line) for line in found.rewritten] == [
        (
            "rewritten  steps.lookup.max_age.order_id: 1d -> 24h: the same decisions; the history "
            "says 24 hours where it said 1 day"
        )
    ]
    assert found.summary() == "fresh: no behaviour change; 1 written otherwise; no wording change"
    # Never less than the digest (choice 5): the path it sees is said, as a rewriting.
    seen = changed(packed(fresh("1d")), packed(fresh("24h"))).behaviour
    assert list(seen) == [line.path for line in found.rewritten]
