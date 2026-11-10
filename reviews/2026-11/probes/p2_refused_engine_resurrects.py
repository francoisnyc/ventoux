# Shows that a migration a case refused because its code didn't know the target engine version is ACCEPTED when a later worker replays the same history: the refusal is decided from the code's list of versions, not from the history.
"""The scenario is the one the refusal exists for (brief, D53: "the version the proposer's code was
built with, refused if the case's code doesn't know it"): a client upgraded before the workers
proposes moving a case to engine 3; the case's worker, at the merge before engine 3 existed
(dc2407e, `KNOWN = (2, 1)`), refuses it and records the refusal. Then the workers are upgraded.

Step 1 records two histories with the code at dc2407e, in a temporary git worktree, on the tests'
time-skipping server: A ends after the refusal; B goes on with an approval sent to
`case.change#1`, an entry that didn't exist, refused too. Step 2 replays A and B with the code
that recorded them and with today's, and prints the state each rebuilds.
Reaches past the supported names for the old tree's test harness (`on_temporal`, `reported`), its
example releases, and p2_harness.py. Nothing in the project's files changes."""

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
RECORDED_AT = "dc2407e"


def record(out: Path) -> None:
    """With the old tree's code and tests on the path: run the scenario, keep both histories."""
    from temporalio.client import Client
    from test_migrations import PEOPLE, REFUND_1, REFUND_2
    from test_temporal_case import LARGE, QUEUE, on_temporal, reported

    from ventoux.case.engine import KNOWN
    from ventoux.temporal.cases import answer, propose_migration, start_case
    from ventoux.testing import DevelopmentCases, development_converter

    assert KNOWN == (2, 1), KNOWN  # the code that records knows no engine 3
    converter = development_converter()

    def refusals(now: Any) -> int:
        return sum(line.startswith("refused") for line in now.history)

    async def scenario(client: Client) -> None:
        case = await start_case(client, DevelopmentCases, REFUND_1, LARGE, "refund-1", QUEUE)
        form = {"approved_amount": Decimal(250)}
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], form)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        # A client already built with engine 3 proposes the move (brief, D53).
        await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"], engine=3)
        said = await reported(case, lambda now: refusals(now) == 1)
        (out / "A.json").write_text((await case.fetch_history()).to_json())
        (out / "A.report.json").write_text(json.dumps([said.history, said.waiting_at]))
        # Someone answers the entry the proposal would have opened: there is none.
        await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
        said = await reported(case, lambda now: refusals(now) == 2)
        (out / "B.json").write_text((await case.fetch_history()).to_json())
        (out / "B.report.json").write_text(json.dumps([said.history, said.waiting_at]))

    on_temporal(scenario, converter=converter)
    (out / "keys.json").write_text(Path(converter.payload_codec.keys.path).read_text())  # type: ignore[union-attr]


def replay(out: Path, name: str) -> None:
    """Replay history `name` with whatever code PYTHONPATH names; print what it rebuilds."""
    from p2_harness import replayed, run
    from temporalio.client import WorkflowHistory

    import ventoux.case.engine as engine
    from ventoux.temporal.converter import data_converter
    from ventoux.testing import DevelopmentCases
    from ventoux.tooling.keys import FileKeys

    keys = Path(tempfile.mkdtemp(prefix="p2-k-")) / "keys.json"
    keys.write_text((out / "keys.json").read_text())
    history = WorkflowHistory.from_json("refund-1", (out / f"{name}.json").read_text())
    seen = run(replayed(history, [DevelopmentCases], data_converter(FileKeys(keys))))
    state = json.loads(seen["state"][0]) if seen.get("state") else {}
    print("P2RESULT " + json.dumps({
        "known": list(engine.KNOWN),
        "failure": seen["failure"],
        "waiting_at": state.get("waiting_at"),
        "release": state.get("release"),
        "engine": state.get("engine"),
        "lines": [line for line in state.get("history", []) if "refund 2" in line or "case.change" in line],
        "activities": [each["type"] for each in seen["activities"]],
    }))


def in_tree(tree: Path, *arguments: str) -> dict[str, Any]:
    paths = [tree / "src", HERE, tree / "tests", tree / "examples" / "quickstart"]
    environment = dict(os.environ, P2_ROOT=str(tree), PYTHONPATH=":".join(map(str, paths)))
    done = subprocess.run(
        [sys.executable, str(HERE / "p2_refused_engine_resurrects.py"), *arguments],
        env=environment, capture_output=True, text=True, timeout=400, check=False, cwd=tree,
    )
    for line in done.stdout.splitlines():
        if line.startswith("P2RESULT "):
            return json.loads(line.removeprefix("P2RESULT "))  # type: ignore[no-any-return]
    if done.returncode:
        print(done.stderr[-2500:])
    return {}


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="p2-engine-"))
    tree, out = work / "tree", work / "out"
    out.mkdir()
    subprocess.run(
        ["git", "-C", str(REPOSITORY), "worktree", "add", "--detach", "-q", str(tree), RECORDED_AT],
        check=True,
    )
    broken = False
    try:
        in_tree(tree, "--record", str(out))
        for name, what in (("A", "ends after the refused proposal"),
                           ("B", "goes on: lee's approval of case.change#1, refused too")):
            lines, waiting = json.loads((out / f"{name}.report.json").read_text())
            print(f"History {name} ({what}), as the case reported it when recorded at {RECORDED_AT}:")
            for line in lines:
                if line.startswith("refused"):
                    print(f"    {line}")
            print(f"    waiting at: {waiting}")
            then = in_tree(tree, "--replay", str(out), name)
            now = in_tree(REPOSITORY, "--replay", str(out), name)
            for label, got in ((f"replayed by the code at {RECORDED_AT}", then),
                               ("replayed by today's code", now)):
                print(f"  {label} (knows engines {got.get('known')}):")
                print(f"    replay error: {(got.get('failure') or 'none')[:230]}")
                print(f"    waiting at: {got.get('waiting_at')}; release {got.get('release')}, "
                      f"engine {got.get('engine')}; activities asked: {got.get('activities')}")
                for line in got.get("lines", []):
                    print(f"    {line[:230]}")
            broken = broken or then.get("waiting_at") != now.get("waiting_at") or bool(
                now.get("failure")) != bool(then.get("failure"))
    finally:
        subprocess.run(
            ["git", "-C", str(REPOSITORY), "worktree", "remove", "--force", str(tree)], check=False
        )
        subprocess.run(["git", "-C", str(REPOSITORY), "worktree", "prune"], check=False)
    if broken:
        print("RESULT: BROKEN - a migration the case refused and recorded as refused is taken "
              "when today's code replays the history: the recorded path is decided differently, "
              "with no engine version or patch behind the change")
    else:
        print("RESULT: HELD - today's code rebuilds the refusal as it was recorded")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--record":
        record(Path(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == "--replay":
        replay(Path(sys.argv[2]), sys.argv[3])
    else:
        main()
