# Shows that a case workflow's class settings (events_per_run, audit_bound) decide where a recorded run switches or holds, with nothing in the history or the state recording the value they had.
"""The engine version is recorded (a patch marker, then the state), so a history replays as the
version it opened at. The class settings read by the same workflow code are not: a deployment
that lowers `events_per_run` or `audit_bound` on its case workflow replays every open run with the
new value. Replays two of the repository's own fixtures against a class that differs only by one
setting. Reaches past the supported names for the fixtures' test classes (p2_fixtures.py)."""

from typing import Any

from p2_fixtures import load
from p2_harness import replayed, run
from p2_time_classes import HoldsSooner, SwitchesSooner  # each differs by one setting


def main() -> None:
    broken = 0
    for name, changed in (
        ("before_12b_paid", SwitchesSooner),
        ("at_19b_refund_export_retried", HoldsSooner),
    ):
        history, own, converter = load(name)
        as_recorded: dict[str, Any] = run(replayed(history, own, converter))
        with_setting: dict[str, Any] = run(replayed(history, [changed], converter))
        print(f"{name}:")
        print(f"  with the class that recorded it ({own[0].__name__}): "
              f"{as_recorded['failure'] or 'replays'}")
        print(f"  with {changed.__name__}: {with_setting['failure'] or 'replays'}")
        broken += as_recorded["failure"] is None and with_setting["failure"] is not None
    if broken:
        print(f"RESULT: BROKEN - {broken} recorded runs no longer replay once a class setting is "
              "lowered: the setting decides the path, and nothing records it")
    else:
        print("RESULT: HELD - both fixtures replay whatever the class settings are")


if __name__ == "__main__":
    main()
