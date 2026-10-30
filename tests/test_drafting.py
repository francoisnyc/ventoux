"""`ventoux draft` (layer 15c): the loop from the command line, writing into the drafts folder
only, never into a package; exit 0 drafted, 1 abandoned, 2 when it couldn't ask or read.

See docs/layers/15-authoring.md (15c) and brief D63.
"""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from test_authoring import (
    GOAL,
    INPUT_POLICY,
    SCHEMA,
    TO_THE_EMAIL,
    TO_THE_NOTE,
    TOO_DEEP,
    TOO_LONG,
    WRITER_DECIDES,
    branching_on_the_remark,
    refund_case,
    refund_plan,
    the_package,
    with_a_remark,
    written,
)

from ventoux.authoring.loop import FIXED, author
from ventoux.authoring.provider import Recorded, Recording
from ventoux.testing import CATALOG
from ventoux.tooling.cli import main
from ventoux.tooling.releases import read_package

PLAN = "refund-order@1"


def project(root: Path) -> Path:
    """A project at `root`: its configuration, naming the catalog and the drafts folder, and the
    refund package, whose case gives its plan the customer's note and email."""
    (root / "pyproject.toml").write_text(
        '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\ndrafts = "drafts"\n'
    )
    package = root / "packages" / "refund"
    (package / "plans").mkdir(parents=True)
    (package / "case.json").write_text(written(refund_case()))
    (package / "plans" / "refund-order.json").write_text(written(refund_plan()))
    return package


def recorded(root: Path, *answers: str) -> Path:
    """A recording of the loop asking for the refund plan and the model answering `answers`:
    the requests are the loop's own, so the command is shown to send exactly those."""
    recording = Recording(Recorded.answering(*answers))
    asyncio.run(author(GOAL, the_package(), PLAN, CATALOG, SCHEMA, recording, 3))
    path = root / "session.json"
    recording.save(path)
    return path


def draft(root: Path, *more: str) -> list[str]:
    return ["draft", str(root / "packages" / "refund"), "--plan", PLAN, "--goal", GOAL, *more]


def package_files(package: Path) -> dict[str, bytes]:
    return {str(path): path.read_bytes() for path in sorted(package.rglob("*")) if path.is_file()}


def record(root: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((root / "drafts" / f"{PLAN}.record.json").read_text())
    return loaded


def test_a_draft_never_repaired_is_abandoned_its_record_written_and_no_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The curriculum's negative test from the command line: exit 1, refused, as release's 1.
    package = project(tmp_path)
    session = recorded(tmp_path, TO_THE_NOTE, TO_THE_NOTE, TO_THE_NOTE)
    before = package_files(package)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 1
    assert not (tmp_path / "drafts" / f"{PLAN}.json").exists()
    kept = record(tmp_path)
    assert kept["verdict"] == "abandoned"
    assert kept["reason"] == "abandoned after 3 rounds: the last draft still has 1 problem"
    assert kept["asked_by"] == "omar"
    assert kept["draft_sha256"] is None  # nothing was written
    assert kept["rounds"] == [{"answer": TO_THE_NOTE, "problems": [INPUT_POLICY]}] * 3
    assert package_files(package) == before  # never written into the package
    said = capsys.readouterr()
    assert said.out == (
        f"{PLAN} abandoned after 3 rounds: the last draft still has 1 problem\n"
        f"its record: drafts/{PLAN}.record.json\n"
    )


def test_answers_python_cant_read_are_fed_back_and_abandoned_with_their_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Anything but a draft of the plan is a problem fed back, and the record is written once the
    # model was asked, whatever it answered (brief, D63).
    project(tmp_path)
    session = recorded(tmp_path, TOO_DEEP, TOO_LONG, TOO_DEEP)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 1
    kept = record(tmp_path)
    assert kept["verdict"] == "abandoned"
    problems = [each["problems"] for each in kept["rounds"]]  # type: ignore[attr-defined]
    deep = "answer: NOT_ONE_OBJECT: the answer is not one JSON object: nested too deeply to read"
    long = "answer: NOT_ONE_OBJECT: the answer is not one JSON object: a number too long to read"
    assert problems == [[deep], [long], [deep]]
    assert "Traceback" not in capsys.readouterr().err


def test_a_draft_repaired_is_written_with_its_record_into_the_drafts_folder_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    package = project(tmp_path)
    session = recorded(tmp_path, TO_THE_NOTE, TO_THE_EMAIL)
    before = package_files(package)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 0
    assert (tmp_path / "drafts" / f"{PLAN}.json").read_text() == TO_THE_EMAIL + "\n"
    kept = record(tmp_path)
    assert kept == {
        "plan": PLAN,
        "package": "refund",
        "goal": GOAL,
        "asked_by": "omar",
        "provider": "recorded",
        "rounds": [
            {"answer": TO_THE_NOTE, "problems": [INPUT_POLICY]},
            {"answer": TO_THE_EMAIL, "problems": []},
        ],
        "verdict": "drafted",
        "reason": None,
        "warnings": kept["warnings"],
        # What was written, so an edit after drafting is told (brief, D64).
        "draft_sha256": hashlib.sha256(
            (tmp_path / "drafts" / f"{PLAN}.json").read_bytes()
        ).hexdigest(),
    }
    assert package_files(package) == before
    assert capsys.readouterr().out == (
        f"{PLAN} drafted in 2 rounds: drafts/{PLAN}.json\n"
        f"its record: drafts/{PLAN}.record.json\n"
        "keep it in a pull request: it runs nowhere until it is reviewed, released and activated\n"
    )


def test_a_provider_that_gives_no_answer_exits_2_with_its_record_and_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path)
    elsewhere = tmp_path / "elsewhere.json"
    Recording(Recorded.answering("{}")).save(elsewhere)  # holds no request at all
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(elsewhere))) == 2
    said = capsys.readouterr()
    assert "Traceback" not in said.err
    assert said.err == (
        f"{PLAN}: the authoring model gave no answer: request 1 was never recorded: the "
        "recording holds 0\n"
        f"its record: drafts/{PLAN}.record.json\n"
    )
    assert record(tmp_path)["verdict"] == "no answer"
    assert not (tmp_path / "drafts" / f"{PLAN}.json").exists()


