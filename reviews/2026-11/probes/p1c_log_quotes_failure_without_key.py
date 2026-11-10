# Shows the worker's log quoting an activity failure's message in plain text (here, a national ID) when the failure can't be sealed: the key service is unavailable at that moment, or the case's key is gone.
"""Run: uv run python reviews/2026-11/probes/p1c_log_quotes_failure_without_key.py

The lookup fails saying what it was given, as a careless system's error would (the repository's
own test does the same, with the key at hand). Here the key service stops answering just before
the failure is sealed, as Vault being down would (`KeyUnavailable`, D78).

Supported names used: start_case, report, case_worker, data_converter, FileKeys. Past them:
`ventoux.tooling.keys.KeyUnavailable`, a `FileKeys` subclass that can be down,
`ventoux.testing`, the tests' server harness.
"""

import logging
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until
from temporalio.exceptions import ApplicationError

from ventoux.temporal.cases import start_case
from ventoux.testing import FAKES, DevelopmentCases
from ventoux.tooling.keys import FileKeys, KeyUnavailable

NATIONAL_ID = "1 85 05 78 006 084 36"


class Keys(FileKeys):
    """The development key file, standing for a key service that can stop answering."""

    down = False

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        if Keys.down:
            raise KeyUnavailable("the key service at vault.example didn't answer in 10 seconds")
        return super().seal(case, data, part)


def quoting(inputs: dict[str, Any]) -> dict[str, Any]:
    Keys.down = True  # the key service goes down while the lookup runs
    raise ApplicationError(f"no record for {inputs['order_id']}", non_retryable=True)


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "national_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"},
            }
        },
        "steps": {
            "look": {
                "kind": "activity",
                "display": {"title": "Look the ID up"},
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "national_id"}},
            }
        },
    }


class Kept(logging.Handler):
    """Every log record, formatted as a handler would write it."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(logging.Formatter().format(record))


async def scenario(setup: Setup) -> list[str]:
    case = await start_case(
        setup.client, DevelopmentCases, claim(), {"national_id": NATIONAL_ID}, "claim-1", QUEUE
    )
    failed = await until(case, lambda now: bool(now.needs_attention))
    return failed.needs_attention


kept = Kept()
logging.getLogger().addHandler(kept)
logging.getLogger().setLevel(logging.DEBUG)
attention = on_temporal(scenario, activities={**FAKES, "orders.lookup@1": quoting}, keys_class=Keys)
print("the case says:", attention)
quoted = [line for line in kept.lines if NATIONAL_ID in line]
for line in quoted:
    print("LOGGED:", line[:400])
if quoted:
    print(
        f"RESULT: BROKEN - the worker's log holds the national ID in plain text, {len(quoted)} "
        "time(s): the SDK logs the activity's own message when sealing its failure fails"
    )
else:
    print("RESULT: HELD - the log keeps only the exception's type, key service down or not")
