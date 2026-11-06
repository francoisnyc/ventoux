"""Layer 18b: repeated steps. A step runs once per item of a list in the case file, each run named
by a number the engine gives its item's key, and given its item (brief, D73).

See docs/layers/18-lifecycle.md (18b) and docs/guides/cases.md, "Repeated steps: one run per item".
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, CaseRefused, close, load_definition, run_case

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Repeated steps: one run per item"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")  # the quickstart's


def guide_block() -> dict[str, Any]:
    """The guide's fields and steps for a returned order, as stored data, read from the guide."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    loaded: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return loaded


def order_return() -> dict[str, Any]:
    """The guide's returned order: its fields and its two repeated steps, as a case of its own."""
    block = guide_block()
    return {
        "case": "order-return",
        "display": {"title": "A returned order"},
        "fields": block["fields"],
        "steps": block["steps"],
    }


def test_a_step_repeated_over_a_field_that_isnt_a_list_is_refused() -> None:
    # The curriculum's negative test (brief, D73).
    definition = order_return()
    definition["steps"]["draft_line"]["for_each"]["over"] = "order_id"
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.draft_line.for_each: order_id is a reference to orders, not a list: a step "
        "repeats over a list field"
    )


# --- Slice 1: a list value, given at the opening (brief, D73) ---

LINES = [{"sku": "A12", "amount": 40}, {"sku": "B7", "amount": 25}]
FILE = {"order_id": "ord-1", "email": "ana@example.com", "lines": LINES}
PEOPLE = {"ana": ["support"], "omar": ["operations"]}
SHAPE = "lines is a list of records with sku (a string) and amount (a number)"


def opened(lines: object) -> CaseRun:
    """The returned order opened with `lines`, nothing answered."""
    return run_case(order_return(), file=FILE | {"lines": lines}, answers=[], people=PEOPLE)


def test_a_list_that_fits_is_given_at_the_opening() -> None:
    assert opened(LINES).status == "open"


@pytest.mark.parametrize(
    ("lines", "refusal"),
    [
        ("A12, B7", f"{SHAPE}, and the opening gives a string"),
        ([{"sku": "A12"}], f"{SHAPE}, and the opening gives an item without amount"),
        (
            [{"sku": "A12", "amount": 40, "note": "x"}],
            f"{SHAPE}, and the opening gives an item with a field lines doesn't declare",
        ),
        (
            [{"sku": "A12", "amount": "40"}],
            f"{SHAPE}, and the opening gives an item whose amount is a string",
        ),
        (["A12"], f"{SHAPE}, and the opening gives an item that is a string"),
        (
            [{"sku": f"s{n}", "amount": 1} for n in range(101)],
            "lines holds at most 100 items, and the opening gives 101",
        ),
    ],
)
def test_a_list_that_doesnt_fit_is_refused_at_the_opening(lines: object, refusal: str) -> None:
    # The type and the shape, never a value: refusals reach people who may not see it (brief,
    # D30) (brief, D73).
    with pytest.raises(CaseRefused) as refused:
        opened(lines)
    assert str(refused.value) == refusal


# --- Slice 2: what can't be repeated, refused when the definition is read (brief, D73) ---


def changed(change: Any) -> dict[str, Any]:
    """The returned order, changed by `change`, a function of its definition."""
    definition = order_return()
    change(definition)
    return definition


def notify(**step: Any) -> dict[str, Any]:
    """A letter drafted once, not repeated, with `step`'s keys."""
    return {
        "kind": "activity",
        "display": {"title": "Draft one letter"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "email"}, "template": "returned"},
        **step,
    }


def key(name: str) -> Any:
    return lambda d: d["steps"]["draft_line"]["for_each"].update(key=name)


def set_step(name: str, **keys: Any) -> Any:
    return lambda d: d["steps"][name].update(keys)


REPEATED = "steps.draft_line: a repeated step starts by itself, a run per item"


