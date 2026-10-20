"""Stories: a timeline in simulated time, played on the in-memory engine (layer 11g2).

Tests go through `parse_story` and `simulate`, and read what a simulation prints.
See docs/layers/11-rules.md (11g), the brief, D45, and docs/guides/cases.md, "Simulating a story".
"""

import json
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_case import guide_refund_with_plan
from test_set import with_owed
from test_timers import chased

from ventoux.case.definition import parse_case
from ventoux.case.reading import CLAUSES, EVERY_RULE
from ventoux.case.simulate import StoryRefused, simulate
from ventoux.case.story import StoryInvalid, parse_story
from ventoux.testing import CATALOG, load_definition
from ventoux.tooling.cli import read_story

EXAMPLES = Path(__file__).parent.parent / "examples"
REFUND = load_definition(EXAMPLES / "refund" / "refund.json")

# --- Slice 1: the format ---


def story(**changes: object) -> dict[str, object]:
    """A story of the refund with nothing on its timeline, changed by `changes`."""
    return {
        "title": "Nobody reviews the refund",
        "definition": "../refund.json",
        "file": {"order_id": "ord-1", "amount": 40},
        "people": {"ana": ["support"]},
        "fakes": {"payments.refund@2": {"gives": {"refund_id": "refund-1"}}},
        "timeline": [],
    } | changes


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"timelien": []}, "timelien: not a field here"),
        (
            {
                "timeline": [
                    {
                        "at": "day 1",
                        "answer": {"step": "review", "outcome": "approve", "by": "ana"},
                        "propose": {"step": "pay", "by": "ana"},
                    }
                ]
            },
            (
                "timeline.0: an entry does one thing, and this one does answer and propose: "
                "split it in two entries"
            ),
        ),
        (
            {"timeline": [{"at": "Tuesday"}]},
            'timeline.0.at: a time looks like "day 3" or "day 3 14:30", counted from the opening',
        ),
        (
            {"timeline": [{"at": "day 1 25:00"}]},
            'timeline.0.at: a time looks like "day 3" or "day 3 14:30", counted from the opening',
        ),
        (
            {"timeline": [{"at": "day 2"}, {"at": "day 1"}]},
            (
                "timeline.1.at: day 1 00:00 comes before day 2 00:00, the entry before it: time "
                "only moves forward"
            ),
        ),
        (
            {"until": "day 0 12:00", "timeline": [{"at": "day 1"}]},
            "until: day 0 12:00 comes before day 1 00:00, the last entry: time only moves forward",
        ),
        (
            {"fakes": {"payments.refund@2": {"gives": {}, "fails": "down"}}},
            (
                "fakes.payments.refund@2: a fake gives, gives an outcome or fails, and this one "
                "does gives and fails: keep one"
            ),
        ),
    ],
)
def test_a_story_that_cant_be_read_is_refused(changes: dict[str, object], problem: str) -> None:
    # Fail closed: a story is data, and one that can't be read whole plays nothing.
    with pytest.raises(StoryInvalid) as refused:
        parse_story(story(**changes))
    assert str(refused.value) == problem


def refused(data: dict[str, Any], definition: dict[str, Any]) -> list[str]:
    """Why `data`, a story, can't run against `definition`: one line per problem."""
    with pytest.raises(StoryRefused) as refusal:
        simulate(parse_story(data), parse_case(definition), CATALOG)
    return str(refusal.value).splitlines()


def test_a_story_without_a_fake_for_what_its_definition_calls_is_refused() -> None:
    # Nothing real is ever reached for: every contract the definition calls has a fake, and a
    # fake for nothing it calls is a typo (brief, D45).
    assert refused(story(fakes={}), REFUND) == [
        "fakes: no fake for payments.refund@2, which pay calls: add one, so nothing real is called"
    ]
    extra = story()
    extra["fakes"] = {**extra["fakes"], "orders.lookup@1": {"gives": {}}}  # type: ignore[dict-item]
    assert refused(extra, REFUND) == [
        (
            "fakes.orders.lookup@1: the definition calls no orders.lookup@1: remove it, or name a "
            "contract a step calls"
        )
    ]


def test_a_story_with_a_plan_step_is_refused() -> None:
    assert "steps.settle: a story can't run a plan step yet: plans in stories come later" in (
        refused(story(), guide_refund_with_plan())
    )


# --- Slice 2: playing a story ---


