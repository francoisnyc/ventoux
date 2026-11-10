# Records fresh histories with OLDER code (an older commit's own Temporal tests, run in a temporary git worktree) and replays each with today's code, comparing what the replay rebuilds with what was recorded.
"""The repository keeps 34 recorded histories. This makes hundreds more, each recorded by the code
of an earlier merge running its own Temporal tests (rules, events, timers, approvals, plan and
workflow steps, change requests, migrations, the registry, child cases, the export), and asks
today's code to replay every one. A replay Temporal refuses is a path decided differently since,
with no engine version or patch marker behind it (brief, D51); a replay that passes but hands
Temporal another payload (an activity's input, a child's start, the next run's start, the result,
an update's answer) is the same, unseen by Temporal.

Run: uv run python reviews/2026-11/probes/p2_old_recordings.py <commit> [test file pattern]
Step 1 runs pytest in the worktree with p2_capture_plugin.py (PYTHONPATH names the old src).
Step 2 runs in a subprocess with today's src and the OLD tests on the path, so each history is
replayed with the workflow class its test defined, on today's engine. The worktree is removed
at the end; nothing in the project's files changes."""

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]


def replay_all(captured: Path, tree: Path) -> None:
    """Step 2, in its own process: today's `ventoux`, the old tree's tests."""
    import importlib

    sys.path[:0] = [str(tree / "tests"), str(tree / "examples" / "quickstart")]
    from p2_harness import compare, recorded, replayed, run
    from temporalio.api.enums.v1 import EventType
    from temporalio.client import WorkflowHistory

    import ventoux
    from ventoux.temporal.converter import data_converter
    from ventoux.tooling.keys import FileKeys

    assert str(REPOSITORY / "src") in ventoux.__file__, ventoux.__file__
    counts: Counter[str] = Counter()
    for path in sorted(captured.glob("*.json")):
        if path.name.endswith(".keys.json"):
            continue
        kept = json.loads(path.read_text())
        label = f"{kept['test']} {kept['id']} ({kept['type']}, {kept['run'][:8]})"
        if kept["class"] is None or "<locals>" in kept["class"][1]:
            counts["no class to replay with"] += 1
            continue
        try:
            module = importlib.import_module(kept["class"][0])
            cases = getattr(module, kept["class"][1])
        except Exception as error:  # noqa: BLE001
            counts["its test module no longer imports with today's code"] += 1
            print(f"UNLOADED {label}: {type(error).__name__}: {str(error)[:200]}")
            continue
        keys = Path(tempfile.mkdtemp(prefix="p2-k-")) / "keys.json"
        if kept["keys"]:
            keys.write_text(Path(kept["keys"]).read_text())
        converter = data_converter(FileKeys(keys))
        history = WorkflowHistory.from_json(kept["id"], kept["history"])
        try:
            was = run(recorded(history, converter))
            now = run(replayed(history, [cases], converter))
        except Exception as error:  # noqa: BLE001
            if "was destroyed when it was forgotten" in str(error) or "there is no key" in str(error):
                counts["its case was forgotten or its key withheld by the test: no key, no replay (brief, D32)"] += 1
            else:
                counts["could not be read"] += 1
                print(f"UNREAD {label}: {type(error).__name__}: {str(error)[:300]}")
            continue
        said, _, _ = compare(was, now)
        last = history.events[-1].event_type
        mid_task = last in (
            EventType.EVENT_TYPE_WORKFLOW_TASK_SCHEDULED, EventType.EVENT_TYPE_WORKFLOW_TASK_STARTED
        )
        kept_lines = []
        for line in said:
            if "replay replay-" in line or "replay 'replay-" in line:
                continue  # the replayer's own task queue, where the history says the worker's
            if mid_task and " recorded, " in line and " on replay" in line:
                # The history was fetched while a workflow task was under way: the replay runs
                # that task, and what it asks for was never recorded. Not a difference.
                few, many = (int(word) for word in line.split() if word.rstrip(",").isdigit())
                if many > few:
                    continue
            kept_lines.append(line)
        said = kept_lines
        if now["failure"] and (
            "was destroyed when it was forgotten" in now["failure"]
            or "there is no key for" in now["failure"]
        ):
            counts["its case was forgotten or its key withheld by the test: no key, no replay (brief, D32)"] += 1
        elif now["failure"]:
            counts["REFUSED by Temporal on replay"] += 1
            print(f"REFUSED {label}: {now['failure'][:260]}")
        elif said:
            counts["DIFFERENT with no error"] += 1
            print(f"DIFFERENT {label}")
            for line in said[:6]:
                print(f"    {line[:700]}")
        else:
            counts["equal"] += 1
    print("P2COUNTS " + json.dumps(counts))


