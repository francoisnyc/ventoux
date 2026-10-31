"""The CI workflow's jobs each end within a bound (fix-overrun-report, choice 1).

A test whose task never ends can't be stopped from inside: the run never exits (the note, "The
cause"). GitHub's default would let it run 360 minutes. So every job says how long it may take.
Read as text, as tests/test_summary.py reads the workflow: no YAML parser for one file.
"""

from pathlib import Path

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
# The bound: four times the full suite's 5 minutes.
MINUTES = 20


def jobs(text: str) -> dict[str, list[str]]:
    """Each job under `jobs:`, by name, with its own lines: a job is a line indented two spaces
    and ending in `:`; its lines are those after it, up to the next job."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.split("\n")[text.split("\n").index("jobs:") + 1 :]:
        is_job = line.startswith("  ") and not line.startswith("   ") and line.endswith(":")
        if is_job and not line.lstrip().startswith("#"):
            current = found.setdefault(line.strip().rstrip(":"), [])
        elif current is not None:
            current.append(line)
    return found


def test_every_job_ends_within_twenty_minutes() -> None:
    found = jobs(WORKFLOW.read_text())
    assert sorted(found) == ["changes", "check"]  # a job added is bounded too: it shows here
    for name, lines in found.items():
        assert f"    timeout-minutes: {MINUTES}" in lines, (
            f"the CI job {name} has no `timeout-minutes: {MINUTES}`: a run that hangs would go on "
            "for GitHub's 360 minutes. Add it under the job's `runs-on`."
        )


def test_a_job_without_a_bound_is_found() -> None:
    # The reader itself, on a workflow with one job bounded and one not.
    text = "on: push\njobs:\n  a:\n    runs-on: x\n    timeout-minutes: 20\n  b:\n    runs-on: x\n"
    found = jobs(text)
    assert "    timeout-minutes: 20" in found["a"]
    assert "    timeout-minutes: 20" not in found["b"]