def played(data: dict[str, Any], definition: dict[str, Any] = REFUND) -> Any:
    """`data`, a story, simulated on `definition`."""
    return simulate(parse_story(data), parse_case(definition), CATALOG)


APPROVE = {"step": "review", "outcome": "approve", "by": "ana", "form": {"approved_amount": 40}}


def test_a_story_names_times_from_the_opening() -> None:
    # Day 0 00:00 is the opening; each entry's time is its event's time (brief, D33).
    simulation = played(story(timeline=[{"at": "day 1 09:30", "answer": APPROVE}]))
    assert simulation.timeline_lines() == {
        "day 0 00:00": [
            "the case opens",
            "opened by system:opener, with amount and order_id",
            "started review#1: waiting for approve or reject by support",
        ],
        "day 1 09:30": [
            "ana answers review: approve, with approved_amount",
            "ana answered review#1 approve as support, setting approved_amount",
            "review#1 done",
            (
                "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
                "person:ana), key story/pay#1"
            ),
            "pay#1 done, giving refund_id from untrusted:undeclared",
            "closed: nothing left to do",
        ],
    }


def test_time_passing_fires_timers_at_their_due_time() -> None:
    # Nobody answers: the chase fires on day 2, stamped with its due time, though the story
    # only says it ends on day 3 (brief, D44).
    simulation = played(story(until="day 3"), chased())
    lines = simulation.timeline_lines()
    assert (
        "set chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z"
        in (lines["day 0 00:00"])
    )
    assert lines["day 2 00:00"] == [
        "chase_review#1 on 2d after started review#1: starting chase",
        "started chase#1: waiting for chased by support-lead",
    ]
    assert simulation.end_at == "day 3 00:00"


def test_a_refused_entry_is_a_line_and_the_story_goes_on() -> None:
    # Eve has no role: the engine refuses her answer, which changes nothing, and Ana's goes on.
    eve = APPROVE | {"by": "eve"}
    simulation = played(
        story(
            people={"ana": ["support"], "eve": []},
            timeline=[{"at": "day 1", "answer": eve}, {"at": "day 2", "answer": APPROVE}],
        )
    )
    lines = simulation.timeline_lines()
    assert lines["day 1 00:00"] == [
        "eve answers review: approve, with approved_amount",
        "refused: review#1 is answered by support, and eve has no role",
    ]
    assert lines["day 2 00:00"][1] == (
        "ana answered review#1 approve as support, setting approved_amount"
    )


# --- Slice 3: what a simulation prints ---


def test_each_firing_is_shown_beside_its_reading() -> None:
    # Its whole reading, fine print included, so the reader sees what the engine does as it
    # does it (brief, D45).
    printed = str(played(story(until="day 3"), chased()))
    assert (
        "day 2 00:00\n"
        "  chase_review#1 on 2d after started review#1: starting chase\n"
        "    ↳ chase_review: Chase a review left open for two days\n"
        "      2d after each run of review starts: start chase.\n"
        "      - The timer is set as each run of review starts, and ends when that run does: "
        "done, rejected or cancelled, a stop included. A failed run keeps it: a retry is the same "
        "run.\n"
        "      - While it is set, the timer keeps the case open; a close cancels it.\n"
        "      - Starting chase is a proposal, decided at once as a person's is: nothing starts, "
        "and the history says why, if it is already running, or it has run and isn't "
        "repeatable.\n"
        "      - Only while the case decides: not once the case is closing.\n"
        "  started chase#1: waiting for chased by support-lead\n"
    ) in printed
    # Every rule's reading is printed once at the top too, under what holds for every rule.
    assert printed.index("Rules\n  A rule remembers nothing") < printed.index("Timeline")


def test_the_end_lists_every_pending_item() -> None:
    # Every kind of pending work is listed, none left unsaid; with none, it says so (brief, D10).
    assert played(story(until="day 1"), chased()).end == (
        "status: open",
        "waiting for: review by support",
        "timer: chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z",
    )
    held = story(timeline=[{"at": "day 1", "answer": APPROVE}])
    held["fakes"] = {"payments.refund@2": {"gives": {"refund_id": "refund-1"}, "held": True}}
    assert played(held).end == ("status: open", "running: pay#1")
    failing = story(timeline=[{"at": "day 1", "answer": APPROVE}])
    failing["fakes"] = {"payments.refund@2": {"fails": "the provider is down"}}
    assert played(failing).end == (
        "status: open",
        "needs attention: pay#1: payments.refund@2 failed with FakeFailed: ‹sensitive›",
    )
    big = APPROVE | {"form": {"approved_amount": 250}}
    asked = played(story(timeline=[{"at": "day 1", "answer": big}]))
    assert asked.end == ("status: open", "waiting for: approval of pay by support-lead")
    paid = played(story(timeline=[{"at": "day 1", "answer": APPROVE}]))
    assert paid.end == ("status: closed", "nothing pending")


