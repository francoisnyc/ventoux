"""Case validation: what can be proven about a case definition by reading it (layer 10).

Tests go through `parse_case`, then `validate_case`, and read the issues it gives.
See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

import copy
import json
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel
from test_case import guide_refund_with_plan  # the cases guide's plan step, as it runs
from test_fresh_facts import refund_fresh  # the case-data guide's fresh refund
from test_rules import SAYS_SEND, notes_say_send, welcome_file, with_welcome  # the welcome letter

from ventoux.case.definition import parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.core.before_activity import InputRefused
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, RetryPolicy, Timeouts
from ventoux.core.contract import Display as ContractDisplay
from ventoux.core.output_sources import source
from ventoux.core.policy import only_from, trusted_only
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    AnswerRefused,
    CaseRefused,
    Outcome,
    ProposalRefused,
    RetryRefused,
    later,
    load_definition,
    payments_refund,
    propose,
    retry,
    run_case,
)

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## What `ventoux check` proves about a case"


def guide_json(index: int) -> dict[str, Any]:
    """The JSON block `index` of the guide's section on the check, as stored data; a fragment
    (`"requires": [...]`) is read as an object."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[index + 1].split("```")[0]
    fragment = block if block.lstrip().startswith("{") else "{" + block + "}"
    loaded: dict[str, Any] = json.loads(fragment, parse_float=Decimal)
    return loaded


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


# --- Slice 0: the seam ---


def test_only_a_parsed_case_is_validated() -> None:
    # Fail closed: a definition nobody parsed is refused, never read as one with no problems.
    with pytest.raises(TypeError, match="parse_case"):
        validate_case(REFUND, CATALOG)  # type: ignore[arg-type]


def test_an_issue_is_an_error_unless_it_says_otherwise() -> None:
    # Fail closed: a check that forgets to say how serious its issue is refuses the definition.
    assert Issue("steps.pay", "NEVER_RUNS", "pay can never run").severity == "error"
    warned = Issue("closes_when", "CLOSE_UNREACHABLE", "paid can never be reached", "warning")
    assert warned.severity == "warning"


def test_the_guides_claim_has_no_issues() -> None:
    assert issues(guide_json(0)) == []


def test_the_quickstart_refund_has_no_issues() -> None:
    assert issues(REFUND) == []


# --- Slice 1: steps that never run ---


def claim_with(**steps: Any) -> dict[str, Any]:
    """The guide's claim with some steps replaced (or added)."""
    claim = guide_json(0)
    claim["steps"] |= steps
    return claim


def reviewed(claim: dict[str, Any]) -> dict[str, Any]:
    """`claim` with a `reviewed` milestone, which no step reaches."""
    claim["milestones"]["reviewed"] = {"display": {"title": "Claim reviewed"}}
    return claim


APPROVE = {
    "kind": "task",
    "display": {"title": "Approve the assessment"},
    "roles": ["adjuster"],
    "requires": ["reviewed"],
    "outcomes": {"ok": {"display": {"title": "Approved"}}},
}


def test_a_step_requiring_what_nothing_reaches_never_runs() -> None:
    assert issues(reviewed(claim_with(approve=APPROVE))) == [
        Issue(
            "steps.approve.requires",
            "NEVER_RUNS",
            "approve can never run: it requires reviewed, which no step or rule reaches: reach "
            "reviewed from a step or a rule, or remove the requirement",
        )
    ]


def test_the_order_of_the_steps_does_not_matter() -> None:
    # A case has no position: `pay` written before the steps it waits on can still run. One pass
    # in the written order would find `pay` and `assess` not yet possible, and refuse them.
    claim = guide_json(0)
    claim["steps"] = dict(reversed(claim["steps"].items()))
    assert list(claim["steps"]) == ["call_customer", "pay", "assess", "check"]
    assert issues(claim) == []


# --- Slice 2: the curriculum's negative test ---

# The claim's `call_customer` waits for `pay`: wherever `pay` can never run, neither can it.
CALL_CUSTOMER_NEVER_RUNS = Issue(
    "steps.call_customer.requires",
    "NEVER_RUNS",
    "call_customer can never run: it requires pay, which can never run: fix pay first",
)


def deadlocked_claim() -> dict[str, Any]:
    """The guide's claim with `assess` also requiring `paid`, as the guide shows it."""
    claim = guide_json(0)
    claim["steps"]["assess"] |= guide_json(1)
    return claim


def errors(definition: dict[str, Any]) -> list[Issue]:
    return [issue for issue in issues(definition) if issue.severity == "error"]


def guide_section() -> str:
    return GUIDE.read_text().split(SECTION)[1]


def printed(found: list[Issue]) -> str:
    """Issues as the guide prints them, `path  CODE  message`, line breaks aside."""
    lines = [
        f"{i.path}  {i.code}{' (warning)' if i.severity == 'warning' else ''}  {i.message}"
        for i in found
    ]
    return " ".join(" ".join(lines).split())


def test_the_deadlocked_claim_is_refused() -> None:
    # The guide's output, word for word, line breaks aside.
    shown = guide_section().split("before any case opens:\n\n```\n")[1].split("```")[0]
    assert printed(issues(deadlocked_claim())) == " ".join(shown.split())
    # One issue for the steps that wait on each other, none for each of them.
    assert errors(deadlocked_claim()) == [
        Issue(
            "steps.assess.requires",
            "DEADLOCK",
            "assess and pay wait on each other: assess requires paid, which only pay reaches; "
            "pay requires assessed, which only assess reaches: remove one of these requirements",
        ),
        CALL_CUSTOMER_NEVER_RUNS,
    ]


def test_a_step_requiring_itself_is_deadlocked() -> None:
    claim = guide_json(0)
    claim["steps"]["check"]["requires"] = ["check"]
    assert errors(claim) == [
        Issue(
            "steps.check.requires",
            "DEADLOCK",
            "check waits on itself: check requires check: remove this requirement",
        ),
        Issue(
            "steps.assess.requires",
            "NEVER_RUNS",
            "assess can never run: it requires checked, which only check reaches, and check can "
            "never run: fix check first",
        ),
        Issue(
            "steps.pay.requires",
            "NEVER_RUNS",
            "pay can never run: it requires assessed, which only assess reaches, and assess can "
            "never run: fix assess first",
        ),
        CALL_CUSTOMER_NEVER_RUNS,
    ]


def test_sequence_and_requires_can_deadlock() -> None:
    # `sequence` makes pay require assess; assess requiring pay closes the circle. The message
    # says where the requirement nobody wrote on pay comes from.
    claim = guide_json(0)
    claim["steps"]["assess"]["requires"] = ["checked", "pay"]
    claim["steps"]["pay"]["requires"] = []
    claim["sequence"] = ["assess", "pay"]
    assert errors(claim) == [
        Issue(
            "steps.assess.requires",
            "DEADLOCK",
            "assess and pay wait on each other: assess requires pay; pay comes after assess in "
            "sequence: remove one of these requirements",
        ),
        CALL_CUSTOMER_NEVER_RUNS,
    ]


NOTIFY = {
    "kind": "task",
    "display": {"title": "Tell the customer"},
    "roles": ["adjuster"],
    "requires": ["assessed"],
    "outcomes": {"told": {"display": {"title": "Told"}}},
}


def test_a_step_waiting_on_a_deadlock_never_runs() -> None:
    claim = deadlocked_claim()
    claim["steps"]["notify"] = NOTIFY
    claim["steps"]["remind"] = {**NOTIFY, "requires": ["assess"]}
    assert errors(claim)[1:] == [
        CALL_CUSTOMER_NEVER_RUNS,
        Issue(
            "steps.notify.requires",
            "NEVER_RUNS",
            "notify can never run: it requires assessed, which only assess reaches, and assess can "
            "never run: fix assess first",
        ),
        Issue(
            "steps.remind.requires",
            "NEVER_RUNS",
            "remind can never run: it requires assess, which can never run: fix assess first",
        ),
    ]


# --- Slice 3: closing ---


def test_a_step_after_the_close_never_runs() -> None:
    # `closes_when` is checked before admission (layer 8b): once paid is reached the case is
    # closing, and nothing starts.
    thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["paid"]}
    assert issues(claim_with(thank=thank)) == [
        Issue(
            "steps.thank.requires",
            "NEVER_RUNS",
            "thank can never run: it requires paid, and claim closes once paid is reached, before "
            "thank could start: remove paid from its requires, or from closes_when",
        )
    ]


def test_a_step_nobody_may_propose_never_runs() -> None:
    # A role nobody registered counts for nothing, as when the case runs (brief, D22).
    recheck = {
        **NOTIFY,
        "display": {"title": "Check the customer again"},
        "requires": ["checked"],
        "automatic": False,
        "proposed_by": ["supprt"],
    }
    assert issues(claim_with(recheck=recheck)) == [
        Issue(
            "steps.recheck.proposed_by",
            "NEVER_RUNS",
            "recheck can never run: it starts only when proposed, and none of its proposed_by "
            "roles (supprt) is registered: name a registered role",
        )
    ]


def test_a_case_that_closes_at_opening_is_refused() -> None:
    # Nothing is pending when it opens, so it closes at once, and every proposal after is refused.
    # Here it is the only cause, so the only issue.
    claim = guide_json(0)
    claim["steps"]["check"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    assert issues(claim) == [
        Issue(
            "steps",
            "CLOSES_AT_OPENING",
            "nothing starts by itself when claim opens, so it closes at once and every proposal "
            "is refused: let a step start by itself with nothing required, start one from a rule "
            "on the opening, or add stays_open",
        )
    ]


def test_closing_at_opening_is_said_beside_a_step_dead_for_its_own_reason() -> None:
    # Two causes, two fixes: the case closes at once, and approve needs reviewed, which nothing
    # reaches. A step dead for its own reason keeps its own issue.
    claim = reviewed(claim_with(approve=APPROVE))
    claim["steps"]["check"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    assert [issue.code for issue in issues(claim)] == ["CLOSES_AT_OPENING", "NEVER_RUNS"]
    assert issues(claim)[1].path == "steps.approve.requires"


def staying_open(claim: dict[str, Any]) -> dict[str, Any]:
    """`claim`, staying open, with one close reason for a role nobody registered."""
    claim["stays_open"] = True
    claim["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate claim"}, "roles": ["supprt"]}
    }
    return claim


NEVER_CLOSES = Issue(
    "close_reasons",
    "NEVER_CLOSES",
    "claim stays open, none of its close reasons' roles (supprt) is registered, and closes_when "
    "never closes it, so nothing but a forget request could close it: name a registered role in "
    "a close reason",
)


def test_a_case_nobody_can_close_is_refused() -> None:
    # The tutor review's probe: closes_when closes a case that stays open too (layer 8b), so
    # paid, which pay reaches, closes this one.
    # Since 10b, the role nobody registered is said: it can never close the case (brief, D35).
    misspelt = unknown_role("close_reasons.duplicate.roles", "supprt")
    assert issues(staying_open(guide_json(0))) == [misspelt]
    # With paid unreachable, or no closes_when at all, only a forget request could close it
    # (brief, D32), as 11b's wording says (it said "nobody could ever close it"). The issue
    # names the roles, and no UNKNOWN_ROLE repeats them: one cause, one issue.
    assert NEVER_CLOSES in issues(staying_open(deadlocked_claim()))
    assert misspelt not in issues(staying_open(deadlocked_claim()))
    without_close = staying_open(guide_json(0))
    del without_close["closes_when"]
    assert issues(without_close) == [NEVER_CLOSES]
    without_close["close_reasons"]["duplicate"]["roles"] = ["supprt", "adjuster"]
    assert issues(without_close) == [misspelt]


def letter_case(**thank: Any) -> dict[str, Any]:
    """A welcome letter: draft it, which reaches `sent`, and the case closes on `sent`. Its
    contract, `letters.draft@3`, declares no outcomes, so every completion reaches `sent`. Then
    `thank`, with `thank`'s keys changed."""
    return {
        "case": "letter",
        "display": {"title": "Welcome letter"},
        "fields": {
            "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}}
        },
        "milestones": {"sent": {"display": {"title": "Letter drafted"}}},
        "steps": {
            "draft": {
                "kind": "activity",
                "display": {"title": "Draft the welcome letter"},
                "activity": "letters.draft@3",
                "inputs": {"customer": {"var": "customer_id"}, "template": "welcome"},
                "reaches": ["sent"],
            },
            "thank": {
                **NOTIFY,
                "display": {"title": "Thank the customer"},
                "requires": ["draft"],
                **thank,
            },
        },
        "closes_when": ["sent"],
    }


AFTER_DRAFT = Issue(
    "steps.thank.requires",
    "NEVER_RUNS",
    "thank can never run: it runs only after draft, which reaches sent, and letter closes once "
    "sent is reached, before thank could start: run thank before draft, or remove sent from "
    "closes_when",
)


def test_a_step_after_the_close_through_a_step_it_requires_never_runs() -> None:
    # The tutor review's probe: requiring draft, thank waits for sent, which closes the case.
    assert issues(letter_case()) == [AFTER_DRAFT]
    # The proof holds in a run: the case closes on sent, and thank never starts.
    run = run_case(letter_case(), file={"customer_id": "cus-7"}, answers=[], people={})
    assert run.history[-1] == "closed: sent reached"
    assert not any(line.startswith("started thank") for line in run.history)


def test_a_step_after_the_close_through_sequence_never_runs() -> None:
    # `sequence: [draft, thank]` is the natural way to write it.
    in_sequence = letter_case(requires=[])
    in_sequence["sequence"] = ["draft", "thank"]
    assert issues(in_sequence) == [AFTER_DRAFT]


def test_what_a_step_waits_for_is_followed_through_the_steps_it_requires() -> None:
    # review waits only for sent, so it runs; thank, requiring review, waits for sent too, through
    # review's own requirement, and for reviewed: every closes_when milestone.
    case = letter_case(requires=["review"])
    case["milestones"]["reviewed"] = {"display": {"title": "Letter reviewed"}}
    case["steps"]["review"] = {
        **NOTIFY,
        "display": {"title": "Review the letter"},
        "requires": ["draft"],
        "reaches": ["reviewed"],
    }
    case["closes_when"] = ["sent", "reviewed"]
    assert issues(case) == [
        Issue(
            "steps.thank.requires",
            "NEVER_RUNS",
            "thank can never run: it runs only after draft, which reaches sent, and review, which "
            "reaches reviewed, and letter closes once they are reached, before thank could start: "
            "change what it requires, or closes_when",
        )
    ]
    # Requiring reviewed itself, and waiting for draft: both parts said.
    case["steps"]["thank"]["requires"] = ["reviewed", "draft"]
    assert issues(case)[0].message == (
        "thank can never run: it requires reviewed and runs only after draft, which reaches sent, "
        "and letter closes once they are reached, before thank could start: change what it "
        "requires, or closes_when"
    )


def test_a_step_after_a_step_that_may_end_otherwise_can_run() -> None:
    # pay's contract declares `declined`: a declined run is done, which meets `requires: [pay]`,
    # but reaches no milestone (layer 8b). So paid isn't sure, and thank does run then: an error
    # here would not hold for every case (brief, D34).
    thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["pay"]}
    assert issues(claim_with(thank=thank)) == []
    run = run_case(
        claim_with(thank=thank),
        file={"customer_id": "cus-7", "order_id": "ord-1"},
        answers=[("assess", "accept", "ana", {"payout": 50}), ("pay", "approve", "sam")],
        people={"ana": ["adjuster"], "sam": ["support-lead"]},
        activities={"payments.refund@2": declines},
    )
    assert "pay#1 gave declined" in run.history
    assert any(line.startswith("started thank#1") for line in run.history)


def declines(inputs: dict[str, Any]) -> dict[str, Any]:
    raise Outcome("declined")


# --- Slice 4: warnings ---

CLOSE_UNREACHABLE = Issue(
    "closes_when",
    "CLOSE_UNREACHABLE",
    "paid can never be reached, so closes_when never closes claim, and it closes when nothing is "
    "left to do: reach paid from a step that can run, or remove it from closes_when",
    "warning",
)


def test_an_unreachable_close_is_a_warning() -> None:
    # A warning, as D10 asks: the case still closes, when nothing is left to do.
    found = issues(deadlocked_claim())
    assert [issue.code for issue in found] == ["DEADLOCK", "NEVER_RUNS", "CLOSE_UNREACHABLE"]
    assert found[2] == CLOSE_UNREACHABLE


def test_an_unreachable_close_says_how_the_case_closes_instead() -> None:
    claim = deadlocked_claim()
    claim["stays_open"] = True
    claim["close_reasons"] = {
        "withdrawn": {"display": {"title": "Claim withdrawn"}, "roles": ["adjuster"]}
    }
    assert issues(claim)[2].message == (
        "paid can never be reached, so closes_when never closes claim, and only a person can "
        "close it: reach paid from a step that can run, or remove it from closes_when"
    )


def test_every_unreachable_close_milestone_is_named() -> None:
    claim = deadlocked_claim()
    claim["closes_when"] = ["assessed", "paid"]
    assert issues(claim)[2].message == (
        "assessed and paid can never be reached, so closes_when never closes claim, and it closes "
        "when nothing is left to do: reach them from steps that can run, or remove them from "
        "closes_when"
    )


def test_a_milestone_nothing_reaches_is_a_warning() -> None:
    assert issues(reviewed(guide_json(0))) == [
        Issue(
            "milestones.reviewed",
            "UNREACHABLE_MILESTONE",
            "no step or rule reaches reviewed: reach it from a step, an outcome or a rule, or "
            "remove it",
            "warning",
        )
    ]
    # One cause, one issue: a milestone a step requires is said by that step's NEVER_RUNS, one in
    # closes_when by CLOSE_UNREACHABLE, and one only dead steps reach by their own issues.
    required = issues(reviewed(claim_with(approve=APPROVE)))
    assert [issue.code for issue in required] == ["NEVER_RUNS"]
    closing = reviewed(guide_json(0))
    closing["closes_when"] = ["reviewed"]
    assert [issue.code for issue in issues(closing)] == ["CLOSE_UNREACHABLE"]
    assert [issue.code for issue in issues(deadlocked_claim())] == [
        "DEADLOCK",
        "NEVER_RUNS",
        "CLOSE_UNREACHABLE",
    ]


# --- Slice 5: the runtime on its own ---


def test_an_unchecked_deadlock_still_runs_safely() -> None:
    # The runtime depends on nothing validation did (brief, D34): run without ever being checked,
    # the deadlocked claim checks the customer, starts nothing more, and closes with nothing paid,
    # as the guide says.
    run = run_case(
        deadlocked_claim(),
        file={"customer_id": "cus-7", "order_id": "ord-1"},
        answers=[],
        people={"ana": ["adjuster"]},
    )
    assert run.closed
    assert run.history[-1] == "closed: nothing left to do; paid not reached"  # #44's review
    assert any(line.startswith("check#1 done") for line in run.history)
    assert not any(line.startswith(("started assess", "scheduled pay")) for line in run.history)


# --- Slice 6: the guide and the promises ---


def closes_at_opening() -> dict[str, Any]:
    claim = guide_json(0)
    claim["steps"]["check"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    return claim


def nobody_closes() -> dict[str, Any]:
    claim = staying_open(guide_json(0))
    del claim["closes_when"]
    return claim


def approve_never_runs() -> dict[str, Any]:
    return reviewed(claim_with(approve=APPROVE))


def reviewed_unreached() -> dict[str, Any]:
    return reviewed(guide_json(0))


# A definition that makes each of the guide's codes happen, in the table's order.
GUIDE_EXAMPLES: dict[str, Callable[[], dict[str, Any]]] = {
    "DEADLOCK": deadlocked_claim,
    "NEVER_RUNS": approve_never_runs,
    "CLOSES_AT_OPENING": closes_at_opening,
    "NEVER_CLOSES": nobody_closes,
    "CLOSE_UNREACHABLE": deadlocked_claim,
    "UNREACHABLE_MILESTONE": reviewed_unreached,
}


def guide_table(index: int = 1) -> list[tuple[str, str, str]]:
    """The guide's table of codes `index` (1: structure, 2: what each step calls), as (code,
    kind, example message); "as above" is the output above it, checked word for word."""
    table = guide_section().split("| Code | Kind |")[index].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    return [
        (code.strip().strip("`"), kind.strip(), says.strip().strip("`"))
        for _, code, kind, _, says, _ in rows
    ]


def test_the_guide_lists_every_code() -> None:
    assert [code for code, _, _ in guide_table()] == list(GUIDE_EXAMPLES)


@pytest.mark.parametrize(("code", "kind", "says"), guide_table())
def test_the_guides_table_is_what_validate_case_says(code: str, kind: str, says: str) -> None:
    found = [issue for issue in issues(GUIDE_EXAMPLES[code]()) if issue.code == code]
    assert [issue.severity for issue in found] == [kind]
    if says != "as above":
        assert [issue.message for issue in found] == [says]


def marked(data: Any) -> Any:
    """`data` with every title and reason replaced by a marker, `TITLE-…`."""
    if isinstance(data, dict):
        return {
            key: f"TITLE-{value}" if key in ("title", "reason") else marked(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [marked(item) for item in data]
    return data


def test_no_message_quotes_a_value() -> None:
    # Messages read names, never what people read or what a condition compares: a definition's
    # titles, its approval's reason, a literal in a `when` (brief, D30).
    for make in GUIDE_EXAMPLES.values():
        definition = marked(make())
        definition["steps"]["pay"]["when"] = {">": [{"var": "payout"}, 987654]}
        found = issues(definition)
        assert found
        for issue in found:
            assert "TITLE-" not in issue.message and "987654" not in issue.message, issue


def test_three_steps_can_wait_on_each_other() -> None:
    claim = guide_json(0)
    claim["steps"]["check"]["requires"] = ["paid"]
    assert errors(claim) == [
        Issue(
            "steps.check.requires",
            "DEADLOCK",
            "check, pay and assess wait on each other: check requires paid, which only pay reaches; "
            "pay requires assessed, which only assess reaches; assess requires checked, which only "
            "check reaches: remove one of these requirements",
        ),
        CALL_CUSTOMER_NEVER_RUNS,
    ]


def test_a_milestone_two_dead_steps_reach_names_both() -> None:
    claim = deadlocked_claim()
    claim["steps"]["reassess"] = {
        **NOTIFY,
        "display": {"title": "Assess the claim again"},
        "requires": ["paid"],
        "reaches": ["assessed"],
    }
    claim["steps"]["notify"] = NOTIFY
    assert errors(claim) == [
        Issue(
            "steps.assess.requires",
            "DEADLOCK",
            "assess and pay wait on each other: assess requires paid, which only pay reaches; "
            "pay requires assessed, which only assess and reassess reach: remove one of these "
            "requirements",
        ),
        CALL_CUSTOMER_NEVER_RUNS,
        Issue(
            "steps.notify.requires",
            "NEVER_RUNS",
            "notify can never run: it requires assessed, which only assess and reassess reach, "
            "and they can never run: fix assess first",
        ),
    ]


def test_a_step_after_a_close_on_two_milestones_never_runs() -> None:
    claim = guide_json(0)
    claim["closes_when"] = ["assessed", "paid"]
    thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["assessed", "paid"]}
    claim["steps"]["thank"] = thank
    assert errors(claim) == [
        Issue(
            "steps.thank.requires",
            "NEVER_RUNS",
            "thank can never run: it requires assessed and paid, and claim closes once they are "
            "reached, before thank could start: remove one of them from its requires",
        )
    ]
    # Removing one from closes_when, as the advice once said, leaves thank requiring the other,
    # on which the case still closes: still never run.
    claim["closes_when"] = ["paid"]
    assert [issue.code for issue in errors(claim)] == ["NEVER_RUNS"]


def test_a_milestone_a_waited_for_step_requires_is_said_so() -> None:
    # notify requires paid and reaches notified; thank, after notify, waits for both. notify
    # doesn't reach paid: it requires it.
    claim = guide_json(0)
    claim["milestones"]["notified"] = {"display": {"title": "Customer told"}}
    claim["closes_when"] = ["paid", "notified"]
    claim["steps"]["notify"] = {**NOTIFY, "requires": ["paid"], "reaches": ["notified"]}
    claim["steps"]["thank"] = {
        **NOTIFY,
        "display": {"title": "Thank the customer"},
        "requires": ["notify"],
    }
    assert errors(claim) == [
        Issue(
            "steps.thank.requires",
            "NEVER_RUNS",
            "thank can never run: it runs only after notify, which requires paid and reaches "
            "notified, and claim closes once they are reached, before thank could start: run "
            "thank before notify, or remove paid and notified from closes_when",
        )
    ]


# --- 10b, slice 1: the contract or the plan a step calls ---

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}
SMALL = {"order_id": "ord-1", "amount": 40}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 40})


def refund_with(**pay: Any) -> dict[str, Any]:
    """The quickstart's refund, with `pay`'s keys changed (or removed, given as None)."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["pay"] |= pay
    refund["steps"]["pay"] = {k: v for k, v in refund["steps"]["pay"].items() if v is not None}
    return refund


def small_refund(definition: dict[str, Any], **given: Any) -> CaseRun:
    """The quickstart's small refund, reviewed by Ana, run with `definition`."""
    return run_case(definition, file=SMALL, answers=[REVIEWED], people=PEOPLE, **given)


NOT_IN_CATALOG = (
    "payments.refund@3 is not in the catalog. Registered: payments.refund@2. Use a registered "
    "version, or register this one first."
)


def test_a_contract_nobody_registered_is_refused() -> None:
    refund = refund_with(activity="payments.refund@3")
    assert issues(refund) == [Issue("steps.pay.activity", "UNKNOWN_CONTRACT", NOT_IN_CATALOG)]
    # The proof: run as it is, the step fails, and waits for a person.
    assert small_refund(refund).needs_attention == [f"pay#1: {NOT_IN_CATALOG}"]


def test_a_step_and_its_contract_are_the_same_kind() -> None:
    wrong = "payments.refund@2 is an activity contract, not a workflow: run it as an activity step."
    refund = refund_with(kind="workflow", workflow="payments.refund@2", activity=None)
    assert issues(refund) == [Issue("steps.pay.workflow", "WRONG_KIND", wrong)]
    assert small_refund(refund).needs_attention == [f"pay#1: {wrong}"]


PLANS_GUIDE = ROOT / "docs" / "guides" / "plans.md"


def refund_order(version: int = 1) -> dict[str, Any]:
    """The plans guide's `refund-order` plan, its first JSON block, as stored data."""
    example = PLANS_GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan | {"version": version}


# The cases guide's plan step: the refund paid through the plans guide's `refund-order` plan.
SETTLE: dict[str, Any] = {
    "kind": "plan",
    "display": {"title": "Settle the refund"},
    "plan": "refund-order@1",
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
    "requires": ["review"],
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
}
PLANS = {"refund-order@1": refund_order(), "refund-order@3": refund_order(version=1)}


def settled(**settle: Any) -> dict[str, Any]:
    """The quickstart's refund, `pay` replaced by the plan step, with `settle`'s keys changed, and
    `call_customer` reacting to the plan failing, as the cases guide writes it."""
    refund = copy.deepcopy(REFUND)
    del refund["steps"]["pay"], refund["sequence"]
    refund["steps"]["settle"] = {**copy.deepcopy(SETTLE), **settle}
    refund["steps"]["call_customer"]["requires"] = ["settle"]
    refund["steps"]["call_customer"]["when"] = {"==": [{"var": "settle.outcome"}, "failed"]}
    return refund


def checked_with(definition: dict[str, Any], plans: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG, plans=plans)


def test_a_plan_nobody_supplied_is_refused() -> None:
    # Fail closed: with no plans given, a plan step's plan isn't there.
    missing = "no plan refund-order@1 is available"
    expected = Issue(
        "steps.settle.plan", "UNKNOWN_PLAN", f"{missing}: supply it with the deployment's plans"
    )
    assert issues(settled()) == [expected]
    assert checked_with(settled(), {}) == [expected]
    # Given as the runtime is given it, the plan is found.
    assert checked_with(settled(), PLANS) == []
    # The proof: run as it is, with no plans, the step fails.
    run = run_case(settled(), file=SMALL, answers=[REVIEWED], people=PEOPLE, plans={})
    assert run.needs_attention == [f"settle#1: {missing}"]


def test_a_plan_the_runtime_would_not_run_is_refused() -> None:
    # Read with the runtime's own reader: a plan supplied under another reference, or one that
    # can't be read, never runs in its place.
    misnamed = "refund-order@3 is supplied as refund-order@1: supply the plan it names"
    assert checked_with(settled(plan="refund-order@3"), PLANS) == [
        Issue("steps.settle.plan", "UNKNOWN_PLAN", misnamed)
    ]
    run = run_case(
        settled(plan="refund-order@3"), file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=PLANS
    )
    assert run.needs_attention == [f"settle#1: {misnamed}"]
    broken = {"refund-order@1": {"plan": "refund-order"}}
    [unreadable] = checked_with(settled(), broken)
    assert (unreadable.path, unreadable.code) == ("steps.settle.plan", "UNKNOWN_PLAN")
    assert unreadable.message.startswith("refund-order@1 can't be read: ")


# --- 10b, slice 2: inputs ---


def test_an_input_the_contract_does_not_take_is_refused() -> None:
    refund = refund_with(inputs={"order_id": {"var": "order_id"}, "amout": {"var": "amount"}})
    assert issues(refund) == [
        Issue(
            "steps.pay.inputs.amout",
            "UNKNOWN_INPUT",
            "payments.refund@2 has no input amout: its inputs are amount, order_id",
        ),
        Issue(
            "steps.pay.inputs",
            "MISSING_INPUT",
            "payments.refund@2 needs the input amount: add it to inputs",
        ),
    ]
    [refused] = small_refund(refund).needs_attention
    assert refused.startswith("pay#1: payments.refund@2 doesn't take these inputs: amout")


def test_an_input_the_contract_needs_is_given() -> None:
    refund = refund_with(inputs={"order_id": {"var": "order_id"}})
    assert issues(refund) == [
        Issue(
            "steps.pay.inputs",
            "MISSING_INPUT",
            "payments.refund@2 needs the input amount: add it to inputs",
        )
    ]
    [refused] = small_refund(refund).needs_attention
    assert refused.startswith("pay#1: payments.refund@2 doesn't take these inputs: amount")


ENGINE_KEY = "idempotency_key is filled by the engine, never by a definition: remove it"


def test_the_engine_fills_the_key() -> None:
    inputs = {**REFUND["steps"]["pay"]["inputs"], "idempotency_key": "mine"}
    refund = refund_with(inputs=inputs)
    assert issues(refund) == [Issue("steps.pay.inputs.idempotency_key", "ENGINE_INPUT", ENGINE_KEY)]
    # The proof: the runtime refuses it too, never overwriting it in silence.
    assert small_refund(refund).needs_attention == [f"pay#1: {ENGINE_KEY}"]


def test_a_step_whose_contract_is_missing_has_one_issue() -> None:
    # One cause, one issue: no input of a contract nobody registered is said to be wrong.
    refund = refund_with(activity="payments.refund@3", inputs={"amout": {"var": "amount"}})
    assert [issue.code for issue in issues(refund)] == ["UNKNOWN_CONTRACT"]


def review_and_pay() -> dict[str, Any]:
    """The plans guide's `review-and-pay` plan, whose review sets `approved_amount`."""
    blocks = PLANS_GUIDE.read_text().split("```json\n")[1:]
    example = next(block for block in blocks if '"review-and-pay"' in block).split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


