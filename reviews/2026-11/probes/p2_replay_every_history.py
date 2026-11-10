# Replays every recorded history under tests/histories and compares what the replay rebuilds (activity inputs and timeouts, child starts, signals, timers, update answers, the result or the next run's start) with what the history recorded.
"""A replay that raises nothing is the tests' whole check; this adds the comparison. Prints one
line per history, then each difference in full. See p2_harness.py for what is compared and how.
Run: uv run python reviews/2026-11/probes/p2_replay_every_history.py [name ...]"""

import sys

from p2_fixtures import FIXTURES, every_history_file, load
from p2_harness import compare, recorded, replayed, run


async def main() -> int:
    names = sys.argv[1:] or every_history_file()
    different = 0
    details: list[str] = []
    additions: list[str] = []
    unchecked: list[str] = []
    print(f"{'history':44} {'type':16} ev  replay  end(rec)   acts chld sigs tmrs upd  markers  equal?")
    for name in names:
        if name not in FIXTURES:
            print(f"{name:44} no test replays this file as a history")
            continue
        history, workflows, converter = load(name)
        was = await recorded(history, converter)
        now = await replayed(history, workflows, converter)
        kind = history.events[0].workflow_execution_started_event_attributes.workflow_type.name
        said, added, options = compare(was, now)
        if added:
            additions.append(f"--- {name}: " + "; ".join(added)[:900])
        if options:
            unchecked.append(f"--- {name}")
            unchecked.extend("    " + line for line in options)
        refused_expected = FIXTURES[name][2]
        ok = "refused" if now["failure"] else "ok"
        end = was["end"][0] if was["end"] else "open"
        equal = "n/a (refused, as its test expects)" if now["failure"] and refused_expected else (
            "EQUAL" if not said and not now["failure"] else "DIFFERENT")
        if equal == "DIFFERENT":
            different += 1
            details.append(f"--- {name}: {now['failure'] or ''}")
            details.extend("    " + line for line in said)
        print(
            f"{name:44} {kind:16} {was['events']:3} {ok:7} {end:10} "
            f"{len(was['activities']):2}/{len(now['activities']):<2} "
            f"{len(was['children'])}/{len(now['children'])}  "
            f"{len(was['signals'])}/{len(now['signals'])}  "
            f"{len(was['timers'])}/{len(now['timers'])}  "
            f"{len(was['updates'])}/{len(now['updates'])}  "
            f"{','.join(m.removeprefix('ventoux-') for m in was['markers']) or '-':8} {equal}"
        )
    print("\nDifferences in what the record holds:")
    print("\n".join(details) or "    none")
    print("\nOnly in the replay (fields added since the recording; nothing recorded to compare):")
    print("\n".join(additions) or "    none")
    print("\nOptions Temporal doesn't compare on replay, which the code now asks for otherwise:")
    print("\n".join(unchecked) or "    none")
    return different


if __name__ == "__main__":
    different = run(main())
    if different:
        print(f"RESULT: BROKEN - {different} histories replay with no error but rebuild something "
              "other than what was recorded (see the lines above)")
    else:
        print("RESULT: HELD - every history that replays rebuilds what it recorded, in every "
              "payload this probe compares")
