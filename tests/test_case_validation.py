"""Case validation: what can be proven about a case definition by reading it (layer 10).

Tests go through `parse_case`, then `validate_case`, and read the issues it gives.
See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

import copy
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import CATALOG, Outcome, load_definition, run_case

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
            "approve can never run: it requires reviewed, which no step reaches: reach reviewed "
            "from a step, or remove the requirement",
        )
    ]


def test_the_order_of_the_steps_does_not_matter() -> None:
    # A case has no position: `pay` written before the steps it waits on can still run. One pass
    # in the written order would find `pay` and `assess` not yet possible, and refuse them.
    claim = guide_json(0)
    claim["steps"] = dict(reversed(claim["steps"].items()))
    assert list(claim["steps"]) == ["pay", "assess", "check"]
    assert issues(claim) == []


# --- Slice 2: the curriculum's negative test ---


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
        )
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
        )
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
            "is refused: let a step start by itself with nothing required, or add stays_open",
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
    "claim stays open, no close reason names a registered role, and closes_when never closes it, "
    "so nobody could ever close it: name a registered role in a close reason",
)


def test_a_case_nobody_can_close_is_refused() -> None:
    # The tutor review's probe: closes_when closes a case that stays open too (layer 8b), so
    # paid, which pay reaches, closes this one.
    assert issues(staying_open(guide_json(0))) == []
    # With paid unreachable, or no closes_when at all, nobody could ever close it.
    assert NEVER_CLOSES in issues(staying_open(deadlocked_claim()))
    without_close = staying_open(guide_json(0))
    del without_close["closes_when"]
    assert issues(without_close) == [NEVER_CLOSES]
    without_close["close_reasons"]["duplicate"]["roles"] = ["supprt", "adjuster"]
    assert issues(without_close) == []


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
    assert [issue.code for issue in found] == ["DEADLOCK", "CLOSE_UNREACHABLE"]
    assert found[1] == CLOSE_UNREACHABLE


def test_an_unreachable_close_says_how_the_case_closes_instead() -> None:
    claim = deadlocked_claim()
    claim["stays_open"] = True
    claim["close_reasons"] = {
        "withdrawn": {"display": {"title": "Claim withdrawn"}, "roles": ["adjuster"]}
    }
    assert issues(claim)[1].message == (
        "paid can never be reached, so closes_when never closes claim, and only a person can "
        "close it: reach paid from a step that can run, or remove it from closes_when"
    )


def test_every_unreachable_close_milestone_is_named() -> None:
    claim = deadlocked_claim()
    claim["closes_when"] = ["assessed", "paid"]
    assert issues(claim)[1].message == (
        "assessed and paid can never be reached, so closes_when never closes claim, and it closes "
        "when nothing is left to do: reach them from steps that can run, or remove them from "
        "closes_when"
    )


def test_a_milestone_nothing_reaches_is_a_warning() -> None:
    assert issues(reviewed(guide_json(0))) == [
        Issue(
            "milestones.reviewed",
            "UNREACHABLE_MILESTONE",
            "no step reaches reviewed: reach it from a step or an outcome, or remove it",
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
    assert [issue.code for issue in issues(deadlocked_claim())] == ["DEADLOCK", "CLOSE_UNREACHABLE"]


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
    assert run.history[-1] == "closed: nothing left to do"
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


def guide_table() -> list[tuple[str, str, str]]:
    """The guide's table of codes, as (code, kind, example message); "as above" is the output
    above it, which `test_the_deadlocked_claim_is_refused` checks word for word."""
    table = guide_section().split("| Code | Kind |")[1].split("\n\n")[0]
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
        )
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
    """The quickstart's refund, `pay` replaced by the plan step, with `settle`'s keys changed."""
    refund = copy.deepcopy(REFUND)
    del refund["steps"]["pay"], refund["sequence"]
    refund["steps"]["settle"] = {**copy.deepcopy(SETTLE), **settle}
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