def test_a_plan_step_gives_the_fields_its_plan_takes_at_its_start() -> None:
    misspelt = settled(inputs={"order_id": {"var": "order_id"}, "amout": {"var": "amount"}})
    assert checked_with(misspelt, PLANS) == [
        Issue(
            "steps.settle.inputs.amout",
            "UNKNOWN_INPUT",
            "refund-order@1 has no input amout: its inputs are amount, order_id",
        ),
        Issue(
            "steps.settle.inputs",
            "MISSING_INPUT",
            "refund-order@1 needs the input amount: add it to inputs",
        ),
    ]
    [refused] = run_case(
        misspelt, file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=PLANS
    ).needs_attention
    assert "amount is missing" in refused and "amout is not a field of refund-order" in refused
    # A field a person sets in the plan is theirs: the case never gives it.
    given = settled(
        plan="review-and-pay@1",
        inputs={"order_id": {"var": "order_id"}, "approved_amount": {"var": "amount"}},
    )
    plans = {"review-and-pay@1": review_and_pay()}
    assert checked_with(given, plans) == [
        Issue(
            "steps.settle.inputs.approved_amount",
            "UNKNOWN_INPUT",
            "review-and-pay@1 takes no input approved_amount: its wait review sets it; its inputs "
            "are order_id",
        )
    ]
    [refused] = run_case(
        given, file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=plans
    ).needs_attention
    assert "approved_amount is set by a person in review, never given at the start" in refused