def test_a_drafts_warnings_are_kept_in_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A warning refuses nothing, and the person reviewing the draft reads it in the record
    # (brief, D63).
    package = project(tmp_path)
    (package / "case.json").write_text(written(with_a_remark()))
    plan = refund_plan()
    plan["fields"]["remark"] = {"type": "string"}
    (package / "plans" / "refund-order.json").write_text(written(plan))
    recording = Recording(Recorded.answering(written(branching_on_the_remark())))
    asyncio.run(author(GOAL, read_package(package), PLAN, CATALOG, SCHEMA, recording, 3))
    session = tmp_path / "session.json"
    recording.save(session)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 0
    kept = record(tmp_path)
    assert kept["verdict"] == "drafted"
    assert kept["warnings"] == [WRITER_DECIDES]


def test_a_draft_already_there_is_refused_and_nothing_is_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path)
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / f"{PLAN}.json").write_text("someone's draft, in review\n")
    session = recorded(tmp_path, TO_THE_EMAIL)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 2
    assert capsys.readouterr().err == (
        f"drafts/{PLAN}.json is there already: move it, or keep it in a pull request\n"
    )
    assert (tmp_path / "drafts" / f"{PLAN}.json").read_text() == "someone's draft, in review\n"
    assert not (tmp_path / "drafts" / f"{PLAN}.record.json").exists()


@pytest.mark.parametrize(
    ("more", "said"),
    [
        (["--rounds", "6"], "--rounds is 6: a loop takes 1 to 5 rounds"),
        (["--by", "Omar"], "Omar"),  # an identifier written one way (brief, D22)
    ],
)
def test_a_command_that_cant_start_exits_2_writing_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    more: list[str],
    said: str,
) -> None:
    project(tmp_path)
    session = recorded(tmp_path, TO_THE_EMAIL)
    monkeypatch.chdir(tmp_path)
    by = [] if "--by" in more else ["--by", "omar"]
    assert main(draft(tmp_path, *by, *more, "--recording", str(session))) == 2
    assert said in capsys.readouterr().err
    assert not (tmp_path / "drafts").exists()


def test_no_drafts_folder_named_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'
    )
    session = recorded(tmp_path, TO_THE_EMAIL)
    monkeypatch.chdir(tmp_path)
    assert main(draft(tmp_path, "--by", "omar", "--recording", str(session))) == 2
    assert capsys.readouterr().err == (
        'no drafts folder is named: name it in pyproject.toml, [tool.ventoux] drafts = "drafts"\n'
    )


GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


@pytest.mark.parametrize(
    "lines",
    [
        FIXED,
        f"{PLAN} abandoned after 3 rounds: the last draft still has 1 problem",
        (
            f"{PLAN} drafted in 2 rounds: drafts/{PLAN}.json\n"
            f"its record: drafts/{PLAN}.record.json\n"
            "keep it in a pull request: it runs nowhere until it is reviewed, released and "
            "activated"
        ),
    ],
)
def test_the_guide_quotes_what_the_loop_and_the_command_say(lines: str) -> None:
    # Each is asserted from a run in the tests above; the guide quotes it word for word.
    assert f"```text\n{lines}\n```" in GUIDE.read_text(encoding="utf-8")
