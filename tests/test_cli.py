"""The `ventoux` command: `ventoux simulate STORY.json` (layer 11g2).

Tests call `main` with its arguments, and run the installed command once.
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ventoux.tooling.cli import main

WITNESSES = Path(__file__).parent.parent / "examples" / "witnesses"
STORY = WITNESSES / "stories" / "timer-on-a-run.json"


def copied(tmp_path: Path, change: dict[str, object]) -> Path:
    """The timer-on-a-run story, written beside a copy of its definition, changed by `change`."""
    story = json.loads(STORY.read_text())
    (tmp_path / "timer-on-a-run.json").write_text((WITNESSES / "timer-on-a-run.json").read_text())
    (tmp_path / "stories").mkdir()
    path = tmp_path / "stories" / "story.json"
    path.write_text(json.dumps(story | change))
    return path


def test_simulate_exits_as_its_story_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 0: what the story expects holds, and the simulation is printed.
    assert main(["simulate", str(STORY)]) == 0
    printed = capsys.readouterr()
    assert printed.out.startswith("Story: A review answered within two days ends its chase\n")
    assert printed.err == ""
    # 1: it doesn't, and the first difference is printed after the simulation.
    story = json.loads(STORY.read_text())
    wrong = story["expect"] | {"end": ["status: open"]}
    assert main(["simulate", str(copied(tmp_path, {"expect": wrong}))]) == 1
    assert capsys.readouterr().out.endswith(
        "the story's expectation fails:\n"
        "  expected, at the end: status: open\n"
        "  printed, at the end: status: closed\n"
    )


def test_a_story_that_cant_be_read_exits_2_saying_where(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nowhere.json"
    assert main(["simulate", str(missing)]) == 2
    assert capsys.readouterr().err == f"{missing}: can't be read: No such file or directory\n"
    misspelt = copied(tmp_path, {"timelien": []})
    assert main(["simulate", str(misspelt)]) == 2
    assert capsys.readouterr().err == f"{misspelt}: timelien: not a field here\n"
    no_fake = tmp_path / "stories" / "no-fake.json"
    no_fake.write_text(json.dumps(json.loads(STORY.read_text()) | {"fakes": {}}))
    assert main(["simulate", str(no_fake)]) == 2
    assert capsys.readouterr().err == (
        f"{no_fake}: fakes: no fake for payments.refund@2, which pay calls: add one, so nothing "
        "real is called\n"
    )


def test_the_ventoux_command_is_installed() -> None:
    # The entry point the project declares, run as a person would run it.
    command = Path(sys.executable).parent / "ventoux"
    ran = subprocess.run(
        [str(command), "simulate", str(STORY)], capture_output=True, text=True, check=False
    )
    assert ran.returncode == 0, ran.stderr
    assert "cancelled chase_review, 2d after started review#1: review#1 is done" in ran.stdout