# --- 10b, slice 3: roles, labels and systems nobody registered ---

ROLES = "adjuster, claims-sensitive, fraud, operations, platform, privacy, support, support-lead"


def unknown_role(path: str, role: str) -> Issue:
    return Issue(
        path,
        "UNKNOWN_ROLE",
        f"{role} is a role nobody registered: the roles are {ROLES}; use one of them, or ask the "
        "platform team to register it",
    )


def test_a_role_nobody_registered_answers_nothing() -> None:
    refund = copy.deepcopy(REFUND)
    refund["steps"]["review"]["roles"] = ["supprt"]
    assert issues(refund) == [unknown_role("steps.review.roles", "supprt")]
    # The proof: a role the engine doesn't know counts for nothing, whoever states it (brief,
    # D22).
    with pytest.raises(AnswerRefused, match="supprt"):
        run_case(refund, file=SMALL, answers=[REVIEWED], people={"ana": ["supprt"]})


def test_a_role_nobody_registered_approves_nothing() -> None:
    refund = refund_with(
        approval={**REFUND["steps"]["pay"]["approval"], "roles": ["support-lead", "suport-lead"]}
    )
    assert issues(refund) == [unknown_role("steps.pay.approval.roles", "suport-lead")]
    large = {"order_id": "ord-1", "amount": 250}
    approved = ("pay", "approve", "lee")
    with pytest.raises(AnswerRefused, match="suport-lead"):
        run_case(
            refund,
            file=large,
            answers=[("review", "approve", "ana", {"approved_amount": 250}), approved],
            people={"ana": ["support"], "lee": ["suport-lead"]},
        )


def test_a_role_nobody_registered_is_said_once() -> None:
    # One misspelt role among proposed_by is its own issue; if none is registered, the step can
    # never run, and that issue names them (10a): one cause, one issue.
    recheck = {
        **NOTIFY,
        "display": {"title": "Check the customer again"},
        "requires": ["checked"],
        "automatic": False,
        "proposed_by": ["supprt", "adjuster"],
    }
    assert issues(claim_with(recheck=recheck)) == [
        unknown_role("steps.recheck.proposed_by", "supprt")
    ]
    recheck["proposed_by"] = ["supprt"]
    assert [i.code for i in issues(claim_with(recheck=recheck))] == ["NEVER_RUNS"]
    # A close reason naming one: an issue, though another role may close the case.
    claim = staying_open(guide_json(0))
    claim["close_reasons"]["duplicate"]["roles"] = ["supprt", "adjuster"]
    assert issues(claim) == [unknown_role("close_reasons.duplicate.roles", "supprt")]


def test_a_role_nobody_registered_sees_nothing() -> None:
    refund = copy.deepcopy(REFUND)
    refund["fields"]["amount"]["visible_to"] = ["support", "suport-lead"]
    assert issues(refund) == [unknown_role("fields.amount.visible_to", "suport-lead")]
    # The proof: stated with a role nobody registered, a person sees nothing it would show
    # (brief, D22) (brief, D35).
    run = small_refund(refund)
    assert "amount" not in run.view(roles=["suport-lead"]).values
    assert "amount" in run.view(roles=["support"]).values


def test_a_label_nobody_registered_is_refused() -> None:
    refund = copy.deepcopy(REFUND)
    refund["fields"]["amount"]["source"] = "untrusted:custmer"
    assert issues(refund) == [
        Issue(
            "fields.amount.source",
            "UNKNOWN_SOURCE",
            "untrusted:custmer has a label nobody registered: the labels are customer, document, "
            "email, llm, web; use one of them, or ask the platform team to register it",
        )
    ]
    # The proof: a case declaring it doesn't open (brief, D12) (brief, D35).
    with pytest.raises(CaseRefused, match="custmer"):
        small_refund(refund)


def test_a_system_nobody_registered_is_refused() -> None:
    refund = copy.deepcopy(REFUND)
    refund["fields"]["order_id"]["system"] = "ordrs"
    assert issues(refund) == [
        Issue(
            "fields.order_id",
            "UNKNOWN_SYSTEM",
            "order_id is a reference to ordrs, which is not a registered system: the systems are "
            "crm, documents, kyc, orders, policies, portal; use one of them, or ask the platform team "
            "to register it",
        )
    ]
    # The proof: a case naming it doesn't open (brief, D30).
    with pytest.raises(CaseRefused, match="ordrs"):
        small_refund(refund)


# --- 10b, slice 4: a case's expressions, type-checked over the case's values ---

CLAIM_FILE = {"customer_id": "cus-7", "order_id": "ord-1"}
CLAIM_PEOPLE = {"ana": ["adjuster"], "sam": ["support-lead"]}
ACCEPTED = ("assess", "accept", "ana", {"payout": 50})


def claim_paying_when(when: Any) -> dict[str, Any]:
    claim = guide_json(0)
    claim["steps"]["pay"]["when"] = when
    return claim


def test_a_misspelt_outcome_is_refused() -> None:
    # The guide's example, word for word, line breaks aside.
    claim = guide_json(0)
    claim["steps"]["pay"] |= guide_json(2)
    shown = guide_section().split("before any case opens:\n\n```\n")[2].split("```")[0]
    assert printed(issues(claim)) == " ".join(shown.split())
    # The proof: run as it is, the step fails, saying why, never reading the condition as false
    # (brief, D35). Before 10b, the claim closed with nothing left to do, never paid.
    run = run_case(claim, file=CLAIM_FILE, answers=[ACCEPTED], people=CLAIM_PEOPLE)
    assert run.needs_attention == [
        (
            'pay#1: pay.when can\'t be read: ==[1]: assess.outcome has no outcome "acept"; its '
            "outcomes are accept, deny"
        )
    ]
    assert not run.closed


def test_a_case_reads_only_its_values() -> None:
    misspelt = claim_paying_when({">": [{"var": "payot"}, 0]})
    assert issues(misspelt) == [
        Issue("steps.pay.when", "EXPRESSION_INVALID", ">[0]: payot is not a declared field")
    ]
    run = run_case(misspelt, file=CLAIM_FILE, answers=[ACCEPTED], people=CLAIM_PEOPLE)
    assert run.needs_attention == [
        "pay#1: pay.when can't be read: >[0]: payot is not a declared field"
    ]
    # An approval nothing writes is not a value either (brief, D11's `pay.approval`).
    approval = {
        **guide_json(0)["steps"]["pay"]["approval"],
        "when": {"==": [{"var": "pay.approval"}, "reject"]},
    }
    claim = claim_with(pay={**guide_json(0)["steps"]["pay"], "approval": approval})
    assert issues(claim) == [
        Issue(
            "steps.pay.approval.when",
            "EXPRESSION_INVALID",
            "==[0]: pay.approval is not a declared field",
        )
    ]


def test_outcomes_and_outputs_have_their_contracts_types() -> None:
    def when(expression: Any) -> list[Issue]:
        thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["check"]}
        # Errors only: thank doesn't wait for pay, so reading pay.outcome warns (10d).
        return errors(claim_with(thank={**thank, "when": expression}))

    # An activity's outcome: done, or one its contract declares; a workflow's: done.
    assert when({"in": [{"var": "pay.outcome"}, ["done", "declined"]]}) == []
    assert when({"==": [{"var": "check.outcome"}, "done"]}) == []
    [declined] = when({"==": [{"var": "pay.outcome"}, "decline"]})
    assert declined.message == (
        '==[1]: pay.outcome has no outcome "decline"; its outcomes are done, declined'
    )
    [failed] = when({"==": [{"var": "check.outcome"}, "failed"]})
    assert failed.message == '==[1]: check.outcome has no outcome "failed"; its outcomes are done'
    # Outputs, with their contracts' types: kyc.check@1's risk_score is a number, status a text.
    assert when({">": [{"var": "check.risk_score"}, 50]}) == []
    [compared] = when({"==": [{"var": "check.status"}, 1]})
    assert (
        compared.message
        == "==[1]: `==` compares values of the same type, and this is a number, not a string"
    )
    [undeclared] = when({"exists": "check.score"})
    assert undeclared.message == "check.score is not a declared field"


def test_a_plan_steps_outcome_is_done_or_failed() -> None:
    def when(expression: Any) -> list[Issue]:
        refund = settled()
        refund["steps"]["tell"] = {
            "kind": "task",
            "display": {"title": "Tell the customer"},
            "roles": ["support"],
            "requires": ["settle"],
            "when": expression,
            "outcomes": {"told": {"display": {"title": "Told"}}},
        }
        return checked_with(refund, PLANS)

    assert when({"==": [{"var": "settle.outcome"}, "failed"]}) == []
    [refused] = when({"==": [{"var": "settle.outcome"}, "stopped"]})
    assert (
        refused.message
        == '==[1]: settle.outcome has no outcome "stopped"; its outcomes are done, failed'
    )


def test_a_condition_gives_true_or_false() -> None:
    assert issues(claim_paying_when({"var": "payout"})) == [
        Issue(
            "steps.pay.when",
            "EXPRESSION_INVALID",
            "a condition gives a boolean, and this gives a number: write a comparison, such as "
            "amount > 100",
        )
    ]
    run = run_case(
        claim_paying_when({"var": "payout"}),
        file=CLAIM_FILE,
        answers=[ACCEPTED],
        people=CLAIM_PEOPLE,
    )
    [failed] = run.needs_attention
    assert failed.startswith("pay#1: pay.when can't be read: a condition gives a boolean")


def test_an_input_reads_only_the_cases_values() -> None:
    refund = refund_with(
        inputs={"order_id": {"var": "order_id"}, "amount": {"+": [{"var": "amount"}, "1"]}}
    )
    assert issues(refund) == [
        Issue(
            "steps.pay.inputs.amount",
            "EXPRESSION_INVALID",
            "+[1]: `+` adds numbers, and this is a string",
        )
    ]
    assert small_refund(refund).needs_attention == [
        "pay#1: pay.inputs.amount can't be read: +[1]: `+` adds numbers, and this is a string"
    ]


def test_what_a_missing_contract_would_give_is_said_once() -> None:
    # One cause, one issue: pay's contract is missing, so neither its inputs nor what reads its
    # outcome is said to be wrong.
    claim = guide_json(0)
    claim["steps"]["pay"] |= {
        "activity": "payments.refund@3",
        "inputs": {"amout": {"var": "nothing"}},
    }
    thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["check"]}
    claim["steps"]["thank"] = {**thank, "when": {"==": [{"var": "pay.outcome"}, "done"]}}
    assert [issue.code for issue in issues(claim)] == ["UNKNOWN_CONTRACT"]


def test_a_proposal_or_a_retry_never_reads_a_misspelt_outcome() -> None:
    # The runtime checks a step's expressions wherever it would read them: a proposal and a
    # retry are refused, saying why, never decided on a condition read as false (brief, D35).
    claim = guide_json(0)
    claim["steps"]["recheck"] = {
        **NOTIFY,
        "display": {"title": "Check the customer again"},
        "requires": ["checked"],
        "automatic": False,
        "proposed_by": ["adjuster"],
        "when": {"==": [{"var": "assess.outcome"}, "acept"]},
    }
    misspelt = (
        'recheck.when can\'t be read: ==[1]: assess.outcome has no outcome "acept"; its outcomes '
        "are accept, deny"
    )
    with pytest.raises(ProposalRefused, match=re.escape(misspelt)):
        run_case(claim, file=CLAIM_FILE, answers=[propose("recheck", "ana")], people=CLAIM_PEOPLE)
    paying = guide_json(0)
    paying["steps"]["pay"] |= guide_json(2)
    with pytest.raises(RetryRefused, match=re.escape("pay#1 can't be retried: pay.when can't")):
        run_case(
            paying,
            file=CLAIM_FILE,
            answers=[ACCEPTED, retry("pay#1", "omar")],
            people={**CLAIM_PEOPLE, "omar": ["operations"]},
        )


# --- 10b, slice 5: approvals ---

LARGE = {"order_id": "ord-1", "amount": 250}
LARGE_REVIEW = ("review", "approve", "ana", {"approved_amount": 250})


