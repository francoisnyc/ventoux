"""'Approve this plan' (layer 15d): a drafted plan, checked again by the sheet itself, shown with
what it changes, the plan as drafted, what it will never do, its warnings, and how it becomes
real; never the model's own text.

See docs/layers/15-authoring.md (15d) and brief D64.
"""

import pytest
from test_authoring import (
    GOAL,
    INPUT_POLICY,
    TO_THE_EMAIL,
    TO_THE_NOTE,
    WRITER_DECIDES,
    branching_on_the_remark,
    refund_plan,
    the_package,
    with_a_remark,
    written,
)

from ventoux.authoring.approve import Drafted, NotApprovable, approve_this_plan
from ventoux.case.diff import diff
from ventoux.case.markdown import text
from ventoux.case.plain import plain
from ventoux.case.releases import package
from ventoux.case.sheet import never_sheet
from ventoux.testing import CATALOG

FOLDER = "packages/refund"
DRAFT = "drafts/refund-order@1.json"


def drafted(text: str, rounds: int = 2) -> Drafted:
    """The draft `text`, asked for by omar, of the recorded provider, for the refund goal."""
    return Drafted(text, DRAFT, asked_by="omar", provider="recorded", goal=GOAL, rounds=rounds)


def test_a_draft_that_doesnt_pass_is_refused_and_never_rendered() -> None:
    # Checked again by the sheet itself, never on the record's word: a record can say drafted,
    # its digest can match, and the draft still not pass (brief, D64).
    with pytest.raises(NotApprovable) as refused:
        approve_this_plan(drafted(TO_THE_NOTE), the_package(), FOLDER, CATALOG)
    assert str(refused.value) == (
        "refund-order@1 doesn't pass the check of refund, so it is never shown for approval: "
        f"draft it again\n{INPUT_POLICY}"
    )


HEADER = (
    "# Approve this plan: refund-order@1, for refund\n"
    "\n"
    "Drafted by `recorded` for omar, in 2 rounds, from the goal:\n"
    "\n"
    "> Refund the order, then draft a letter telling the customer it is on its way.\n"
)
PLAN_READ = "## Plan refund-order@1, as drafted\n\n- It starts at check\\_order.\n"
HOW = (
    "## How it becomes real\n"
    "\n"
    "This is a draft. It runs nowhere until a pull request is reviewed and merged, a release is "
    "made, and an environment activates it.\n"
)


def test_the_page_reads_provenance_changes_the_plan_nevers_warnings_and_how_in_order() -> None:
    before = the_package()
    after = package(before.written.case, [TO_THE_EMAIL])
    page = approve_this_plan(drafted(TO_THE_EMAIL), before, FOLDER, CATALOG)
    changes = plain(diff(before, after, CATALOG), before, after, CATALOG)
    # The sheet's headings one level down, under the page's title (brief, D64).
    nevers = "".join(
        f"#{line}" if line.startswith("#") else line
        for line in never_sheet(after, CATALOG).splitlines(keepends=True)
    )
    warnings = "## Warnings\n\nNone.\n"
    order = [page.index(part) for part in (HEADER, changes, PLAN_READ, nevers, warnings, HOW)]
    assert page.startswith(HEADER)
    assert order == sorted(order)
    assert page.endswith(HOW)
    # Every state of the plan as drafted, read as the case map reads it (brief, D56).
    assert "- write\\_letter calls letters.draft@2 (low risk, it writes)" in page


def test_warnings_are_said_as_ventoux_check_says_them() -> None:
    # A warning refuses nothing, and the approver reads it where the issue is, as `ventoux check`
    # writes it for a package written by hand (brief, D64).
    plan = refund_plan()
    plan["fields"]["remark"] = {"type": "string"}
    before = package(written(with_a_remark()), [written(plan)])
    page = approve_this_plan(drafted(written(branching_on_the_remark())), before, FOLDER, CATALOG)
    path, code, message = WRITER_DECIDES.split(": ", 2)
    line = f"{FOLDER}/case.json: {path} {code} (warning): {message}"
    assert f"## Warnings\n\n- {text(line)}\n" in page
