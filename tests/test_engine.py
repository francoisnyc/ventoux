"""The engine version a case decides as (layer 12b; brief, D51).

See docs/layers/12-releases.md (12b).
"""

import pytest

from ventoux.case.engine import ENGINE, EngineUnknown
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