def test_a_high_risk_step_has_an_approval() -> None:
    refund = refund_with(approval=None)
    no_approval = "payments.refund@2 is high risk, and pay has no approval"
    assert issues(refund) == [Issue("steps.pay", "APPROVAL_REQUIRED", f"{no_approval}: add one")]
    # The proof: the runtime stops it before it is scheduled (brief, D11).
    assert small_refund(refund).needs_attention == [f"pay#1: {no_approval}"]
    # An approval with a `when` is enough: the quickstart's refund asks only above 100.
    assert issues(REFUND) == []


def test_an_approvals_roles_may_approve_its_steps_risk() -> None:
    approval = {**REFUND["steps"]["pay"]["approval"], "roles": ["support-lead", "adjuster"]}
    refund = refund_with(approval=approval)
    refused = "adjuster may approve no risk, and payments.refund@2 is high risk"
    assert issues(refund) == [
        Issue(
            "steps.pay.approval.roles",
            "APPROVAL_ROLE",
            f"{refused}: name a role that may approve high risk",
        )
    ]
    with pytest.raises(AnswerRefused, match=re.escape(refused)):
        run_case(
            refund,
            file=LARGE,
            answers=[LARGE_REVIEW, ("pay", "approve", "lee")],
            people={"ana": ["support"], "lee": ["adjuster"]},
        )
    # A role nobody registered is said once, as UNKNOWN_ROLE; a missing contract once, as
    # UNKNOWN_CONTRACT: one cause, one issue.
    approval["roles"] = ["suport-lead"]
    assert [i.code for i in issues(refund_with(approval=approval))] == ["UNKNOWN_ROLE"]
    missing = refund_with(approval=None, activity="payments.refund@3")
    assert [i.code for i in issues(missing)] == ["UNKNOWN_CONTRACT"]


# --- 10b, slice 6: the guide and the promises ---


def check_as_activity() -> dict[str, Any]:
    claim = guide_json(0)
    del claim["steps"]["check"]["workflow"]
    claim["steps"]["check"] |= {"kind": "activity", "activity": "kyc.check@1"}
    return claim


def misspelt_acceptance() -> dict[str, Any]:
    claim = guide_json(0)
    claim["steps"]["pay"] |= guide_json(2)
    return claim


def with_field(name: str, **changed: Any) -> Callable[[], dict[str, Any]]:
    def make() -> dict[str, Any]:
        refund = copy.deepcopy(REFUND)
        refund["fields"][name] |= changed
        return refund

    return make


def misspelt_reviewer() -> dict[str, Any]:
    refund = copy.deepcopy(REFUND)
    refund["steps"]["review"]["roles"] = ["supprt"]
    return refund


# A definition that makes each of the guide's codes for what steps call happen, in its order.
CALLS_EXAMPLES: dict[str, Callable[[], dict[str, Any]]] = {
    "UNKNOWN_CONTRACT": lambda: refund_with(activity="payments.refund@3"),
    "WRONG_KIND": check_as_activity,
    "UNKNOWN_PLAN": lambda: settled(plan="refund-order@2"),
    "UNKNOWN_INPUT": lambda: refund_with(
        inputs={"order_id": {"var": "order_id"}, "amout": {"var": "amount"}}
    ),
    "MISSING_INPUT": lambda: refund_with(inputs={"order_id": {"var": "order_id"}}),
    "ENGINE_INPUT": lambda: refund_with(
        inputs={**REFUND["steps"]["pay"]["inputs"], "idempotency_key": "mine"}
    ),
    "UNKNOWN_ROLE": misspelt_reviewer,
    "UNKNOWN_SOURCE": with_field("amount", source="untrusted:custmer"),
    "UNKNOWN_SYSTEM": with_field("order_id", system="ordrs"),
    "EXPRESSION_INVALID": misspelt_acceptance,
    "APPROVAL_REQUIRED": lambda: refund_with(approval=None),
    "APPROVAL_ROLE": lambda: refund_with(
        approval={**REFUND["steps"]["pay"]["approval"], "roles": ["support-lead", "adjuster"]}
    ),
}


def test_the_guide_lists_every_code_for_what_steps_call() -> None:
    assert [code for code, _, _ in guide_table(2)] == list(CALLS_EXAMPLES)


@pytest.mark.parametrize(("code", "kind", "says"), guide_table(2))
def test_the_guides_table_of_calls_is_what_validate_case_says(
    code: str, kind: str, says: str
) -> None:
    found = [i for i in checked_with(CALLS_EXAMPLES[code](), PLANS) if i.code == code]
    assert [issue.severity for issue in found] == [kind]
    if says != "as above":
        assert [issue.message for issue in found] == [says]


def test_a_message_quotes_only_the_literal_that_is_wrong() -> None:
    # A literal the author wrote may be quoted when it is the mistake; titles, an approval's
    # reason and any other literal never are (brief, D35).
    for make in CALLS_EXAMPLES.values():
        for issue in checked_with(marked(make()), PLANS):
            assert "TITLE-" not in issue.message, issue
    claim = guide_json(0)
    claim["steps"]["pay"]["when"] = {
        "and": [
            {"==": [{"var": "assess.outcome"}, "acept"]},
            {">": [{"var": "payout"}, 987654]},
        ]
    }
    [issue] = issues(claim)
    assert '"acept"' in issue.message and "987654" not in issue.message


# --- 10c, slice 1: where each value comes from ---


def estimated_claim() -> dict[str, Any]:
    """The guide's claim, paying the lesser of the payout and the customer's own estimate."""
    claim = guide_json(0)
    claim["fields"] |= guide_json(3)
    claim["steps"]["pay"]["inputs"] |= guide_json(4)
    return claim


def test_an_untrusted_value_is_refused_where_only_trusted_ones_go() -> None:
    # The guide's example, word for word, line breaks aside.
    shown = guide_section().split("so the check refuses it:\n\n```\n")[1].split("```")[0]
    assert printed(issues(estimated_claim())) == " ".join(shown.split())
    # The proof: run as it is, the step fails with the same reason, before the payment is called.
    run = run_case(
        estimated_claim(),
        file=CLAIM_FILE | {"estimate": 1},
        answers=[ACCEPTED, ("pay", "approve", "sam")],
        people=CLAIM_PEOPLE,
    )
    assert run.needs_attention == [
        (
            "pay#1: payments.refund@2 takes amount only from a system or a person, never from "
            "untrusted data, and this value comes from estimate (system:opener, untrusted:customer)"
        )
    ]


def claim_writing_to(to_customer: Any) -> dict[str, Any]:
    """The guide's claim, drafting a letter to `to_customer` once the customer is checked."""
    claim = guide_json(0)
    claim["steps"]["write"] = {
        "kind": "activity",
        "display": {"title": "Write to the customer"},
        "activity": "letters.draft@2",
        "requires": ["checked"],
        "inputs": {"to_customer": to_customer, "template": "claim-received"},
    }
    return claim


def test_one_pass_gives_the_sources_the_run_records() -> None:
    # An output carries its contract's source; one declaring none is untrusted:undeclared
    # (brief, D29). A value computed from several fields comes from all of them.
    computed = {"cat": [{"var": "check.status"}, " ", {"var": "check.contact_email"}]}
    reason = (
        "letters.draft@2 takes to_customer only from a system or a person, never from untrusted "
        "data, and this value comes from check.contact_email (untrusted:undeclared)"
    )
    assert issues(claim_writing_to(computed)) == [
        Issue(
            "steps.write.inputs.to_customer",
            "INPUT_POLICY",
            f"{reason}: use a value a system or a person gave",
        )
    ]
    run = run_case(claim_writing_to(computed), file=CLAIM_FILE, answers=[], people=CLAIM_PEOPLE)
    assert run.needs_attention == [f"write#1: {reason}"]
    # The check's sources are the run's: what passes one passes the other, as the history says.
    trusted = {"cat": [{"var": "check.status"}, " ", {"string": [{"var": "customer_id"}]}]}
    assert issues(claim_writing_to(trusted)) == []
    run = run_case(claim_writing_to(trusted), file=CLAIM_FILE, answers=[], people=CLAIM_PEOPLE)
    assert any(
        "letters.draft@2 (to_customer from system:kyc, system:opener; template from the case)"
        in line
        for line in run.history
    )


class RecordInput(BaseModel):
    amount: Annotated[Decimal, only_from("opener")]  # only an amount the opening system gave


class RecordOutput(BaseModel):
    entry_id: str


def with_ledger(taking: type[BaseModel] | None = None) -> Catalog:
    """The development catalog, and `ledger.record@1`, taking only an amount the opener gave, or
    what `taking` says."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(
        ActivityContract(
            name="ledger.record",
            version=1,
            input=taking or RecordInput,
            output=RecordOutput,
            risk="low",
            effect="compute",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None,
            outcomes=[],
            display=ContractDisplay(title="Record", description="Record an amount"),
        )
    )
    return catalog


def refund_recording(amount: Any) -> dict[str, Any]:
    """The quickstart's refund, recording `amount` in the ledger once reviewed."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the request"},
        "activity": "ledger.record@1",
        "requires": ["review"],
        "inputs": {"amount": amount},
    }
    return refund


def test_who_opens_the_case_decides_only_a_warning() -> None:
    ledger = with_ledger()
    # A value given at the opening passes `only_from("opener")` when a system opens the case, and
    # not when a person does: the check can't know who will, so it warns (brief, D36).
    opened = refund_recording({"var": "amount"})
    assert validate_case(parse_case(opened), ledger) == [
        Issue(
            "steps.record.inputs.amount",
            "OPENER_DECIDES",
            "ledger.record@1 takes amount only from opener, and this value comes from amount "
            "(the opener), which is refused when a person opens the case: open it only from a "
            "system, or give amount a value a system gave",
            "warning",
        )
    ]
    record = {"ledger.record@1": lambda inputs: {"entry_id": "led-1"}}
    by_a_system = small_refund(opened, catalog=ledger, activities=record)
    assert by_a_system.needs_attention == []
    by_ana = small_refund(opened, catalog=ledger, activities=record, opened_by="ana")
    assert by_ana.needs_attention == [
        (
            "record#1: ledger.record@1 takes amount only from opener, and this value comes from "
            "amount (person:ana)"
        )
    ]
    # Refused whoever opens it, it is an error: the reviewer's amount comes from a person.
    [refused] = validate_case(parse_case(refund_recording({"var": "approved_amount"})), ledger)
    assert refused == Issue(
        "steps.record.inputs.amount",
        "INPUT_POLICY",
        "ledger.record@1 takes amount only from opener, and this value comes from "
        "approved_amount (person:answering review): use a value opener gave",
    )


# --- 10c, slice 2: into plan steps ---


def settled_from_the_estimate() -> dict[str, Any]:
    """The refund through `refund-order@1`, its amount the customer's, declared untrusted."""
    refund = settled(inputs={"order_id": {"var": "order_id"}, "amount": {"var": "amount"}})
    refund["fields"]["amount"]["source"] = "untrusted:customer"
    return refund


