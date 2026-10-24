"""A contract's readable diff, layer 13d (brief, D57; design question 16).

Two promises, as the contract hash reads them, compared path by path: `retry.maximum_attempts:
5 -> 9`. See docs/layers/13-diff.md (13d).
"""

from typing import Any

import pytest
from pydantic import BaseModel
from test_catalog import lookup_contract

from ventoux.core.contract import Display, RetryPolicy
from ventoux.core.promise import PromiseUnreadable, promise_changes, promise_of

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