@pytest.mark.parametrize(
    ("change", "refusal"),
    [
        (
            key("amount"),
            (
                "steps.draft_line.for_each: amount is not a text field of lines: a key is a text "
                "field every item has"
            ),
        ),
        (
            key("colour"),
            (
                "steps.draft_line.for_each: colour is not a text field of lines: a key is a text "
                "field every item has"
            ),
        ),
        (set_step("draft_line", proposed_by=["support"]), f"{REPEATED}: drop proposed_by"),
        (
            set_step("draft_line", proposed_by=["support"], repeatable=True),
            f"{REPEATED}: drop proposed_by and repeatable",
        ),
        (
            lambda d: d.setdefault("rules", {}).update(
                start_letters={
                    "display": {"title": "Draft again"},
                    "on": "opened",
                    "then": {"start": ["draft_line"]},
                }
            ),
            f"{REPEATED}: no rule starts it, and start_letters does",
        ),
        (
            set_step(
                "draft_line",
                approval={"roles": ["support-lead"], "display": {"reason": "Why"}},
            ),
            "steps.draft_line.approval: a repeated step has no approval yet",
        ),
        (
            lambda d: d["steps"].update(
                notify=notify(
                    inputs={"to_customer": {"var": "email"}, "template": {"var": "each.sku"}}
                )
            ),
            "steps.notify.inputs.template: each is read only in a repeated step",
        ),
        (
            lambda d: d["fields"].update(each={"type": "string", "display": {"title": "Each"}}),
            "fields.each: each is the name a repeated step reads its item by: name it otherwise",
        ),
        (
            lambda d: d["steps"].update(
                notify=notify(when={"==": [{"var": "inspect_line.outcome"}, "received"]})
            ),
            "steps.notify.when: inspect_line.outcome: a repeated step has no one outcome",
        ),
        (
            lambda d: d["steps"].update(
                review={
                    "kind": "task",
                    "display": {"title": "Review"},
                    "roles": ["support"],
                    "outcomes": {"redo": {"display": {"title": "Redo"}, "sets": ["lines"]}},
                }
            ),
            (
                "steps.review.outcomes.redo.sets: lines is a list, and a form never gives a list "
                "yet: a list is given at the opening"
            ),
        ),
        (
            lambda d: d["fields"]["lines"].update(sensitive=True, visible_to=["support"]),
            "fields.lines: a list is never sensitive yet: keep the personal data out of it",
        ),
    ],
)
def test_what_cant_be_repeated_is_refused_when_read(change: Any, refusal: str) -> None:
    with pytest.raises(CaseInvalid) as refused:
        parse_case(changed(change))
    assert str(refused.value) == refusal


def test_a_plan_workflow_or_wait_step_has_no_for_each() -> None:
    # Only a task or an activity repeats: the others refuse the key, as the format refuses any key
    # a kind of step doesn't have.
    plan_step = {
        "kind": "plan",
        "display": {"title": "Settle"},
        "plan": "refund-order@1",
        "for_each": {"over": "lines", "key": "sku"},
    }
    with pytest.raises(CaseInvalid, match="^steps.settle.for_each: not a field here$"):
        parse_case(changed(lambda d: d["steps"].update(settle=plan_step)))


@pytest.mark.parametrize(
    ("step", "keys", "refusal"),
    [
        (
            "draft_line",
            {"reaches": ["drafted"]},
            (
                "steps.draft_line.reaches: a repeated step reaches no milestone yet: reach it from a "
                "step that requires draft_line"
            ),
        ),
        (
            "inspect_line",
            {"outcomes": {"received": {"display": {"title": "Received"}, "reaches": ["drafted"]}}},
            (
                "steps.inspect_line.outcomes.received.reaches: a repeated step reaches no milestone "
                "yet: reach it from a step that requires inspect_line"
            ),
        ),
        (
            "inspect_line",
            {"outcomes": {"received": {"display": {"title": "Received"}, "sets": ["email"]}}},
            (
                "steps.inspect_line.outcomes.received.sets: a repeated task's answer sets no field "
                "yet: each answer would overwrite the last"
            ),
        ),
        (
            "draft_line",
            {"max_age": {"email": "1d"}},
            "steps.draft_line.max_age: a repeated step needs no fact fresh yet",
        ),
        (
            "inspect_line",
            {"assign": {"to": "opener"}},
            "steps.inspect_line.assign: a repeated task is asked of its queue yet",
        ),
    ],
)
def test_what_a_repeated_step_cant_do_yet_is_refused(
    step: str, keys: dict[str, Any], refusal: str
) -> None:
    # Each assumes one run per step; each a deliberate limit, a door for later (brief, D48, D73).
    definition = order_return()
    definition["milestones"] = {"drafted": {"display": {"title": "Drafted"}}}
    definition["steps"][step].update(keys)
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == refusal


# --- Slice 3: the runs, a run per item, named by its key's number (brief, D73) ---


def test_each_item_gets_its_run_named_by_its_keys_number() -> None:
    # The guide's example, as written: a draft for each line, each named by the number its sku was
    # given, and keyed by that name, so reordering the list never swaps two lines' keys.
    run = opened(LINES)
    drafts = [line for line in run.history if line.startswith("scheduled draft_line")]
    assert [line.split(":")[0] for line in drafts] == [
        "scheduled draft_line.1#1",
        "scheduled draft_line.2#1",
    ]
    assert [line.split(", key ")[1] for line in drafts] == [
        "memory/draft_line.1#1",
        "memory/draft_line.2#1",
    ]
    # Each inspection is open, named by its number, never by its value (brief, D30).
    assert run.waiting_for == ["inspect_line.1 by support", "inspect_line.2 by support"]


