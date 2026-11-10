# Shows that a request to forget a case stamps its audit records with the code's ENGINE constant, not with anything its history recorded, and that a replay raises nothing when the constant has moved.
"""Replays the repository's own fixture at_19b_forget_request (recorded at engine 3) twice: as the
code is, and with `ventoux.case.engine.ENGINE` set to 4 IN MEMORY, as it will be once a fourth
engine version exists (no file is changed). Temporal compares a scheduled activity by its type and
ID only, so the replay passes; the probe compares the input of each `ventoux.audit.append` with
the one the history recorded. Reaches past the supported names as p2_harness.py says."""

import json
from typing import Any

from p2_fixtures import load
from p2_harness import recorded, replayed, run

import ventoux.case.engine as engine


def engines(activities: list[dict[str, Any]]) -> list[int]:
    """The engine version each record sent to the audit store says."""
    return [
        record["engine"]
        for each in activities
        if each["type"] == "ventoux.audit.append"
        for record in json.loads(each["input"][0][0])["records"]
    ]


def main() -> None:
    history, workflows, converter = load("at_19b_forget_request")
    was = run(recorded(history, converter))
    print(f"recorded in the history: each record's engine: {engines(was['activities'])}")
    now = run(replayed(history, workflows, converter))
    print(f"replayed with ENGINE = {engine.ENGINE}: error {now['failure']}; "
          f"engines {engines(now['activities'])}")
    kept, engine.ENGINE = engine.ENGINE, 4
    try:
        later = run(replayed(history, workflows, converter))
    finally:
        engine.ENGINE = kept
    print(f"replayed with ENGINE = 4: error {later['failure']}; engines "
          f"{engines(later['activities'])}")
    if later["failure"] is None and engines(later["activities"]) != engines(was["activities"]):
        print("RESULT: BROKEN - with the constant moved, the replay rebuilds records that say "
              "another engine version than the ones recorded, and nothing notices")
    else:
        print("RESULT: HELD - the replay rebuilds the records as recorded, or refuses")


if __name__ == "__main__":
    main()
