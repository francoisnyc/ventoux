"""A contract's readable diff, layer 13d (brief, D57; design question 16).

Two promises, as the contract hash reads them, compared path by path: `retry.maximum_attempts:
5 -> 9`. See docs/layers/13-diff.md (13d).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from test_catalog import catalog_of, lookup_contract
from test_diff import ROOT

from ventoux.core.contract import Display, RetryPolicy, Timeouts
from ventoux.core.contract_hash import contract_hash, promise_hash
from ventoux.core.hash_check import check_hashes
from ventoux.core.promise import PromiseUnreadable, promise_changes, promise_of
from ventoux.testing import CATALOG
from ventoux.tooling.cli import main

# --- Slice 0: a promise read path by path --------------------------------------------------------


def test_a_value_that_isnt_json_is_refused() -> None:
    # Fail closed: a promise holding something no JSON holds is never skipped (brief, D57).
    before = promise_of(lookup_contract())
    after = dict(before) | {"retry": {"maximum_attempts": {5, 9}}}
    with pytest.raises(
        PromiseUnreadable, match="^retry.maximum_attempts holds a set, which a promise never holds$"
    ):
        promise_changes(before, after)


def test_a_value_changed_is_said_path_by_path() -> None:
    before = promise_of(lookup_contract())
    after = promise_of(
        lookup_contract(
            retry=RetryPolicy(maximum_attempts=9, initial_interval=1, backoff_coefficient=2)
        )
    )
    assert promise_changes(before, after) == ["retry.maximum_attempts: 3 -> 9"]


def test_a_key_one_side_has_is_added_or_removed_with_its_value() -> None:
    class Wider(BaseModel):
        order_id: str
        reason: str

    before, after = promise_of(lookup_contract()), promise_of(lookup_contract(input=Wider))
    assert promise_changes(before, after) == [
        'input.properties.reason: added {"title": "Reason", "type": "string"}',
        'input.required: ["order_id"] -> ["order_id", "reason"]',
        "input.title: LookupInput -> Wider",
    ]
    assert promise_changes(after, before)[0] == (
        'input.properties.reason: removed {"title": "Reason", "type": "string"}'
    )


def answering(*outcomes: str) -> dict[str, Any]:
    """A lookup declaring `outcomes`, each with its title, in the order given."""
    titles = {outcome: outcome.replace("_", " ").capitalize() for outcome in outcomes}
    display = Display(title="Look up an order", description="Reads it.", outcomes=titles)
    return promise_of(lookup_contract(outcomes=list(outcomes), display=display))


def test_a_list_is_shown_whole_and_outcomes_never_by_their_order() -> None:
    before, after = answering("not_found", "closed"), answering("closed", "not_found", "held")
    assert promise_changes(before, after) == [
        'outcomes: ["closed", "not_found"] -> ["closed", "held", "not_found"]'
    ]
    assert promise_changes(before, answering("closed", "not_found")) == []


def test_a_class_renamed_shows_the_cause_the_hash_hides() -> None:
    # Design question 16: renaming the input class changes its JSON Schema, so the hash, with no
    # change anyone meant. The diff names it.
    class OrderQuery(BaseModel):
        order_id: str

    before, after = promise_of(lookup_contract()), promise_of(lookup_contract(input=OrderQuery))
    assert promise_changes(before, after) == ["input.title: LookupInput -> OrderQuery"]


# --- Slice 1: the hash check says what changed ---------------------------------------------------

LOOKUP = "orders.lookup@1"
LONGER = Timeouts(start_to_close=30, schedule_to_start=60)


def test_a_promise_given_that_isnt_the_lockfiles_is_never_compared() -> None:
    # The promise given must hash to what contracts.lock.json records, or it is someone else's
    # promise: what changed can't be said (brief, D57).
    recorded = {LOOKUP: contract_hash(lookup_contract())}
    other = promise_of(lookup_contract(risk="medium"))
    assert check_hashes(
        catalog_of(lookup_contract(timeouts=LONGER)), recorded, {LOOKUP: other}
    ) == [
        (
            "orders.lookup@1 changed without a new version: register it as orders.lookup@2.\n"
            "  what changed can't be said: the promise given for orders.lookup@1 isn't the one "
            "contracts.lock.json records"
        )
    ]


def test_a_contract_changed_in_place_says_what_changed() -> None:
    recorded = {LOOKUP: contract_hash(lookup_contract())}
    before = {LOOKUP: promise_of(lookup_contract())}
    assert check_hashes(catalog_of(lookup_contract(timeouts=LONGER)), recorded, before) == [
        (
            "orders.lookup@1 changed without a new version: register it as orders.lookup@2.\n"
            "  timeouts.start_to_close: 10 -> 30"
        )
    ]


def test_a_contract_with_no_promise_given_says_so() -> None:
    recorded = {LOOKUP: contract_hash(lookup_contract())}
    assert check_hashes(catalog_of(lookup_contract(timeouts=LONGER)), recorded, {}) == [
        (
            "orders.lookup@1 changed without a new version: register it as orders.lookup@2.\n"
            "  what changed can't be said: no promise was given for orders.lookup@1"
        )
    ]


LOCK = ROOT / "contracts.lock.json"


def test_hashes_refuses_promises_it_cant_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Fail closed: a promises file that can't be read stops the check, naming it (exit 2).
    given = tmp_path / "promises.json"
    given.write_text("{not json")
    assert main(["hashes", "--lock", str(LOCK), "--before", str(given)]) == 2
    assert capsys.readouterr().err.startswith(f"{given}: isn't JSON")


def test_hashes_passes_when_every_contract_matches(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["hashes", "--lock", str(LOCK)]) == 0
    assert capsys.readouterr().out == "every contract matches contracts.lock.json\n"


def test_the_base_commits_promises_say_what_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # As CI will run it (13e): the base commit prints its promises; here orders.lookup@1 had a
    # 5-second timeout there, and the lockfile records that promise's hash.
    assert main(["promises"]) == 0
    promises = json.loads(capsys.readouterr().out)
    assert promises == {c.reference: promise_of(c) for c in CATALOG.contracts()}
    promises[LOOKUP]["timeouts"]["start_to_close"] = 5
    recorded = json.loads(LOCK.read_text()) | {LOOKUP: promise_hash(promises[LOOKUP])}
    lock, before = tmp_path / "contracts.lock.json", tmp_path / "promises.json"
    lock.write_text(json.dumps(recorded))
    before.write_text(json.dumps(promises))
    assert main(["hashes", "--lock", str(lock), "--before", str(before)]) == 1
    said = capsys.readouterr().out
    assert said == (
        "orders.lookup@1 changed without a new version: register it as orders.lookup@3.\n"
        "  timeouts.start_to_close: 5 -> 10\n"
    )
    # The activities guide shows this run as it prints.
    guide = (ROOT / "docs" / "guides" / "activities.md").read_text()
    block = guide.split("**What changed, path by path.**")[1].split("```\n")[1]
    command, printed = block.split("\n", 1)
    assert command == "$ ventoux hashes --lock contracts.lock.json --before base-promises.json"
    assert printed == said