def test_a_repeated_task_is_answered_by_its_entry_and_sets_nothing_under_its_name() -> None:
    # Each inspection is its own run: answered by its entry, it's done, and its outcome isn't
    # written under the step's name, where the next answer would overwrite it (brief, D73).
    run = run_case(
        order_return(),
        file=FILE,
        answers=[("inspect_line.2#1", "missing", "ana")],
        people=PEOPLE,
    )
    assert "ana answered inspect_line.2#1 missing as support" in run.history
    assert run.waiting_for == ["inspect_line.1 by support"]
    assert "inspect_line.outcome" not in run.state.values
    done = run_case(
        order_return(),
        file=FILE,
        answers=[("inspect_line.1#1", "received", "ana"), ("inspect_line.2#1", "missing", "ana")],
        people=PEOPLE,
    )
    assert done.closed


def drafted_with(template: object) -> dict[str, Any]:
    """The returned order, each letter's template read from `template`."""
    definition = order_return()
    definition["steps"]["draft_line"]["inputs"]["template"] = template
    return definition


def test_validation_reads_each_with_its_items_types() -> None:
    # A repeated step's expressions are read over the case's types and its item's: each.sku is a
    # text, so it may be a template; each.amount is a number, so it may not (brief, D35, D73).
    assert validate_case(parse_case(drafted_with({"var": "each.sku"})), CATALOG) == []
    [issue] = validate_case(parse_case(drafted_with({"var": "each.amount"})), CATALOG)
    assert (issue.path, issue.code) == ("steps.draft_line.inputs.template", "INPUT_TYPE")


# --- Slice 4: read from outside, required, its items told apart, and their sources ---


def closing_out(**inspect: Any) -> dict[str, Any]:
    """The returned order with a close-out task that requires every line inspected; with
    `inspect`'s keys on `inspect_line`."""
    definition = order_return()
    definition["steps"]["inspect_line"].update(inspect)
    definition["steps"]["close_out"] = {
        "kind": "task",
        "display": {"title": "Close out the return"},
        "roles": ["support"],
        "requires": ["inspect_line"],
        "outcomes": {"closed": {"display": {"title": "Closed out"}}},
    }
    return definition


def test_requires_over_a_repeated_step_waits_for_every_item() -> None:
    # Line 2 inspected, line 1 not: the requirement isn't met, whichever run came last.
    run = run_case(
        closing_out(), file=FILE, answers=[("inspect_line.2#1", "received", "ana")], people=PEOPLE
    )
    assert run.waiting_for == ["inspect_line.1 by support"]
    both = run_case(
        closing_out(),
        file=FILE,
        answers=[("inspect_line.2#1", "received", "ana"), ("inspect_line.1#1", "missing", "ana")],
        people=PEOPLE,
    )
    assert both.waiting_for == ["close_out by support"]


def test_an_empty_list_meets_a_requirement_at_once_and_says_so() -> None:
    run = run_case(closing_out(), file=FILE | {"lines": []}, answers=[], people=PEOPLE)
    assert "inspect_line: lines has no items, so it has no runs" in run.history
    assert run.waiting_for == ["close_out by support"]


def test_a_required_repeated_step_owes_every_item() -> None:
    # Owed until every item's latest run is done (brief, D72): with line 1 still open, closing it
    # by a reason names what was owed.
    definition = closing_out(required=True)
    del definition["steps"]["close_out"]
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}
    }
    run = run_case(
        definition,
        file=FILE,
        answers=[("inspect_line.2#1", "received", "ana"), close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert run.history[-1] == "closed: duplicate, by ana; inspect_line not done"


def test_items_that_share_a_key_fail_the_step() -> None:
    # Nothing guesses which line is which: the step needs attention (brief, D17) (brief, D73).
    twice = [{"sku": "A12", "amount": 40}, {"sku": "A12", "amount": 25}]
    run = opened(twice)
    assert run.needs_attention == [
        (
            "inspect_line#1: inspect_line can't run: two items of lines have the same sku: each "
            "item's key is its own"
        ),
        (
            "draft_line#1: draft_line can't run: two items of lines have the same sku: each "
            "item's key is its own"
        ),
    ]


def test_each_item_carries_the_lists_sources() -> None:
    # A list the customer typed leaves every line untrusted (brief, D12): a trusted-only input
    # refuses its item's value, and each run fails, nothing drafted (brief, D73).
    definition = order_return()
    definition["fields"]["lines"]["source"] = "untrusted:customer"
    definition["steps"]["draft_line"]["inputs"]["to_customer"] = {"var": "each.sku"}
    run = run_case(definition, file=FILE, answers=[], people=PEOPLE)
    failed = [line.split(": ")[0] for line in run.needs_attention]
    assert failed == ["draft_line.1#1", "draft_line.2#1"]
    assert "untrusted:customer" in run.needs_attention[0]
    assert not any(line.startswith("scheduled draft_line") for line in run.history)
