# Replays each recorded history twice, with the code that recorded it (an old commit, checked out in a temporary git worktree) and with today's code, and compares the whole state each rebuilds.
"""A history that is still open records no result to compare a replay with. So this asks the code
that recorded it: the state the old code rebuilds from the history (the report, and the state as
it would cross continue-as-new) against the state today's code rebuilds. A value the old code
held and today's gives otherwise is a path decided differently with no error (brief, D51).

The worktrees are made under a temporary directory and removed at the end; nothing in the
project's files changes. Reaches past the supported names as p2_harness.py says.
Run: uv run python reviews/2026-11/probes/p2_time_travel.py"""

import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]

# Each fixture, the commit whose code recorded it (as its test's comment says), its workflow ID,
# and the workflow class, by name (p2_time_classes.py).
TRAVELS: dict[str, tuple[str, str, str]] = {
    "before_12b_paid": ("b734098", "refund-1", "DevelopmentCases"),
    "before_12b_waiting": ("b734098", "refund-1", "DevelopmentCases"),
    "before_12b_switched": ("b734098", "refund-1", "EveryEventCases"),
    "before_12c_waiting": ("5801ca0", "refund-1", "DevelopmentCases"),
    "before_12c_switched": ("5801ca0", "refund-1", "EveryEventCases"),
    "before_12c_forgotten_by_its_opener": ("5801ca0", "claim-7", "DevelopmentCases"),
    "before_12c_forget_request": ("5801ca0", "claim-7/forget", "DevelopmentForget"),
    "before_12d_released_waiting": ("66e2cff", "refund-1", "DevelopmentCases"),
    "before_12d_released_open": ("66e2cff", "refund-1", "DevelopmentCases"),
    "before_12d_pending_edit_switched": ("66e2cff", "refund-1", "EveryEventCases"),
    "before_12e_draft_waiting": ("2fde255", "refund-1", "DevelopmentCases"),
    "before_12e_released_waiting": ("2fde255", "refund-1", "DevelopmentCases"),
    "before_12e_released_switched": ("2fde255", "refund-1", "EveryEventCases"),
    "before_12e_migrated_switched": ("2fde255", "refund-1", "EveryEventCases"),
    "before_12e_closed": ("2fde255", "refund-1", "DevelopmentCases"),
    "before_18d_case_step_failed_switched": ("dc2407e", "claim-2", "SwitchingCases"),
    "before_18d_production_case": ("dc2407e", "claim-3", "ProductionCases"),
    "before_18d_registry": ("dc2407e", "ventoux-registry/production", "RegistryWorkflow"),
    "at_19b_forget_request": ("43da6ca", "claim-7/forget", "DevelopmentForget"),
}


def child(name: str) -> None:
    """In a subprocess whose PYTHONPATH names one tree: replay `name`, print what was rebuilt."""
    import shutil

    from p2_harness import replayed, run
    from temporalio.client import WorkflowHistory

    import p2_time_classes
    import ventoux
    from ventoux.temporal.converter import data_converter
    from ventoux.tooling.keys import FileKeys

    _, id, class_name = TRAVELS[name]
    path = REPOSITORY / "tests" / "histories" / f"{name}.json"
    keys = Path(tempfile.mkdtemp(prefix="p2-keys-")) / "keys.json"
    if path.with_suffix(".keys.json").exists():
        shutil.copy(path.with_suffix(".keys.json"), keys)
    history = WorkflowHistory.from_json(id, path.read_text())
    seen = run(replayed(history, [getattr(p2_time_classes, class_name)], data_converter(FileKeys(keys))))
    seen["code"] = ventoux.__file__
    print("P2RESULT " + json.dumps(seen, default=str))


def read(value: Any) -> Any:
    """`value` with each JSON text in it read, so two of them compare field by field."""
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value, parse_float=Decimal)
        except ValueError:
            return value
    if isinstance(value, list):
        return [read(each) for each in value]
    if isinstance(value, dict):
        return {key: read(each) for key, each in value.items()}
    return value


def rebuilt(name: str, root: Path) -> dict[str, Any]:
    environment = dict(os.environ, P2_ROOT=str(root), PYTHONPATH=f"{root / 'src'}:{HERE}")
    done = subprocess.run(
        [sys.executable, str(HERE / "p2_time_travel.py"), "--child", name],
        env=environment, capture_output=True, text=True, timeout=300, check=False,
    )
    for line in done.stdout.splitlines():
        if line.startswith("P2RESULT "):
            return json.loads(line.removeprefix("P2RESULT "))  # type: ignore[no-any-return]
    return {"failure": "the replay didn't run: " + (done.stderr.strip().splitlines() or ["?"])[-1]}


def main() -> None:
    from p2_harness import deep

    names = sys.argv[1:] or list(TRAVELS)
    work = Path(tempfile.mkdtemp(prefix="p2-trees-"))
    trees: dict[str, Path] = {}
    different = unread = 0
    try:
        for commit in sorted({TRAVELS[name][0] for name in names}):
            trees[commit] = work / commit
            subprocess.run(
                ["git", "-C", str(REPOSITORY), "worktree", "add", "--detach", "-q",
                 str(trees[commit]), commit], check=True,
            )
        for name in names:
            commit = TRAVELS[name][0]
            then, now = rebuilt(name, trees[commit]), rebuilt(name, REPOSITORY)
            if then.get("failure") or now.get("failure"):
                unread += 1
                print(f"{name}: at {commit}: {then.get('failure')} | today: {now.get('failure')}")
                continue
            assert str(trees[commit]) in then["code"] and str(REPOSITORY) in now["code"]
            changed: list[str] = []
            added: list[str] = []
            compared = []
            for part in ("state", "carried"):
                if then.get(part) is None or now.get(part) is None:
                    continue
                compared.append(part)
                old = json.loads(then[part][0], parse_float=Decimal)
                new = json.loads(now[part][0], parse_float=Decimal)
                deep(old, new, part, changed, added)
                if then[part][1] != now[part][1]:
                    changed.append(f"{part}: sensitive parts differ")
            for part in ("activities", "children", "signals", "updates", "end"):
                # What it sent and answered: compared value by value, each JSON text read first.
                deep(read(then.get(part)), read(now.get(part)), part, changed, added)
            verdict = "DIFFERENT" if changed else "the same"
            different += bool(changed)
            print(f"{name}: recorded at {commit}; compared {', '.join(compared) or 'nothing'} and "
                  f"what it sent: {verdict}; {len(added)} fields only today's code holds")
            for line in changed:
                print(f"    {line}")
            if added and "-v" in os.environ.get("P2_FLAGS", ""):
                print("    added: " + "; ".join(added)[:1500])
    finally:
        for tree in trees.values():
            subprocess.run(
                ["git", "-C", str(REPOSITORY), "worktree", "remove", "--force", str(tree)],
                check=False,
            )
        subprocess.run(["git", "-C", str(REPOSITORY), "worktree", "prune"], check=False)
    if different:
        print(f"RESULT: BROKEN - {different} histories rebuild another state with today's code "
              f"than with the code that recorded them, with no replay error ({unread} not read)")
    else:
        print(f"RESULT: HELD - every history read rebuilds, with today's code, each value the "
              f"code that recorded it rebuilt ({unread} could not be read by one of the two)")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        main()