def test_a_plan_step_carries_the_cases_sources_into_its_plan() -> None:
    # Refused at the case's input, before the plan runs, naming the plan's state (brief, D36).
    assert checked_with(settled_from_the_estimate(), PLANS) == [
        Issue(
            "steps.settle.inputs.amount",
            "INPUT_POLICY",
            "refund-order@1, in its state pay: payments.refund@2 takes amount only from a system "
            "or a person, never from untrusted data, and this value comes from amount (the "
            "opener, untrusted:customer): use a value a system or a person gave",
        )
    ]
    # The proof: run as it is, the plan starts, asks for its approval, and stops at `pay`.
    run = run_case(
        settled_from_the_estimate(),
        file=SMALL,
        answers=[REVIEWED],
        people=PEOPLE,
        plans=PLANS,
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    assert run.needs_attention == [
        (
            "settle#1: refund-order@1 stopped: payments.refund@2 takes amount only from a system "
            "or a person, never from untrusted data, and this value comes from amount "
            "(system:opener, untrusted:customer)"
        )
    ]


def test_a_plans_own_mark_is_the_plans_issue() -> None:
    # A plan declaring its own field untrusted refuses it wherever it is published (layer 3's
    # `validate`): the case's check doesn't say it again, since the case can't change it.
    marked_plan = refund_order()
    marked_plan["fields"]["amount"]["source"] = "untrusted:customer"
    assert checked_with(settled(), {"refund-order@1": marked_plan}) == []
    # A field a person sets in the plan comes from them: trusted, the case's input or not.
    given = settled(plan="review-and-pay@1", inputs={"order_id": {"var": "order_id"}})
    assert checked_with(given, {"review-and-pay@1": review_and_pay()}) == []


# --- 10c, slice 3: references ---


def claim_lettering(customer: Any) -> dict[str, Any]:
    """The guide's claim, drafting a letter through `letters.draft@3` to `customer`."""
    claim = claim_writing_to("unused")
    claim["steps"]["write"] |= {
        "activity": "letters.draft@3",
        "inputs": {"customer": customer, "template": "claim-received"},
    }
    return claim


def test_a_reference_goes_only_where_its_system_is_expected() -> None:
    reason = (
        "letters.draft@3 takes customer as a reference to crm, and is given order_id, a "
        "reference to orders"
    )
    wrong_system = claim_lettering({"var": "order_id"})
    assert issues(wrong_system) == [
        Issue(
            "steps.write.inputs.customer",
            "REFERENCE",
            f"{reason}: give it a reference to crm, read as it is",
        )
    ]
    # The proof: run as it is, the step fails before the letter is drafted (brief, D30).
    run = run_case(wrong_system, file=CLAIM_FILE, answers=[], people=CLAIM_PEOPLE)
    assert run.needs_attention == [f"write#1: {reason}"]
    # A computed value has no system, whatever it looks like.
    computed = claim_lettering({"cat": ["cus-", {"string": [{"var": "order_id"}]}]})
    [refused] = issues(computed)
    assert refused.message == (
        "letters.draft@3 takes customer as a reference to crm, and is given a computed value: "
        "give it a reference to crm, read as it is"
    )


def test_a_plan_steps_reference_field_takes_a_reference_of_its_system() -> None:
    made_up = {"cat": ["ord-", {"string": [{"var": "amount"}]}]}
    settle = settled(inputs={"order_id": made_up, "amount": {"var": "approved_amount"}})
    reason = "refund-order@1 takes order_id as a reference to orders, and is given a computed value"
    assert checked_with(settle, PLANS) == [
        Issue(
            "steps.settle.inputs.order_id",
            "REFERENCE",
            f"{reason}: give it a reference to orders, read as it is",
        )
    ]
    # The proof: run as it is, the step fails before the plan starts (G7).
    run = run_case(settle, file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=PLANS)
    assert run.needs_attention == [f"settle#1: {reason}"]


# --- 10c, slice 4: types ---


def test_an_input_is_given_the_type_it_takes() -> None:
    text = refund_with(inputs={"order_id": {"var": "order_id"}, "amount": "40"})
    assert issues(text) == [
        Issue(
            "steps.pay.inputs.amount",
            "INPUT_TYPE",
            "payments.refund@2 takes amount as a number, and is given a string: give it a number",
        )
    ]
    # The proof: run as it is, the text is refused, never paid as 40 (G6). Before 10c, it was.
    assert small_refund(text).needs_attention == [
        (
            "pay#1: payments.refund@2 doesn't take these inputs: amount: Input should be an "
            "instance of Decimal"
        )
    ]
    # A plan's field too: the plan doesn't start (G7).
    as_text = {"string": [{"var": "approved_amount"}]}
    settle = settled(inputs={"order_id": {"var": "order_id"}, "amount": as_text})
    assert checked_with(settle, PLANS) == [
        Issue(
            "steps.settle.inputs.amount",
            "INPUT_TYPE",
            "refund-order@1 takes amount as a number, and is given a string: give it a number",
        )
    ]
    run = run_case(settle, file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=PLANS)
    assert run.needs_attention == [
        "settle#1: refund-order@1 can't start: amount is a number, and is given a string"
    ]


class CountInput(BaseModel):
    amount: int  # a whole number: no value of a case is one


def test_an_input_no_value_of_a_case_fits_is_refused_at_registration() -> None:
    # A whole number: strict validation refuses a decimal for it, so no case could ever give it
    # one. Registration refuses the contract, as it refuses a float output (brief, D29) (brief,
    # D36), so no case can call it.
    with pytest.raises(ValueError, match="input amount is int, which no value of a case is"):
        with_ledger(taking=CountInput)


def test_a_plan_field_given_only_literals_has_no_sources() -> None:
    literal = settled(inputs={"order_id": {"var": "order_id"}, "amount": Decimal(40)})
    assert checked_with(literal, PLANS) == [
        Issue(
            "steps.settle.inputs.amount",
            "NO_SOURCES",
            "refund-order@1 takes amount from the case, and is given only values written in the "
            "definition, which come from nobody: give it a field of the case file",
        )
    ]
    run = run_case(literal, file=SMALL, answers=[REVIEWED], people=PEOPLE, plans=PLANS)
    assert run.needs_attention == [
        (
            "settle#1: refund-order@1 can't start: amount comes with no sources: say where its "
            "value came from, such as system:opener"
        )
    ]


# --- 10c, slice 5: sensitive values and approvers ---


def claim_checking_national_id() -> dict[str, Any]:
    """The guide's claim, its workflow step given the customer's national ID, a sensitive field."""
    claim = guide_json(0)
    claim["fields"]["national_id"] = {
        "type": "string",
        "sensitive": True,
        "visible_to": ["claims-sensitive"],
        "display": {"title": "National ID"},
    }
    claim["steps"]["check"]["inputs"] = {"customer_id": {"var": "national_id"}}
    return claim


def test_a_workflow_step_is_never_given_a_sensitive_value() -> None:
    reason = (
        "kyc.check@1 is a workflow step and can't be given national_id, a sensitive field: its "
        "worker doesn't hold the case's key"
    )
    assert issues(claim_checking_national_id()) == [
        Issue(
            "steps.check.inputs.customer_id",
            "SENSITIVE_TO_WORKFLOW",
            f"{reason}; give it a value that isn't sensitive",
        )
    ]
    # The proof: run as it is, the step fails before the workflow starts (brief, D31).
    run = run_case(
        claim_checking_national_id(),
        file=CLAIM_FILE | {"national_id": "1850775123456"},
        answers=[],
        people=CLAIM_PEOPLE,
    )
    assert run.needs_attention == [f"check#1: {reason}"]


def claim_paying_below_a_fraud_score() -> dict[str, Any]:
    """The guide's claim, paid only below a fraud score only the fraud team sees."""
    claim = guide_json(0)
    claim["fields"]["fraud_score"] = {
        "type": "number",
        "visible_to": ["fraud"],
        "display": {"title": "Fraud score"},
    }
    claim["steps"]["pay"]["when"] = {"<": [{"var": "fraud_score"}, 50]}
    return claim


def test_an_approver_who_cannot_see_is_warned() -> None:
    assert issues(claim_paying_below_a_fraud_score()) == [
        Issue(
            "steps.pay.approval.roles",
            "APPROVER_CANT_SEE",
            "support-lead can't see fraud_score, which pay reads: a person approving pay needs "
            "fraud as well; let support-lead see fraud_score, or approve with a role that does",
            "warning",
        )
    ]

    # A warning, not an error: who holds which roles is what the check can't know (brief, D34).
    # Sam holds support-lead only, and is refused; Lee holds fraud too, and the claim is paid.
    def paid(roles: list[str]) -> CaseRun:
        return run_case(
            claim_paying_below_a_fraud_score(),
            file=CLAIM_FILE | {"fraud_score": 10},
            answers=[ACCEPTED, ("pay", "approve", "lee")],
            people={**CLAIM_PEOPLE, "lee": roles},
        )

    with pytest.raises(AnswerRefused, match="^lee can't see fraud_score, which pay reads"):
        paid(["support-lead"])
    assert paid(["support-lead", "fraud"]).reached("pay")


# --- 10c, slice 6: one cause, one issue; the guide ---


def test_an_input_has_one_data_flow_issue() -> None:
    # The first the runtime meets. A reference refused is not asked where it comes from.
    claim = claim_lettering({"var": "estimate_ref"})
    claim["fields"]["estimate_ref"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "Customer's reference"},
    }
    assert [issue.code for issue in issues(claim)] == ["REFERENCE"]
    run = run_case(
        claim, file=CLAIM_FILE | {"estimate_ref": "cus-1"}, answers=[], people=CLAIM_PEOPLE
    )
    [refused] = run.needs_attention
    assert "as a reference to crm" in refused
    # A sensitive value from an untrusted source: the policy first, as `checked_inputs` is asked
    # before the workflow's own refusal.
    claim = claim_checking_national_id()
    claim["fields"]["national_id"]["source"] = "untrusted:customer"
    assert [issue.code for issue in issues(claim)] == ["INPUT_POLICY"]
    # An input whose expression is refused is not asked again, nor one of a missing contract.
    misspelt = refund_with(inputs={"order_id": {"var": "order_id"}, "amount": {"var": "amout"}})
    assert [issue.code for issue in issues(misspelt)] == ["EXPRESSION_INVALID"]
    missing = refund_with(activity="payments.refund@3", inputs={"amount": "40"})
    assert [issue.code for issue in issues(missing)] == ["UNKNOWN_CONTRACT"]
    no_plan = settled(inputs={"order_id": {"var": "order_id"}, "amount": "40"})
    assert [issue.code for issue in issues(no_plan)] == ["UNKNOWN_PLAN"]
    # A plan step refused when it starts runs nothing inside its plan: no in-plan issue.
    made_up = {"cat": ["ord-", {"string": [{"var": "amount"}]}]}
    both = settled_from_the_estimate()
    both["steps"]["settle"]["inputs"]["order_id"] = made_up
    assert [issue.code for issue in checked_with(both, PLANS)] == ["REFERENCE"]


FLOW_EXAMPLES: dict[str, Callable[[], dict[str, Any]]] = {
    "REFERENCE": lambda: claim_lettering({"var": "order_id"}),
    "INPUT_POLICY": estimated_claim,
    "OPENER_DECIDES": lambda: refund_recording({"var": "amount"}),
    "INPUT_TYPE": lambda: refund_with(inputs={"order_id": {"var": "order_id"}, "amount": "40"}),
    "NO_SOURCES": lambda: settled(inputs={"order_id": {"var": "order_id"}, "amount": Decimal(40)}),
    "SENSITIVE_TO_WORKFLOW": claim_checking_national_id,
    "APPROVER_CANT_SEE": claim_paying_below_a_fraud_score,
}


def flow_issues(definition: dict[str, Any]) -> list[Issue]:
    """The issues of `definition`, read with the ledger beside the catalog and the guide's plans."""
    return validate_case(parse_case(definition), with_ledger(), plans=PLANS)


def test_the_guide_lists_every_code_for_data_flow() -> None:
    assert [code for code, _, _ in guide_table(3)] == list(FLOW_EXAMPLES)


@pytest.mark.parametrize(("code", "kind", "says"), guide_table(3))
def test_the_guides_table_of_data_flow_is_what_validate_case_says(
    code: str, kind: str, says: str
) -> None:
    found = [issue for issue in flow_issues(FLOW_EXAMPLES[code]()) if issue.code == code]
    assert [issue.severity for issue in found] == [kind]
    if says != "as above":
        assert [issue.message for issue in found] == [says]


def test_no_data_flow_message_quotes_a_value() -> None:
    # Fields, types, sources and roles, never a title, a literal or who opens the case
    # (brief, D30) (brief, D35).
    for make in FLOW_EXAMPLES.values():
        for issue in flow_issues(marked(make())):
            assert "TITLE-" not in issue.message and "person:opening" not in issue.message, issue
    text = refund_with(inputs={"order_id": {"var": "order_id"}, "amount": "987654"})
    literal = settled(inputs={"order_id": {"var": "order_id"}, "amount": Decimal(987654)})
    for definition in (text, literal):
        [issue] = flow_issues(definition)
        assert "987654" not in issue.message


class StatusInput(BaseModel):
    amount: Decimal
    status: Annotated[str, only_from("kyc")]  # only what the KYC system says


def test_an_outcome_comes_from_its_contract_not_its_system() -> None:
    # The output `check.status` comes from what the contract declares, system:kyc; the workflow's
    # outcome from the contract itself, system:kyc.check@1 (brief, D29). The run records the same.
    ledger = with_ledger(taking=StatusInput)
    record = {"ledger.record@1": lambda inputs: {"entry_id": "led-1"}}

    def recording(status: str) -> dict[str, Any]:
        claim = guide_json(0)
        claim["steps"]["record"] = {
            "kind": "activity",
            "display": {"title": "Record the check"},
            "activity": "ledger.record@1",
            "requires": ["checked", "assessed"],
            "inputs": {"amount": {"var": "payout"}, "status": {"var": status}},
        }
        return claim

    def run(status: str) -> CaseRun:
        return run_case(
            recording(status),
            file=CLAIM_FILE,
            answers=[ACCEPTED],
            people=CLAIM_PEOPLE,
            catalog=ledger,
            activities=record,
        )

    assert validate_case(parse_case(recording("check.status")), ledger) == []
    assert (
        "scheduled record#1: ledger.record@1 (amount from person:ana; status from system:kyc)"
        in run("check.status").history
    )
    reason = (
        "ledger.record@1 takes status only from kyc, and this value comes from check.outcome "
        "(system:kyc.check@1)"
    )
    assert validate_case(parse_case(recording("check.outcome")), ledger) == [
        Issue("steps.record.inputs.status", "INPUT_POLICY", f"{reason}: use a value kyc gave")
    ]
    assert run("check.outcome").needs_attention == [f"record#1: {reason}"]


# --- 10c, tutor review: a Literal input ---


class PriorityInput(BaseModel):
    amount: Decimal
    priority: Literal["low", "high"]  # one of these texts, exactly


def refund_flagging(priority: Any) -> dict[str, Any]:
    """The refund, recording the request in the ledger with `priority`."""
    refund = refund_recording({"var": "amount"})
    refund["steps"]["record"]["inputs"]["priority"] = priority
    return refund


