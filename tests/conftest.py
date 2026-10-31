"""After each decision, in every test: nothing pending is silent.

Checked after every decision the in-memory driver (`ventoux.case.memory.Driver`) makes, and every
decision a test asks of `decide` itself. See docs/layers/fix-retry-rejected.md, "The invariant".
And around every test: no thread it started outlives it (`thread_guard`).
"""

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a helper there imports by
# its name.
from invariants import Silent, unshown

# Around every test, too: no thread it started outlives it (docs/layers/fix-replayer-threads.md).
from thread_guard import no_thread_outlives_its_test  # noqa: F401  (pytest finds it here)

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
    if silent := unshown(case, decided):
        raise Silent(f"after {type(event).__name__}, pending and shown nowhere: {silent}")
    return decided, commands


# pytest: `autouse` runs this fixture around every test; `monkeypatch` puts back what it replaced
# once the test ends; `request.module` is the test's own module.
@pytest.fixture(autouse=True)
def every_decision_shows_what_is_pending(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ventoux.case.memory, "decide", checked)
    # A test module that imported `decide` itself calls it by its own name: wrapped there too.
    if getattr(request.module, "decide", None) is decide:
        monkeypatch.setattr(request.module, "decide", checked)