def test_no_output_line_quotes_a_value_from_the_case_file() -> None:
    # Names only: the story's lines, the engine's, the readings. Each value below is distinct,
    # the opening's, a form's, a fake's, and one a rule computes (brief, D30, D45).
    data = story(
        file={"order_id": "ord-9876", "amount": 6543, "fee": 17},
        people={"ana": ["support"], "sam": ["support", "support-lead"]},
        timeline=[
            {"at": "day 1", "answer": APPROVE | {"form": {"approved_amount": 4999}}},
            {"at": "day 2", "answer": {"step": "pay", "outcome": "approve", "by": "sam"}},
        ],
    )
    data["fakes"] = {"payments.refund@2": {"gives": {"refund_id": "rf-5555"}}}
    simulation = played(data, with_owed())
    printed = str(simulation)
    assert "work_out_owed#1 on answered review: setting owed" in printed
    assert simulation.end == ("status: closed", "nothing pending")
    for value in ("ord-9876", "6543", "17", "4999", "4982", "rf-5555"):
        assert value not in printed.replace("2026-01-01T00:00:00Z", ""), value


def test_a_story_simulates_the_same_every_time() -> None:
    first = str(played(story(until="day 3"), chased()))
    assert str(played(story(until="day 3"), chased())) == first


def test_only_the_storys_fakes_run() -> None:
    # The development fakes would pay; the story's says the provider declined, so it did.
    declined = story(timeline=[{"at": "day 1", "answer": APPROVE}])
    declined["fakes"] = {"payments.refund@2": {"outcome": "declined"}}
    lines = played(declined).timeline_lines()["day 1 00:00"]
    assert "pay#1 gave declined" in lines
    assert "started call_customer#1: waiting for called by support" in lines


def test_a_held_run_finishes_when_the_story_says() -> None:
    held = story(
        timeline=[
            {"at": "day 1", "answer": APPROVE},
            {"at": "day 1 10:00", "finish": {"entry": "pay#1"}},
        ]
    )
    held["fakes"] = {"payments.refund@2": {"gives": {"refund_id": "refund-1"}, "held": True}}
    assert played(held).timeline_lines()["day 1 10:00"] == [
        "pay#1 finishes",
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "closed: nothing left to do",
    ]
    # Finishing what isn't held and running is the story's mistake: refused, never skipped.
    wrong = story(timeline=[{"at": "day 1", "finish": {"entry": "pay#1"}}])
    with pytest.raises(StoryRefused) as refusal:
        played(wrong)
    assert str(refusal.value) == ("day 1 00:00: pay#1 isn't a held run going on: nothing finishes")


# --- Slice 4: what a story expects ---


def test_a_failing_expectation_says_where() -> None:
    # Compared whole: the story expects the chase never fires, and it does (brief, D45).
    expected = played(story(until="day 1"), chased())
    data = story(
        until="day 3",
        expect={"timeline": expected.timeline_lines(), "end": list(expected.end)},
    )
    simulation = played(data, chased())
    assert simulation.difference() == (
        "the story's expectation fails:\n"
        "  expected, at the end: status: open\n"
        "  printed, at day 2 00:00: chase_review#1 on 2d after started review#1: starting chase"
    )
    # What it did, expected exactly, holds.
    holding = story(
        until="day 3",
        expect={"timeline": simulation.timeline_lines(), "end": list(simulation.end)},
    )
    assert played(holding, chased()).difference() is None


# --- Slice 5: stories as tests, and each clause's witness a story ---

STORIES = sorted(EXAMPLES.glob("*/stories/*.json"))


@pytest.mark.parametrize("path", STORIES, ids=lambda path: f"{path.parent.parent.name}/{path.stem}")
def test_every_story_holds(path: Path) -> None:
    # A story under examples/ states what it expects, and a failing expectation fails here.
    story, case = read_story(path)
    assert story.expect is not None, f"{path.name} states nothing it expects"
    assert simulate(story, case, CATALOG).difference() is None