def test_a_literal_input_takes_one_of_its_texts() -> None:
    ledger = with_ledger(taking=PriorityInput)
    calls: list[dict[str, Any]] = []

    def record(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        return {"entry_id": "led-1"}

    def run(priority: Any) -> CaseRun:
        calls.clear()
        return small_refund(
            refund_flagging(priority), catalog=ledger, activities={"ledger.record@1": record}
        )

    # One of its texts: no issue, and the activity is called with it.
    assert validate_case(parse_case(refund_flagging("high")), ledger) == []
    assert run("high").needs_attention == [] and calls == [
        {"amount": Decimal(40), "priority": "high"}
    ]
    # Another text is the mistake, so the message names it (brief, D35); run, the step fails.
    assert validate_case(parse_case(refund_flagging("urgent")), ledger) == [
        Issue(
            "steps.record.inputs.priority",
            "INPUT_TYPE",
            'ledger.record@1 takes priority as one of low or high, and is given "urgent": give it '
            "one of low or high",
        )
    ]
    [refused] = run("urgent").needs_attention
    assert refused.startswith("record#1: ledger.record@1 doesn't take these inputs: priority:")
    assert calls == []
    # A number never fits.
    assert validate_case(parse_case(refund_flagging({"var": "amount"})), ledger) == [
        Issue(
            "steps.record.inputs.priority",
            "INPUT_TYPE",
            "ledger.record@1 takes priority as one of low or high, and is given a number: give it "
            "one of low or high",
        )
    ]
    [refused] = run({"var": "amount"}).needs_attention
    assert refused.startswith("record#1: ledger.record@1 doesn't take these inputs: priority:")
    # A text field may or may not be one of them: that depends on the value, so no issue.
    refund = refund_flagging({"var": "order_id"})
    assert validate_case(parse_case(refund), ledger) == []


class DecisionInput(BaseModel):
    amount: Decimal
    decision: Literal["approve", "reject", "hold"]  # what the review decided, or a hold


def test_an_outcome_or_a_boolean_given_to_a_literal_input() -> None:
    # An outcome all of whose outcomes are among the texts always fits: no issue, and it runs.
    ledger = with_ledger(taking=DecisionInput)
    record = {"ledger.record@1": lambda inputs: {"entry_id": "led-1"}}
    decided = refund_recording({"var": "amount"})
    decided["steps"]["record"]["inputs"]["decision"] = {"var": "review.outcome"}
    assert validate_case(parse_case(decided), ledger) == []
    assert small_refund(decided, catalog=ledger, activities=record).needs_attention == []
    # An outcome with others may fit or not, depending on the answer: no issue.
    ledger = with_ledger(taking=PriorityInput)
    flagged = refund_flagging({"var": "review.outcome"})
    assert validate_case(parse_case(flagged), ledger) == []
    # A boolean never fits; run, the step fails.
    as_boolean = refund_flagging(True)
    assert validate_case(parse_case(as_boolean), ledger) == [
        Issue(
            "steps.record.inputs.priority",
            "INPUT_TYPE",
            "ledger.record@1 takes priority as one of low or high, and is given a boolean: give "
            "it one of low or high",
        )
    ]
    run = small_refund(as_boolean, catalog=ledger, activities=record)
    [refused] = run.needs_attention
    assert refused.startswith("record#1: ledger.record@1 doesn't take these inputs: priority:")


# --- Layer 10d: teaching warnings ---

WARNINGS = "### What the check warns about"


def warning_output(index: int) -> str:
    """The plain-text block `index` of the guide's warnings (one whose fence names no language,
    as the guide prints output), its line breaks aside."""
    blocks: list[tuple[str, list[str]]] = []  # each block's language, and its lines
    inside = False
    for line in GUIDE.read_text().split(WARNINGS)[1].splitlines():
        if line.startswith("```"):
            if not inside:
                blocks.append((line[3:], []))
            inside = not inside
        elif inside:
            blocks[-1][1].append(line)
    plain = [lines for language, lines in blocks if language == ""]
    return " ".join(" ".join(plain[index]).split())


def without_call_customer() -> dict[str, Any]:
    """The quickstart's refund, with nothing reacting to a declined refund."""
    refund = copy.deepcopy(REFUND)
    del refund["steps"]["call_customer"]
    return refund


PAY_UNREAD = Issue(
    "steps.pay",
    "OUTCOME_UNREAD",
    "pay may end declined, and no condition tells that from done, so the case goes on and nobody "
    "is told: add a step that runs when pay.outcome is declined",
    "warning",
)


def test_an_outcome_nobody_reads_is_a_warning() -> None:
    # The guide's output, word for word, line breaks aside.
    assert printed(issues(without_call_customer())) == warning_output(0)
    assert issues(without_call_customer()) == [PAY_UNREAD]
    # The surprise it warns about: declined, the case closes, and nobody is told.
    run = run_case(
        without_call_customer(),
        file=SMALL,
        answers=[REVIEWED],
        people=PEOPLE,
        activities={"payments.refund@2": declines},
    )
    assert run.history[-2:] == ["pay#1 gave declined", "closed: nothing left to do"]
    assert run.waiting_for == [] and run.needs_attention == []


def holding() -> Catalog:
    """The development catalog, and `payments.refund@3`: `@2`, able to end `held` as well."""
    catalog = copy.deepcopy(CATALOG)
    refund = dict(payments_refund)
    refund["version"] = 3
    refund["outcomes"] = ["declined", "held"]
    refund["display"] = ContractDisplay(
        title="Refund a customer",
        description="Refunds an order through the payment provider.",
        outcomes={"declined": "Declined by the provider", "held": "Held for review"},
    )
    catalog.register(ActivityContract(**refund))
    return catalog


def paying_with_held(definition: dict[str, Any]) -> dict[str, Any]:
    definition["steps"]["pay"]["activity"] = "payments.refund@3"
    return definition


def test_each_outcome_is_read_on_its_own() -> None:
    # call_customer tells declined from done, and nothing tells held: held is unread.
    catalog = holding()
    refund = paying_with_held(copy.deepcopy(REFUND))
    assert validate_case(parse_case(refund), catalog) == [
        Issue(
            "steps.pay",
            "OUTCOME_UNREAD",
            "pay may end held, and no condition tells that from done, so the case goes on and "
            "nobody is told: add a step that runs when pay.outcome is held",
            "warning",
        )
    ]
    # Neither read: one issue for the step, naming both.
    assert validate_case(parse_case(paying_with_held(without_call_customer())), catalog) == [
        Issue(
            "steps.pay",
            "OUTCOME_UNREAD",
            "pay may end declined or held, and no condition tells them from done, so the case goes "
            "on and nobody is told: add a step that runs when pay.outcome is one of them",
            "warning",
        )
    ]


def reacting_when(when: Any) -> dict[str, Any]:
    """The quickstart's refund, `call_customer` running on `when`."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["call_customer"]["when"] = when
    return refund


def test_a_condition_reads_an_outcome_when_it_tells_it_from_done() -> None:
    outcome = {"var": "pay.outcome"}
    read = [
        {"!=": [outcome, "declined"]},  # true for done, false for declined
        {"!=": [outcome, "done"]},  # done compared: every outcome told from it
        {"==": ["done", outcome]},  # either side
        {"in": [outcome, ["declined"]]},
        {"in": [outcome, ["done"]]},
        {"==": [{"cat": [outcome]}, "declined"]},  # read as a value: the check doesn't guess
    ]
    for reading in read:
        assert issues(reacting_when(reading)) == [], reading
    # Reading another step's outcome, or only whether pay ended, tells nothing about pay's.
    unread = [
        {"==": [{"var": "review.outcome"}, "approve"]},
        {"exists": "pay.outcome"},
    ]
    for not_reading in unread:
        assert issues(reacting_when(not_reading)) == [PAY_UNREAD], not_reading
    # `in` reads only the outcomes it lists: held stays unread.
    listing = paying_with_held(reacting_when({"in": [{"var": "pay.outcome"}, ["declined"]]}))
    assert [issue.message for issue in validate_case(parse_case(listing), holding())] == [
        (
            "pay may end held, and no condition tells that from done, so the case goes on and "
            "nobody is told: add a step that runs when pay.outcome is held"
        )
    ]
    # So does `!=`, and a comparison written either way round: each tells declined, not held.
    for when in (
        {"!=": [{"var": "pay.outcome"}, "declined"]},
        {"==": ["declined", {"var": "pay.outcome"}]},
    ):
        told = paying_with_held(reacting_when(when))
        assert [issue.code for issue in validate_case(parse_case(told), holding())] == [
            "OUTCOME_UNREAD"
        ], when


def unread_settle() -> dict[str, Any]:
    """The refund with its plan step, and nothing reacting to the plan failing."""
    refund = settled()
    del refund["steps"]["call_customer"]
    return refund


def test_a_plan_that_fails_unread_is_a_warning() -> None:
    assert checked_with(unread_settle(), PLANS) == [
        Issue(
            "steps.settle",
            "OUTCOME_UNREAD",
            "settle may end failed, and no condition tells that from done, so the case goes on "
            "and nobody is told: add a step that runs when settle.outcome is failed",
            "warning",
        )
    ]
    # The surprise: Sam rejects the refund inside the plan, and the case closes, nobody told.
    run = run_case(
        unread_settle(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans=PLANS,
        plan_answers={"settle": [("approve_refund", "reject", "sam")]},
    )
    assert run.history[-2:] == ["settle#1 gave failed", "closed: nothing left to do"]
    assert run.needs_attention == []


def test_an_outcome_a_person_chose_is_never_unread() -> None:
    # The claim's deny reaches nothing and no condition reads it: that is how a "no" is written,
    # and the adjuster who chose it knows. Its check, a workflow step, ends only done.
    claim = guide_json(0)
    assert "reaches" not in claim["steps"]["assess"]["outcomes"]["deny"]
    assert issues(claim) == []


def refund_without_when() -> dict[str, Any]:
    """The quickstart's refund, `pay` running whatever the review said."""
    refund = copy.deepcopy(REFUND)
    del refund["steps"]["pay"]["when"]
    return refund


def test_a_value_read_before_it_is_surely_set_is_a_warning() -> None:
    # The guide's output, word for word, line breaks aside.
    assert printed(issues(refund_without_when())) == warning_output(1)
    # The surprise: the review rejected, pay still starts, reads approved_amount, and fails.
    run = run_case(
        refund_without_when(),
        file=SMALL,
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "pay#1: pay's approval condition approved_amount > 100 can't be evaluated: "
            "approved_amount has no value"
        )
    ]
    assert not run.closed


def refund_paying_when(when: Any) -> dict[str, Any]:
    refund = copy.deepcopy(REFUND)
    refund["steps"]["pay"]["when"] = when
    return refund


APPROVED = {"==": [{"var": "review.outcome"}, "approve"]}
AMOUNT_UNSET = (
    "pay reads approved_amount, which only review's approve sets, and pay may run after review is "
    "answered otherwise: then pay fails and needs attention: run pay only when review.outcome is "
    "approve"
)


def test_a_guard_in_the_when_makes_a_value_surely_set() -> None:
    outcome = {"var": "review.outcome"}
    guards = [
        APPROVED,
        {"!=": [outcome, "reject"]},  # review has two outcomes: not reject is approve
        {"in": [outcome, ["approve"]]},
        {"exists": "approved_amount"},
        {"and": [{">": [{"var": "amount"}, 0]}, APPROVED]},  # a part of an `and`, once true
        {"if": [APPROVED, {">": [{"var": "amount"}, 0]}, False]},  # true only through its branch
    ]
    for guard in guards:
        assert issues(refund_paying_when(guard)) == [], guard
    # What guards nothing: a condition on another value, or an `if` that may be true otherwise.
    for no_guard in (
        {">": [{"var": "amount"}, 0]},
        {"if": [APPROVED, True, True]},
        {"in": [outcome, ["approve", "reject"]]},
    ):
        found = issues(refund_paying_when(no_guard))
        assert found == [
            Issue("steps.pay.approval.when", "MAY_BE_UNSET", AMOUNT_UNSET, "warning")
        ], no_guard


