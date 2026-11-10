# Runs every in-memory test's decisions under several PYTHONHASHSEED values and compares, test by test, a digest of everything the pure deciding functions gave: states, history lines, audit records, commands, refusals.
"""`core` and `case` hold many sets (a value's sources, a person's roles). A set's order follows
the process's hash seed, so one that reached a history line, a command, an audit record or the
order of a dict would make a replay on another worker process differ from the first run. Each
seed is one pytest run in a subprocess with p2_seed_plugin.py loaded; the tests chosen are the
ones that start no Temporal server (about 4,000 tests, 84,000 decisions).
Run: uv run python reviews/2026-11/probes/p2_hash_seeds.py [--amplify] [seed ...]
(default seeds: 0 1 2 3 4). With --amplify, every decision is asked with more in each set (every
registered role stated, two more trusted sources on every value): the tests' own assertions then
fail in places, which doesn't matter here; only seed is compared with seed."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SERVERS = ("WorkflowEnvironment", "skipping_server", "dev_server", "on_temporal",
           "temporalio.testing", "subprocess")


def main() -> None:
    amplify = "--amplify" in sys.argv
    seeds = [arg for arg in sys.argv[1:] if arg != "--amplify"] or ["0", "1", "2", "3", "4"]
    files = sorted(
        str(path) for path in (ROOT / "tests").glob("test_*.py")
        if not any(word in path.read_text() for word in SERVERS)
    )
    out = Path(tempfile.mkdtemp(prefix="p2-seeds-"))
    digests: dict[str, dict[str, tuple[str, str]]] = {}
    for seed in seeds:
        target = out / f"seed-{seed}.txt"
        environment = dict(os.environ, PYTHONHASHSEED=seed, P2_SEED_OUT=str(target),
                           PYTHONPATH=str(HERE))
        if amplify:
            environment["P2_SEED_AMPLIFY"] = "1"
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p",
             "p2_seed_plugin", *files],
            cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
        )
        print(f"seed {seed}: {done.stdout.strip().splitlines()[-1]}")
        for line in target.read_text().splitlines():
            test, count, digest = line.split("\t")
            digests.setdefault(test, {})[seed] = (count, digest)
    decisions = sum(int(found[seeds[0]][0]) for found in digests.values() if seeds[0] in found)
    differing = sorted(test for test, found in digests.items() if len(set(found.values())) > 1)
    print(f"{len(files)} test files, {len(digests)} tests, {decisions} results written per seed")
    for test in differing[:40]:
        print(f"  differs: {test}: " + " ".join(f"{s}={d[1][:8]}" for s, d in digests[test].items()))
    if differing:
        print(f"RESULT: BROKEN - {len(differing)} tests' decisions differ with the hash seed")
    else:
        print(f"RESULT: HELD - under seeds {', '.join(seeds)}{' (amplified)' if amplify else ''}, every decision of every test gave "
              "the same states, lines, records, commands and refusals, in the same order")


if __name__ == "__main__":
    main()
