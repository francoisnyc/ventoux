"""The engine version a case decides as (layer 12b; brief, D51).

See docs/layers/12-releases.md (12b).
"""

from collections.abc import Callable

import pytest

from ventoux.case.engine import ENGINE, EngineUnknown, opening_engine
from ventoux.case.state import CaseState
from ventoux.temporal.carried import state_as_data, state_from_data


def test_a_state_from_before_12b_is_engine_1() -> None:
    # A state carried before 12b says no version: it was decided by version 1 (brief, D51).
    carried = state_as_data(CaseState("refund-1/run-1"))
    assert carried["engine"] == ENGINE == 1
    del carried["engine"]
    assert state_from_data(carried).engine == 1


def test_an_unknown_engine_version_is_refused() -> None:
    # A version newer than this code is never read as an older one: the workflow task stops, and
    # the case waits for code that knows it (brief, D17, D51).
    carried = state_as_data(CaseState("refund-1/run-1")) | {"engine": 2}
    with pytest.raises(EngineUnknown) as refusal:
        state_from_data(carried)
    assert str(refusal.value) == (
        "this case decides as engine 2, which this code doesn't know (it knows 1): deploy code "
        "that knows it"
    )


def asking(yes: set[int]) -> tuple[list[int], Callable[[int], bool]]:
    """What was asked, and an `asked` that says yes to the versions in `yes`."""
    asked: list[int] = []

    def ask(version: int) -> bool:
        asked.append(version)
        return version in yes

    return asked, ask


def test_the_opening_asks_the_newest_version_first() -> None:
    # On Temporal each version above 1 is a patch marker: a new case's run says yes to the newest,
    # a replayed one to the version its history recorded (research 1.5; brief, D51).
    asked, ask = asking({3, 2})
    assert opening_engine((3, 2, 1), ask) == 3 and asked == [3]
    asked, ask = asking({2})
    assert opening_engine((3, 2, 1), ask) == 2 and asked == [3, 2]
    # No marker: a history recorded under version 1, which writes none.
    asked, ask = asking(set())
    assert opening_engine((3, 2, 1), ask) == 1 and asked == [3, 2]


def test_one_version_asks_nothing() -> None:
    # With version 1 alone nothing is asked, so no marker is written: a case opened under 12b has
    # a history of the same shape as one opened before it.
    asked, ask = asking({1})
    assert opening_engine((1,), ask) == 1 and asked == []