def test_and_reads_every_part_so_a_part_guards_nothing_beside_it() -> None:
    # The runtime evaluates every part of an `and` (brief, D20): a rejected review fails pay's
    # condition, though its first part is already false.
    both_parts = {"and": [APPROVED, {">": [{"var": "approved_amount"}, 0]}]}
    assert issues(refund_paying_when(both_parts)) == [
        Issue("steps.pay.when", "MAY_BE_UNSET", AMOUNT_UNSET, "warning")
    ]
    run = run_case(
        refund_paying_when(both_parts),
        file=SMALL,
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    [failed] = run.needs_attention
    assert failed.endswith("approved_amount has no value")
    # Inside an `if`, the branch is read only once its condition held: no issue.
    in_if = {"if": [APPROVED, {">": [{"var": "approved_amount"}, 0]}, False]}
    assert issues(refund_paying_when(in_if)) == []
    rejected = run_case(
        refund_paying_when(in_if),
        file=SMALL,
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    assert rejected.closed and rejected.needs_attention == []


def old_refund_fresh() -> dict[str, Any]:
    """The case-data guide's `refund_fresh` as it was before 10d: `pay`'s `when` reads the
    lookup's status, and nothing guards the approved amount."""
    guide = (ROOT / "docs" / "guides" / "case-data.md").read_text()
    section = guide.split("### Saying how fresh a step needs its facts")[1]
    steps = json.loads(
        "{" + section.split("```json\n")[1].split("```")[0] + "}", parse_float=Decimal
    )
    refund = copy.deepcopy(REFUND)
    refund["steps"] = {"check_order": steps["check_order"], **refund["steps"]}
    refund["steps"]["pay"] = steps["pay"]
    refund["steps"]["pay"]["when"] = {"==": [{"var": "check_order.status"}, "delivered"]}
    return refund


def gives(outcome: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def giving(inputs: dict[str, Any]) -> dict[str, Any]:
        raise Outcome(outcome)

    return giving


def test_the_old_refund_fresh_reads_two_values_that_may_be_unset() -> None:
    assert issues(old_refund_fresh()) == [
        Issue(
            "steps.pay.when",
            "MAY_BE_UNSET",
            "pay reads check_order.status, which check_order gives only when done, and "
            "check_order may end not_found: then pay fails and needs attention: read it only "
            "when check_order.outcome is done",
            "warning",
        ),
        Issue("steps.pay.approval.when", "MAY_BE_UNSET", AMOUNT_UNSET, "warning"),
    ]
    # Each surprise, run: the order not found, and the review rejected.
    not_found = run_case(
        old_refund_fresh(),
        file=SMALL,
        answers=[REVIEWED],
        people=PEOPLE,
        activities={"orders.lookup@2": gives("not_found")},
    )
    [failed] = not_found.needs_attention
    assert failed.endswith("check_order.status has no value")
    rejected = run_case(
        old_refund_fresh(),
        file=SMALL,
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
        activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
    )
    [failed] = rejected.needs_attention
    assert failed.endswith("approved_amount has no value")
    # As the guide now writes it, neither: the status read only once the lookup is done.
    assert issues(refund_fresh_as_guided()) == []


def refund_fresh_as_guided() -> dict[str, Any]:
    refund = old_refund_fresh()
    guide = (ROOT / "docs" / "guides" / "case-data.md").read_text()
    section = guide.split("### Saying how fresh a step needs its facts")[1]
    steps = json.loads(
        "{" + section.split("```json\n")[1].split("```")[0] + "}", parse_float=Decimal
    )
    refund["steps"]["pay"] = steps["pay"]
    return refund


NOTED = {
    "kind": "task",
    "display": {"title": "Note the refund"},
    "roles": ["support"],
    "outcomes": {"noted": {"display": {"title": "Noted"}}},
}


def test_what_a_step_waits_for_says_what_is_set() -> None:
    # A value from a step not waited for: it may not be there yet.
    note = {**NOTED, "requires": ["review"], "when": {"==": [{"var": "pay.outcome"}, "done"]}}
    refund = copy.deepcopy(REFUND)
    refund["steps"]["note"] = note
    assert issues(refund) == [
        Issue(
            "steps.note.when",
            "MAY_BE_UNSET",
            "note reads pay.outcome, and doesn't wait for pay, which gives it: if note runs "
            "first, it fails and needs attention: require pay",
            "warning",
        )
    ]
    # Waited for through the step it requires: call_customer requires pay.
    refund["steps"]["note"] = {**note, "requires": ["call_customer"]}
    assert issues(refund) == []
    # A task every outcome of which sets the value: pay needs no guard.
    both_set = refund_without_when()
    both_set["steps"]["review"]["outcomes"]["reject"]["sets"] = ["approved_amount"]
    assert issues(both_set) == []


def test_a_milestone_only_setting_outcomes_reach_says_the_value_is_set() -> None:
    # The claim's pay requires assessed, which only accept reaches, and accept sets payout.
    assert issues(guide_json(0)) == []
    # If deny reaches assessed too, payout may be unset when pay runs.
    claim = guide_json(0)
    claim["steps"]["assess"]["outcomes"]["deny"]["reaches"] = ["assessed"]
    assert issues(claim) == [
        Issue(
            "steps.pay.inputs.amount",
            "MAY_BE_UNSET",
            "pay reads payout, which only assess's accept sets, and pay may run after assess is "
            "answered otherwise: then pay fails and needs attention: run pay only when "
            "assess.outcome is accept",
            "warning",
        )
    ]
    # Reached another way as well, by a fast track that sets nothing: payout may be unset.
    claim = guide_json(0)
    claim["steps"]["fast_track"] = {
        **NOTED,
        "roles": ["adjuster"],
        "requires": ["checked"],
        "outcomes": {"accept": {"display": {"title": "Accept"}, "reaches": ["assessed"]}},
    }
    assert [issue.message for issue in issues(claim)] == [
        (
            "pay reads payout, and doesn't wait for assess, which sets it: if pay runs first, it "
            "fails and needs attention: require assess"
        )
    ]


# --- 10d, slice 3: a value only a later step sets ---


class NoteInput(BaseModel):
    refund: str  # the refund's ID, to note it


class NoteOutput(BaseModel):
    # Declared, so a condition may read it: an undeclared value refuses what its step sends
    # (brief, D39).
    entry_id: Annotated[str, source("system:ledger")]


def noting() -> Catalog:
    """The development catalog, the ledger and letters systems, and `refunds.note@1`, which notes
    a refund by its ID."""
    catalog = copy.deepcopy(CATALOG)
    for system in ("ledger", "letters"):  # its outputs' sources name them (brief, D29)
        catalog.register_system(system)
    catalog.register(
        ActivityContract(
            name="refunds.note",
            version=1,
            input=NoteInput,
            output=NoteOutput,
            risk="low",
            effect="compute",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None,
            outcomes=[],
            display=ContractDisplay(title="Note a refund", description="Notes a refund's ID"),
        )
    )
    return catalog


def noting_before_paying(**notify: Any) -> dict[str, Any]:
    """The quickstart's refund, noting the refund's ID before paying it."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Note the refund"},
        "activity": "refunds.note@1",
        "inputs": {"refund": {"var": "pay.refund_id"}},
        **notify,
    }
    refund["sequence"] = ["review", "notify", "pay"]
    return refund


def test_a_value_only_a_later_step_sets_is_refused() -> None:
    catalog = noting()
    found = validate_case(parse_case(noting_before_paying()), catalog)
    # The guide's output, word for word, line breaks aside.
    assert printed(found) == warning_output(2)
    assert found[0].severity == "error"
    # The proof: notify fails when it starts, and again when an operator retries it.
    run = run_case(
        noting_before_paying(),
        file=SMALL,
        answers=[REVIEWED, retry("notify#1", "omar")],
        people={**PEOPLE, "omar": ["operations"]},
        catalog=catalog,
        activities={"refunds.note@1": lambda inputs: {"entry_id": "n-1"}},
    )
    # Its inputs' sources are asked first: a value nobody set has none.
    failed = "notify#1 failed: refund can't be evaluated: pay.refund_id has no known sources"
    assert [line for line in run.history if "failed" in line] == [failed, failed]
    assert "omar retried notify#1 as operations" in run.history
    assert not run.reached("pay")


def test_a_step_that_can_be_proposed_still_fails_every_time() -> None:
    # The value is set only once notify is done, and notify is done only after a run that read
    # it: no run of it ever succeeds, proposed or not, repeatable or not.
    catalog = noting()
    for proposed in (
        {"proposed_by": ["support"]},
        {"proposed_by": ["support"], "repeatable": True},
    ):
        definition = noting_before_paying(**proposed)
        [refused] = validate_case(parse_case(definition), catalog)
        assert refused.code == "SET_AFTER", proposed
        # Refused when proposed: it has run and isn't repeatable, or its inputs can't be read.
        with pytest.raises((ProposalRefused, InputRefused)):
            run_case(
                definition,
                file=SMALL,
                answers=[REVIEWED, propose("notify", "ana")],
                people=PEOPLE,
                catalog=catalog,
                activities={"refunds.note@1": lambda inputs: {"entry_id": "n-1"}},
            )


def test_a_condition_reads_only_the_branch_of_an_if_it_takes() -> None:
    # notify's condition reads how the payment ended only after an approved review: a rejected
    # one starts nothing, and the case closes. (The payment's outcome, which its contract vouches
    # for: the refund's ID is untrusted, and pay, requiring notify, would then be refused on its
    # inputs whenever it ran, brief, D43.)
    catalog = noting()
    noted = {"==": [{"var": "pay.outcome"}, "done"]}
    definition = noting_before_paying(when={"if": [APPROVED, noted, False]})
    assert validate_case(parse_case(definition), catalog) == [
        Issue(
            "steps.notify.when",
            "MAY_BE_UNSET",
            "notify reads pay.outcome, which only pay gives, and pay runs only after notify: "
            "when notify reads it, it fails and needs attention: read it in a step that comes "
            "after pay",
            "warning",
        )
    ]
    rejected = run_case(
        definition,
        file=SMALL,
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
        catalog=catalog,
        activities={"refunds.note@1": lambda inputs: {"entry_id": "n-1"}},
    )
    assert rejected.closed and rejected.needs_attention == []


def test_an_input_reads_every_value_it_names() -> None:
    # Where an input's value comes from is worked out from every value it names, an `if`'s other
    # branch and an `exists` included (brief, D36): a value nobody set fails it either way.
    catalog = noting()
    for refund in (
        {"if": [APPROVED, {"var": "pay.refund_id"}, "none"]},
        {"if": [{"exists": "pay.refund_id"}, "noted", "none"]},
    ):
        definition = noting_before_paying(inputs={"refund": refund})
        [refused] = validate_case(parse_case(definition), catalog)
        assert refused.code == "SET_AFTER", refund
        rejected = run_case(
            definition,
            file=SMALL,
            answers=[("review", "reject", "ana")],
            people=PEOPLE,
            catalog=catalog,
            activities={"refunds.note@1": lambda inputs: {"entry_id": "n-1"}},
        )
        assert rejected.needs_attention == [
            "notify#1: refund can't be evaluated: pay.refund_id has no known sources"
        ], refund


# --- 10d, slice 4: a max_age that can only end in attention ---


def refund_needing_fresh(field: str) -> dict[str, Any]:
    """The quickstart's refund, `pay` needing `field` at most a day old."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["pay"]["max_age"] = {field: "1d"}
    return refund


def test_a_max_age_nothing_can_fetch_again_is_a_warning() -> None:
    # The guide's output, word for word, line breaks aside.
    assert printed(issues(refund_needing_fresh("approved_amount"))) == warning_output(3)
    # The surprise: Sam approves three days after the review, and pay needs attention.
    run = run_case(
        refund_needing_fresh("approved_amount"),
        file=LARGE,
        answers=[LARGE_REVIEW, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "pay#1: approved_amount was obtained 3 days ago, and pay needs it at most 1 day old: "
            "it came from a person, so it can't be fetched again"
        )
    ]


def paying_fresh(value: str, **steps: Any) -> dict[str, Any]:
    """The quickstart's refund with `steps` added, `pay` reading `value` and needing it at most
    a day old."""
    refund = copy.deepcopy(REFUND)
    refund["steps"].update(copy.deepcopy(steps))
    refund["steps"]["pay"]["when"] = {"and": [APPROVED, {"exists": value}]}
    refund["steps"]["pay"]["max_age"] = {value: "1d"}
    return refund


# `orders.lookup@2` declares its status from the orders system, so `pay` may decide on it: under
# `@1`, undeclared, it couldn't (brief, D39).
LOOKUP = {
    "kind": "activity",
    "display": {"title": "Look the order up"},
    "activity": "orders.lookup@2",
    "inputs": {"order_id": {"var": "order_id"}},
}
TEAM_LEAD = {"roles": ["support-lead"], "display": {"reason": "Look-ups need a team lead"}}
DELIVERED = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}  # @2 has no fake


class FileInput(BaseModel):
    to_customer: Annotated[str, trusted_only()]  # never an address chosen by an AI
    template: str
    idempotency_key: str


class FiledOutput(BaseModel):
    draft_id: Annotated[str, source("system:letters")]  # the letters system says it


def filing() -> Catalog:
    """`noting()`'s catalog, and `letters.file@1`, which files a letter, a write, and declares
    where its draft ID comes from, so `pay` may decide on it (brief, D39)."""
    catalog = noting()
    catalog.register(
        ActivityContract(
            name="letters.file",
            version=1,
            input=FileInput,
            output=FiledOutput,
            risk="low",
            effect="write",
            timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
            idempotency_key="idempotency_key",
            outcomes=[],
            display=ContractDisplay(title="File a letter", description="Files a letter"),
        )
    )
    return catalog


def never_refreshed(definition: dict[str, Any], catalog: Catalog = CATALOG) -> list[str]:
    found = validate_case(parse_case(definition), catalog)
    assert [issue for issue in found if issue.severity == "error"] == []
    return [issue.message for issue in found if issue.code == "NEVER_REFRESHED"]


def test_only_a_read_needing_no_approval_is_fetched_again() -> None:
    def why(value: str) -> list[str]:
        return [
            f"{value} comes from {source}: whenever it is older than pay's max_age allows, pay "
            "needs attention: keep it only if a person should decide each time"
            for source in WHY[value]
        ]

    WHY = {
        "amount": ["the opening, and can't be fetched again"],
        "review.outcome": ["a person, in review, and can't be fetched again"],
        "draft.draft_id": ["draft, which has side effects (write), and can't be run again"],
        "note.entry_id": [
            "note, which computes it (compute), so running it again gives nothing new"
        ],
        "check_order.status": [
            "check_order, a read that always needs an approval, which a refresh never asks for"
        ],
    }
    draft = {
        "kind": "activity",
        "display": {"title": "Draft a letter"},
        "activity": "letters.file@1",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
    }
    note = {
        "kind": "activity",
        "display": {"title": "Note the order"},
        "activity": "refunds.note@1",
        "inputs": {"refund": {"var": "order_id"}},
    }
    assert never_refreshed(paying_fresh("amount")) == why("amount")
    assert never_refreshed(paying_fresh("review.outcome")) == why("review.outcome")
    drafted = paying_fresh("draft.draft_id", draft=draft)
    assert never_refreshed(drafted, filing()) == why("draft.draft_id")
    noted = paying_fresh("note.entry_id", note=note)
    assert never_refreshed(noted, noting()) == why("note.entry_id")
    # A read is fetched again; behind an approval only if the approval may not be needed.
    assert never_refreshed(paying_fresh("check_order.status", check_order=LOOKUP)) == []
    asked = {**LOOKUP, "approval": TEAM_LEAD}
    behind = paying_fresh("check_order.status", check_order=asked)
    assert never_refreshed(behind) == why("check_order.status")
    sometimes = {**LOOKUP, "approval": {**TEAM_LEAD, "when": {">": [{"var": "amount"}, 100]}}}
    assert never_refreshed(paying_fresh("check_order.status", check_order=sometimes)) == []


def test_a_workflow_or_a_plan_step_is_never_run_again_unasked() -> None:
    check = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "customer_id"}},
    }
    checked = paying_fresh("check.status", check=check)
    checked["fields"]["customer_id"] = {
        "type": "reference",
        "system": "crm",
        "display": {"title": "Customer"},
    }
    assert never_refreshed(checked) == [
        (
            "check.status comes from check, a workflow step, which isn't run again unasked: whenever "
            "it is older than pay's max_age allows, pay needs attention: keep it only if a person "
            "should decide each time"
        )
    ]
    # A plan step's outcome, read by a step after it.
    settled_then = settled()
    settled_then["steps"]["note"] = {
        "kind": "activity",
        "display": {"title": "Note the order"},
        "activity": "refunds.note@1",
        "requires": ["settle"],
        "when": {"==": [{"var": "settle.outcome"}, "done"]},
        "max_age": {"settle.outcome": "1d"},
        "inputs": {"refund": {"var": "order_id"}},
    }
    found = validate_case(parse_case(settled_then), noting(), plans=PLANS)
    assert [issue.message for issue in found if issue.code == "NEVER_REFRESHED"] == [
        (
            "settle.outcome comes from settle, a plan step, which isn't run again unasked: whenever it "
            "is older than note's max_age allows, note needs attention: keep it only if a person "
            "should decide each time"
        )
    ]


def test_a_read_behind_an_approval_needs_attention_when_stale() -> None:
    # The refresh gate (brief, D33): a refresh never asks for an approval, so a read that always
    # needs one is never fetched again, and the step that needs it fresh needs attention.
    behind = paying_fresh("check_order.status", check_order={**LOOKUP, "approval": TEAM_LEAD})
    run = run_case(
        behind,
        file=SMALL,
        answers=[("check_order", "approve", "sam"), later("3d"), REVIEWED],
        people=PEOPLE,
        activities=DELIVERED,
    )
    assert run.needs_attention == [
        (
            "pay#1: check_order.status was obtained 3 days ago, and pay needs it at most 1 day "
            "old: check_order needs an approval to run, so it isn't run again unasked"
        )
    ]
    # An approval asked only above 100: for a small refund the read is fetched again, so no
    # warning, and the run refreshes it.
    when = {">": [{"var": "amount"}, 100]}
    sometimes = paying_fresh(
        "check_order.status", check_order={**LOOKUP, "approval": {**TEAM_LEAD, "when": when}}
    )
    fetched = run_case(
        sometimes, file=SMALL, answers=[later("3d"), REVIEWED], people=PEOPLE, activities=DELIVERED
    )
    assert "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day" in (
        fetched.history
    )
    assert fetched.reached("pay")