def main() -> None:
    commit = sys.argv[1]
    pattern = sys.argv[2] if len(sys.argv) > 2 else "test_temporal*.py"
    work = Path(tempfile.mkdtemp(prefix="p2-old-"))
    tree, captured = work / "tree", work / "captured"
    again = os.environ.get("P2_CAPTURED")  # histories an earlier run of step 1 kept: skip step 1
    if again:
        captured = Path(again)
    else:
        captured.mkdir()
    subprocess.run(
        ["git", "-C", str(REPOSITORY), "worktree", "add", "--detach", "-q", str(tree), commit],
        check=True,
    )
    try:
        files = sorted(str(path) for path in (tree / "tests").glob(pattern))
        environment = dict(
            os.environ, P2_CAPTURE_DIR=str(captured), PYTHONPATH=f"{tree / 'src'}:{HERE}"
        )
        if again:
            print(f"step 1, at {commit}: skipped; the histories kept in {captured} are used")
        else:
            ran = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p",
                 "p2_capture_plugin", *files],
                cwd=tree, env=environment, capture_output=True, text=True, check=False,
            )
            print(f"step 1, at {commit}: {len(files)} test files: "
                  f"{(ran.stdout.strip().splitlines() or ['?'])[-1]}")
            print(f"         kept in {captured} (P2_CAPTURED={captured} replays them again)")
        histories = [p for p in captured.glob("*.json") if not p.name.endswith(".keys.json")]
        print(f"         {len(histories)} histories recorded by the code at {commit}")
        environment = dict(os.environ, PYTHONPATH=f"{REPOSITORY / 'src'}:{HERE}")
        done = subprocess.run(
            [sys.executable, str(HERE / "p2_old_recordings.py"), "--replay", str(captured), str(tree)],
            env=environment, capture_output=True, text=True, check=False,
        )
        counts: dict[str, Any] = {}
        for line in done.stdout.splitlines():
            if line.startswith("P2COUNTS "):
                counts = json.loads(line.removeprefix("P2COUNTS "))
            elif not line.startswith("\x1b"):
                print(line)
        if not counts:
            print(done.stderr[-1500:])
        print(f"step 2, with today's code: {counts}")
    finally:
        subprocess.run(
            ["git", "-C", str(REPOSITORY), "worktree", "remove", "--force", str(tree)], check=False
        )
        subprocess.run(["git", "-C", str(REPOSITORY), "worktree", "prune"], check=False)
    bad = counts.get("REFUSED by Temporal on replay", 0) + counts.get("DIFFERENT with no error", 0)
    if not counts:
        print("RESULT: BROKEN - the probe itself did not finish; nothing shown either way")
    elif bad:
        print(f"RESULT: BROKEN - of the histories recorded at {commit}, today's code refuses or "
              f"rebuilds differently {bad} (each named above); {counts.get('equal', 0)} equal")
    else:
        print(f"RESULT: HELD - {counts.get('equal', 0)} histories recorded at {commit} replay "
              "with today's code and rebuild what they recorded")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--replay":
        replay_all(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        main()