# Each clause a reading may say (brief, D45), its witness story in examples/witnesses/stories/,
# the rule whose reading says it, and the line that shows the engine doing what it says.
WITNESSES = {
    "condition read when it fires": (
        "condition-read-when-it-fires",
        "chase_review",
        "chase_review#1 on answered review: starting chase",
    ),
    "timer's condition read when it fires": (
        "timers-condition-read-when-it-fires",
        "chase_review",
        "chase_review#1 on 2d after opened: starting chase",
    ),
    "actions in the engine's order": (
        "actions-in-the-engines-order",
        "chase_review",
        "chase_review#1 on answered review: reaching owed_known",
    ),
    "timer on a run": (
        "timer-on-a-run",
        "chase_review",
        "cancelled chase_review, 2d after started review#1: review#1 is done",
    ),
    "timer on an instant": (
        "timer-on-an-instant",
        "chase_review",
        "chase_review#1 on 30d after answered review#1: starting chase",
    ),
    "timer holds the case": (
        "timer-holds-the-case",
        "chase_review",
        "timer: chase_review: 30d after answered review#1, due 2026-02-01T00:00:00Z",
    ),
    "listening": ("listening", "chase_review", "closed: nothing left to do"),
    "untrusted data decides nothing": (
        "untrusted-data-decides-nothing",
        "close_it",
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data",
    ),
    "set value carries what it read": (
        "set-value-carries-what-it-read",
        "work_out_owed",
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener",
    ),
    "start checked against inputs": (
        "start-checked-against-inputs",
        "close_it",
        (
            "needs attention: letter#1: letters.draft@2 takes to_customer only from a system or a "
            "person, never from untrusted data"
        ),
    ),
    "what a stop does": (
        "what-a-stop-does",
        "flag_large",
        "flagged: pay#1 completed after its stop was requested by flag_large#1",
    ),
    "a start is a proposal": (
        "a-start-is-a-proposal",
        "flag_large",
        "asked pay.approval#1: approval of pay by support-lead",
    ),
    "reaching closes the case": (
        "reaching-closes-the-case",
        "flag_large",
        "cancelled review#1: the case closes when large is reached",
    ),
    "only while the case decides": (
        "only-while-the-case-decides",
        "flag_large",
        (
            "flag_large#1 on reached paid: not applied: paid is reached, so the case closes and "
            "nothing new is decided"
        ),
    ),
    "every rule": (
        "every-rule",
        "flag_large",
        (
            "needs attention: flag_large#1: flag_large's condition approved_amount > 1000 can't be "
            "evaluated: approved_amount has no value"
        ),
    ),
}


def test_every_clause_has_a_witness_story() -> None:
    # The reading says it, the story's run shows the engine doing it, and the story holds: a
    # clause can't be added without one, nor drift from the engine (brief, D45).
    assert set(WITNESSES) == set(CLAUSES)
    for clause, (name, rule, evidence) in WITNESSES.items():
        story, case = read_story(EXAMPLES / "witnesses" / "stories" / f"{name}.json")
        simulation = simulate(story, case, CATALOG)
        assert simulation.difference() is None, name
        printed = str(simulation)
        reading = next(reading for reading in simulation.readings if reading.name == rule)
        assert clause in reading.clauses or (clause == "every rule" and EVERY_RULE in printed)
        assert evidence in printed, name


# --- Slice 7: the guide ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
SIMULATING = GUIDE.split("## Simulating a story\n")[1].split("\n## ")[0]
GUIDES_STORY = EXAMPLES / "refund" / "stories" / "nobody-reviews.json"


def test_the_guides_story_is_what_simulate_prints() -> None:
    # The guide's story is the file, less what it expects, and its output is what simulate
    # prints, word for word, so the guide can't drift from the engine.
    blocks = SIMULATING.split("```")[1::2]
    written = next(block for block in blocks if block.startswith("json\n"))
    printed = next(block for block in blocks if block.startswith("\n"))
    story_file = json.loads(GUIDES_STORY.read_text())
    del story_file["expect"]
    assert json.loads(written.removeprefix("json\n")) == story_file
    assert f"ventoux simulate {GUIDES_STORY.relative_to(EXAMPLES.parent)}" in SIMULATING
    story, case = read_story(GUIDES_STORY)
    assert printed.removeprefix("\n") == str(simulate(story, case, CATALOG))