def test_never_refreshed_says_a_proposal_is_refused() -> None:
    # A person's proposal on a stale fact nothing can fetch again is refused, saying why; a start
    # by itself or by a rule needs attention (brief, D39). The warning says which happens.
    proposed = paying_fresh("review.outcome")
    proposed["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
    done = {"display": {"title": "Done"}, "roles": ["support"]}
    proposed |= {"stays_open": True, "close_reasons": {"done": done}}
    assert never_refreshed(proposed) == [
        (
            "review.outcome comes from a person, in review, and can't be fetched again: whenever it "
            "is older than pay's max_age allows, a proposal of pay is refused: keep it only if a "
            "person should decide each time"
        )
    ]
    with pytest.raises(ProposalRefused, match="it came from a person, so it can't be fetched"):
        run_case(
            proposed,
            file=SMALL,
            answers=[REVIEWED, later("3d"), propose("pay", "ana")],
            people=PEOPLE,
        )
    both = copy.deepcopy(proposed)
    both["steps"]["pay"]["automatic"] = True
    both["steps"]["pay"]["repeatable"] = True
    [said] = never_refreshed(both)
    assert "allows, pay needs attention, and a proposal of it is refused:" in said
    # Started by a rule as well: the rule's start needs attention.
    by_a_rule = copy.deepcopy(proposed)
    by_a_rule["rules"] = {
        "pay_it": {
            "display": {"title": "Pay an answered review"},
            "on": {"answered": "review"},
            "then": {"start": ["pay"]},
        }
    }
    [said] = never_refreshed(by_a_rule)
    assert "allows, pay needs attention, and a proposal of it is refused:" in said


def test_an_untrusted_approval_is_always_needed() -> None:
    # An approval whose condition reads untrusted data is asked whatever it gives (brief, D39), so
    # for a refresh, which never asks for one, it is always needed: the read isn't fetched again.
    when = {"!": [{"exists": "notes"}]}
    approval = {**TEAM_LEAD, "when": when}
    untrusted = paying_fresh("check_order.status", check_order={**LOOKUP, "approval": approval})
    untrusted["fields"]["notes"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's notes"},
    }
    assert never_refreshed(untrusted) == [
        (
            "check_order.status comes from check_order, a read that always needs an approval, which "
            "a refresh never asks for: whenever it is older than pay's max_age allows, pay needs "
            "attention: keep it only if a person should decide each time"
        )
    ]
    run = run_case(
        untrusted,
        file=SMALL,
        answers=[("check_order", "approve", "sam"), later("3d"), REVIEWED],
        people=PEOPLE,
        activities=DELIVERED,
    )
    assert run.needs_attention == [
        (
            "pay#1: check_order.status was obtained 3 days ago, and pay needs it at most 1 day "
            "old: check_order needs an approval to run, so it isn't run again unasked"
        )
    ]


# --- 10d, slice 5: an approval that guards a neighbouring value ---


def approving_on(when: Any) -> dict[str, Any]:
    """The quickstart's refund, its approval asked when `when` holds."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["pay"]["approval"]["when"] = when
    return refund


ON_THE_REQUEST = {">": [{"var": "amount"}, 100]}


def test_an_approval_that_guards_a_neighbouring_value_is_a_warning() -> None:
    # The guide's output, word for word, line breaks aside.
    assert printed(issues(approving_on(ON_THE_REQUEST))) == warning_output(4)
    # The surprise: a customer asks for 50, the reviewer approves 5000, and 5000 is paid with
    # no team lead asked.
    run = run_case(
        approving_on(ON_THE_REQUEST),
        file={"order_id": "ord-1", "amount": 50},
        answers=[("review", "approve", "ana", {"approved_amount": 5000})],
        people=PEOPLE,
    )
    assert not any(line.startswith("asked pay.approval") for line in run.history)
    assert "pay#1 done, giving refund_id from untrusted:undeclared" in run.history
    assert run.closed


def test_an_approval_reading_any_value_its_step_is_given_guards_it() -> None:
    amount, approved = {"var": "amount"}, {"var": "approved_amount"}
    for when in (
        {">": [approved, 100]},  # the quickstart's
        {"or": [{">": [amount, 100]}, {">": [approved, 100]}]},  # a neighbour beside it
        {">": [{"-": [approved, amount]}, 0]},  # more approved than asked
    ):
        assert issues(approving_on(when)) == [], when
    # An approval with no `when` guards every run.
    always = copy.deepcopy(REFUND)
    del always["steps"]["pay"]["approval"]["when"]
    assert issues(always) == []
    # A field the step is given through an expression counts: the amount is the lesser of two.
    lesser = approving_on(ON_THE_REQUEST)
    lesser["steps"]["pay"]["inputs"]["amount"] = {
        "if": [{"<": [amount, approved]}, amount, approved]
    }
    assert issues(lesser) == []
    # Two neighbouring values, both named.
    neighbours = approving_on(
        {"and": [ON_THE_REQUEST, {"==": [{"var": "review.outcome"}, "approve"]}]}
    )
    assert [issue.message for issue in issues(neighbours)] == [
        (
            "pay's approval reads amount and review.outcome, and pay is given only order_id and "
            "approved_amount: it guards a value pay doesn't use: read one of those in its when"
        )
    ]


# --- 10d, slice 6: every example, one cause, no quoted value, the guide's table ---


def test_every_example_definition_gives_no_issue() -> None:
    # No noise: a warning that fires on what the guides call correct teaches people to ignore
    # warnings. Each whole definition the quickstart and the guides show, as they show it.
    case_data = (ROOT / "docs" / "guides" / "case-data.md").read_text()
    read_aloud = GUIDE.read_text().split("```json\n")[1].split("```")[0]
    examples = {
        "the quickstart's refund": (REFUND, {}),
        "the cases guide's refund, read aloud": (json.loads(read_aloud, parse_float=Decimal), {}),
        "the cases guide's claim": (guide_json(0), {}),
        "the cases guide's plan step": (guide_refund_with_plan(), PLANS),
        "the case data guide's claim": (
            json.loads(case_data.split("```json\n")[1].split("```")[0], parse_float=Decimal),
            {},
        ),
        "the case data guide's fresh refund": (refund_fresh(), {}),
    }
    for name, (definition, plans) in examples.items():
        assert validate_case(parse_case(definition), CATALOG, plans=plans) == [], name


# Each 10d issue, and the same definition with an error on its step, or on the step whose value
# it reads: the error alone is said.
def unknown_contract(definition: dict[str, Any], step: str = "pay") -> dict[str, Any]:
    definition["steps"][step]["activity"] = "payments.refund@9"
    return definition


def note_reading_pay_outcome() -> dict[str, Any]:
    refund = copy.deepcopy(REFUND)
    refund["steps"]["note"] = {
        **NOTED,
        "requires": ["review"],
        "when": {"==": [{"var": "pay.outcome"}, "done"]},
    }
    return refund


ONE_CAUSE: dict[str, tuple[Callable[[], dict[str, Any]], Callable[[dict[str, Any]], Any]]] = {
    "OUTCOME_UNREAD": (without_call_customer, unknown_contract),
    "MAY_BE_UNSET": (refund_without_when, unknown_contract),
    "MAY_BE_UNSET from a refused writer": (note_reading_pay_outcome, unknown_contract),
    "NEVER_REFRESHED": (lambda: refund_needing_fresh("approved_amount"), unknown_contract),
    "APPROVAL_ELSEWHERE": (lambda: approving_on(ON_THE_REQUEST), unknown_contract),
}


def misspelt_role(definition: dict[str, Any], step: str = "pay") -> dict[str, Any]:
    definition["steps"][step]["approval"]["roles"] = ["suport-lead"]
    return definition


@pytest.mark.parametrize("code", list(ONE_CAUSE))
def test_a_step_an_error_refuses_gets_no_warning(code: str) -> None:
    make, refuse = ONE_CAUSE[code]
    assert code.split()[0] in [issue.code for issue in issues(make())]
    # Its contract missing, or any other error on the step: that error alone.
    assert [issue.code for issue in issues(refuse(make()))] == ["UNKNOWN_CONTRACT"]
    assert [issue.code for issue in issues(misspelt_role(make()))] == ["UNKNOWN_ROLE"]


def test_a_step_that_fails_every_time_gets_its_error_alone() -> None:
    # SET_AFTER replaces MAY_BE_UNSET for its read; and an error on its step replaces it.
    catalog = noting()
    found = validate_case(parse_case(noting_before_paying()), catalog)
    assert [issue.code for issue in found] == ["SET_AFTER"]
    refused = noting_before_paying(activity="refunds.note@9")
    assert [issue.code for issue in validate_case(parse_case(refused), catalog)] == [
        "UNKNOWN_CONTRACT"
    ]


TEN_D: dict[str, Callable[[], dict[str, Any]]] = {
    "OUTCOME_UNREAD": without_call_customer,
    "MAY_BE_UNSET": refund_without_when,
    "NEVER_REFRESHED": lambda: refund_needing_fresh("approved_amount"),
    "APPROVAL_ELSEWHERE": lambda: approving_on({">": [{"var": "amount"}, 987654]}),
}


def test_no_10d_message_quotes_a_value() -> None:
    # Names only: no title, no reason, no literal the definition compares (brief, D35).
    for code, make in TEN_D.items():
        definition = make()
        if code != "APPROVAL_ELSEWHERE":  # its own approval compares the marked literal already
            definition["steps"]["pay"]["approval"]["when"] = {
                ">": [{"var": "approved_amount"}, 987654]
            }
        found = [issue for issue in issues(marked(definition)) if issue.code == code]
        assert found, code
        for issue in found:
            assert "TITLE-" not in issue.message and "987654" not in issue.message, issue
    set_after = validate_case(parse_case(marked(noting_before_paying())), noting())
    assert set_after and all("TITLE-" not in issue.message for issue in set_after)


def test_the_guides_table_of_warnings_is_what_validate_case_says() -> None:
    # Each row's code and kind is what the code gives for its example; its message is the
    # output above it, compared word for word by each slice's first test.
    table = GUIDE.read_text().split(WARNINGS)[1].split("| Code | Kind |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    kinds = {code.strip().strip("`"): kind.strip() for _, code, kind, *_ in rows}
    given = {code: issues(make()) for code, make in TEN_D.items()}
    given["SET_AFTER"] = validate_case(parse_case(noting_before_paying()), noting())
    assert list(kinds) == [
        "OUTCOME_UNREAD",
        "MAY_BE_UNSET",
        "SET_AFTER",
        "NEVER_REFRESHED",
        "APPROVAL_ELSEWHERE",
    ]
    for code, kind in kinds.items():
        [issue] = [issue for issue in given[code] if issue.code == code]
        assert issue.severity == kind, code


# --- 10d, from the tutor review: a guard written with `or` ---


def reviewed_also(outcome: str, sets: bool) -> dict[str, Any]:
    """The quickstart's refund, its review also answerable `outcome` (setting the approved amount
    if `sets`), and `pay` running on approve or `outcome`, the guard written with `or`."""
    refund = copy.deepcopy(REFUND)
    refund["steps"]["review"]["outcomes"][outcome] = {
        "display": {"title": f"Answer {outcome}"},
        "sets": ["approved_amount"] if sets else [],
    }
    refund["steps"]["pay"]["when"] = {
        "or": [APPROVED, {"==": [{"var": "review.outcome"}, outcome]}]
    }
    return refund


def test_an_or_guards_what_all_its_parts_agree_on() -> None:
    # approve or partial: both set the approved amount, so pay reads it set.
    partial = reviewed_also("partial", sets=True)
    assert issues(partial) == []
    rejected = run_case(partial, file=SMALL, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert rejected.closed and rejected.needs_attention == []
    answered = ("review", "partial", "ana", {"approved_amount": 20})
    paid = run_case(partial, file=SMALL, answers=[answered], people=PEOPLE)
    assert paid.closed and paid.needs_attention == [] and paid.reached("pay")
    # approve or escalate: escalate sets nothing, so the amount may be unset, and is.
    escalate = reviewed_also("escalate", sets=False)
    assert issues(escalate) == [
        Issue("steps.pay.approval.when", "MAY_BE_UNSET", AMOUNT_UNSET, "warning")
    ]
    escalated = run_case(
        escalate, file=SMALL, answers=[("review", "escalate", "ana")], people=PEOPLE
    )
    [failed] = escalated.needs_attention
    assert failed.endswith("approved_amount has no value")


# --- 11b: rules that start steps ---


def rechecked(*roles: str) -> dict[str, Any]:
    """The guide's claim with `recheck`, which a rule starts once the customer is checked, and
    which only `roles` may propose."""
    recheck = {
        **NOTIFY,
        "display": {"title": "Check the customer again"},
        "requires": ["checked"],
        "automatic": False,
        "proposed_by": list(roles),
    }
    claim = claim_with(recheck=recheck)
    claim["rules"] = {
        "recheck_checked": {
            "display": {"title": "Have the check looked at again"},
            "on": {"reached": "checked"},
            "then": {"start": ["recheck"]},
        }
    }
    return claim


def test_a_step_a_rule_may_start_can_run() -> None:
    # Who can start a step is one answer: it starts by itself, a person with a registered role
    # proposes it, or a rule that can fire starts it (brief, D39). Before 11b, a step only a rule
    # started was NEVER_RUNS.
    assert issues(rechecked()) == []
    run = run_case(rechecked(), file=CLAIM_FILE, answers=[], people=CLAIM_PEOPLE)
    assert "recheck_checked#1 on reached checked: starting recheck" in run.history
    # A rule starts it, so its misspelt role is said: it counts for nothing (brief, D22).
    assert issues(rechecked("supprt")) == [unknown_role("steps.recheck.proposed_by", "supprt")]


CHOSEN_BY_THE_MODEL = (
    "letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, "
    "and {who}'s condition reads kyc.analyst_notes (untrusted:llm): read a value a person or a "
    "trusted system gives, such as a task's answer"
)


def welcomed_by_a_rule() -> dict[str, Any]:
    """The welcome letter, started by a rule when the model's notes say so."""
    definition = with_welcome(SAYS_SEND)
    del definition["steps"]["welcome"]["when"]
    definition["steps"]["welcome"]["automatic"] = False
    definition["rules"]["send_welcome"] = {
        "display": {"title": "Send a welcome letter"},
        "on": {"reached": "checked"},
        "when": SAYS_SEND,
        "then": {"start": ["welcome"]},
    }
    return definition


def test_input_policy_counts_conditions() -> None:
    # A condition that lets a step start decides that its inputs are sent: the untrusted data it
    # reads counts for their policies (brief, D39). The opener's source is trusted either way, so
    # who opens the case changes nothing: an error, never OPENER_DECIDES.
    assert issues(with_welcome(SAYS_SEND)) == [
        Issue(
            "steps.welcome.inputs.to_customer",
            "INPUT_POLICY",
            CHOSEN_BY_THE_MODEL.format(who="welcome"),
        )
    ]
    for opened_by in (None, "ana"):
        run = run_case(
            with_welcome(SAYS_SEND),
            file=welcome_file(),
            answers=[],
            people={"ana": ["support"]},
            opened_by=opened_by,
            workflows={"kyc.check@1": notes_say_send},
        )
        [failed] = run.needs_attention
        assert failed.startswith("welcome#1: letters.draft@2 takes to_customer only from")
    # At the rule, said as a failure; no UNTRUSTED_TRIGGER, since a rule that only starts acts.
    assert issues(welcomed_by_a_rule()) == [
        Issue(
            "rules.send_welcome.then.start",
            "INPUT_POLICY",
            "welcome fails on its inputs every time send_welcome starts it: "
            + CHOSEN_BY_THE_MODEL.format(who="send_welcome"),
        )
    ]
    # A rule that reaches a milestone too doesn't act at all on untrusted data (brief, D38).
    reaching = welcomed_by_a_rule()
    reaching["milestones"]["welcomed"] = {"display": {"title": "Welcomed"}}
    reaching["rules"]["send_welcome"]["then"]["reach"] = ["welcomed"]
    [untrusted] = issues(reaching)
    assert (untrusted.path, untrusted.code) == ("rules.send_welcome.when", "UNTRUSTED_TRIGGER")
    assert untrusted.message.endswith(
        "so it never reaches welcomed or starts welcome: read a value a person or a trusted "
        "system gives, such as a task's answer"
    )
    # An input already refused on its own is the cause, said at the input only: one cause, one
    # issue.
    own = welcomed_by_a_rule()
    own["steps"]["welcome"]["inputs"]["to_customer"] = {"var": "kyc.analyst_notes"}
    assert [issue.path for issue in issues(own)] == ["steps.welcome.inputs.to_customer"]
    # A warning on the input's own sources is another cause: it never hides the condition's
    # error. `ledger.record@1` takes the amount only from the opener, so a person opening the case
    # would be refused too (OPENER_DECIDES); the model's notes refuse it whoever opens it (the
    # second review).
    recorded = with_welcome(SAYS_SEND)
    del recorded["steps"]["welcome"]
    recorded["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the request"},
        "activity": "ledger.record@1",
        "requires": ["checked"],
        "when": SAYS_SEND,
        "inputs": {"amount": {"var": "amount"}},
    }
    found = validate_case(parse_case(recorded), with_ledger())
    assert [(i.path, i.code) for i in found] == [
        ("steps.record.inputs.amount", "OPENER_DECIDES"),
        ("steps.record.inputs.amount", "INPUT_POLICY"),
    ]


def without_forgetters() -> Catalog:
    """The development catalog, with no role that may forget a case."""
    catalog = Catalog()
    for label in CATALOG.labels:
        catalog.register_label(label)
    for system in CATALOG.systems:
        catalog.register_system(system)
    for role, approves in CATALOG.roles.items():
        if role not in CATALOG.forgetters:
            catalog.register_role(role, approves, operates=role in CATALOG.operators)
    for contract in CATALOG.contracts():
        catalog.register(contract)
    return catalog


def test_never_closes_says_nothing_could_without_forgetting() -> None:
    # A forget request closes any case its definition lets be forgotten (brief, D32): without
    # one, nothing could close it, and the issue says so.
    never = staying_open(guide_json(0))
    del never["closes_when"]
    nothing_could = Issue(
        "close_reasons",
        "NEVER_CLOSES",
        "claim stays open, none of its close reasons' roles (supprt) is registered, and "
        "closes_when never closes it, so nothing could ever close it: name a registered role in "
        "a close reason",
    )
    assert issues(never) == [NEVER_CLOSES]
    assert validate_case(parse_case(never), without_forgetters()) == [nothing_could]
    assert issues(never | {"forgetting": "never"}) == [nothing_could]
