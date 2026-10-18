"""Checks every in-memory test gets: after each decision, nothing pending is silent.

See docs/layers/fix-retry-rejected.md, "The invariant".
"""

from collections.abc import Iterator

import pytest
from invariants import unshown

import ventoux.case.memory
from ventoux.case.definition import CaseDefinition
from ventoux.case.runtime import decide
from ventoux.case.state import CaseState, Command, Event
from ventoux.core.catalog import Catalog


def checked(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: Event
) -> tuple[CaseState, list[Command]]:
    """`decide`, then the invariant on the state it gives: a silent pending item fails the test
    that made it, naming the event."""
    decided, commands = decide(case, catalog, state, event)
    silent = unshown(case, decided)
    assert not silent, f"after {type(event).__name__}, pending and shown nowhere: {silent}"
    return decided, commands


# pytest: `autouse` runs this fixture around every test; `monkeypatch` puts the in-memory
# driver's `decide` back once the test ends.
@pytest.fixture(autouse=True)
def every_decision_shows_what_is_pending(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(ventoux.case.memory, "decide", checked)
    yield
