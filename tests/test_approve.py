"""'Approve this plan' (layer 15d): a drafted plan, checked again by the sheet itself, shown with
what it changes, the plan as drafted, what it will never do, its warnings, and how it becomes
real; never the model's own text.

See docs/layers/15-authoring.md (15d) and brief D64.
"""

import subprocess
import sys

import pytest
from test_authoring import (
    GOAL,
    INPUT_POLICY,
    OUT_OF_REACH,
    ROOT,
    TO_THE_EMAIL,
    TO_THE_NOTE,
    WRITER_DECIDES,
    branching_on_the_remark,
    refund_plan,
    the_package,
    with_a_remark,
    with_letter,
    written,
)
from test_layers import forbidden_calls

from ventoux.authoring.approve import Drafted, NotApprovable, approve_this_plan
from ventoux.case.diff import diff
from ventoux.case.markdown import text
from ventoux.case.plain import plain
from ventoux.case.releases import package
from ventoux.case.sheet import never_sheet
from ventoux.testing import CATALOG

FOLDER = "packages/refund"


def drafted(text: str, rounds: int = 2) -> Drafted:
    """The draft `text`, asked for by omar, of the recorded provider, for the refund goal."""
    return Drafted(text, asked_by="omar", provider="recorded", goal=GOAL, rounds=rounds)


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


def test_what_a_draft_or_a_person_writes_is_shown_never_rendered() -> None:
    # A title, a literal, the goal and who asked are shown escaped, as D56's pages are: no HTML,
    # heading, link or code span of their own, and a line break shown as \n (brief, D64).
    plan = with_letter("customer_email")
    plan["display"]["title"] = "<b>Pay</b>\n# a heading [a link](https://example.com) `x`"
    plan["states"]["write_letter"]["inputs"]["template"] = "<img src=x>"
    goal = "Refund it\n# Approved already, sign below"
    page = approve_this_plan(
        Drafted(written(plan), asked_by="omar", provider="recorded`x", goal=goal, rounds=1),
        the_package(),
        FOLDER,
        CATALOG,
    )
    for raw in ("<b>", "<img", "[a link](", "\n# a heading", "\n# Approved"):
        assert raw not in page
    # Quoted as JSON by the diff, then escaped: the line break shows as \\n (brief, D56).
    assert (
        "&lt;b&gt;Pay&lt;/b&gt;\\\\n\\# a heading \\[a link\\](https://example.com) \\`x\\`" in page
    )
    assert "> Refund it\\\\n\\# Approved already, sign below\n" in page  # renders as \\n
    assert "Drafted by ``recorded`x`` for omar, in 1 round, from the goal:" in page
    # The page's own headings, and only those, start a line with #.
    headings = [line for line in page.splitlines() if line.startswith("#")]
    assert headings[0] == "# Approve this plan: refund-order@1, for refund"
    assert all(line.startswith(("## ", "### ")) for line in headings[1:])


def test_the_sheet_cant_reach_the_builder_the_interpreter_or_temporal() -> None:
    # Nothing a draft holds runs, on the sheet either: it reads the draft as a plan and renders
    # it (brief, D58) (brief, D64).
    listed = subprocess.run(
        [sys.executable, "-I", "-c", "import sys, ventoux.authoring.approve; print(*sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert [name for name in listed if name.startswith(OUT_OF_REACH)] == []
    source = (ROOT / "src" / "ventoux" / "authoring" / "approve.py").read_text()
    assert forbidden_calls(source) == []
