"""`ventoux check`: the builder files run, each package checked as `ventoux release` checks it,
each problem at the line that made it, and the packages written only if all pass (layer 14c,
choices 29 to 33, 36). See docs/layers/14-builder.md and docs/QUICKSTART.md, section 3.
"""

from pathlib import Path

import pytest

from ventoux.tooling.cli import main

ROOT = Path(__file__).parent.parent
QUICKSTART = ROOT / "examples" / "quickstart" / "cases" / "refund.py"
CONFIGURATION = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'


def a_project(folder: Path, **files: str) -> Path:
    """A project in `folder`: its configuration, and each builder file under `cases/`."""
    (folder / "pyproject.toml").write_text(CONFIGURATION)
    (folder / "cases").mkdir()
    for name, source in files.items():
        (folder / "cases" / f"{name}.py").write_text(source)
    return folder


def test_a_builder_file_that_raises_is_refused_at_its_line_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raising = QUICKSTART.read_text() + "\nif approved > 100:\n    pass\n"
    line = raising.count("\n") - 1  # the `if`, the file's second line from the end
    claim = (ROOT / "examples" / "builder" / "claim.py").read_text()
    monkeypatch.chdir(a_project(tmp_path, refund=raising, claim=claim))
    assert main(["check"]) == 2
    said = capsys.readouterr().err
    assert f"cases/refund.py:{line}: BuildTimeDecision: approved_amount > 100 is decided" in said
    assert "Nothing was written." in said
    assert not (tmp_path / "packages").exists()


def untrusted_amount() -> str:
    """The quickstart's section 6: the amount paid is the one the customer typed."""
    source = QUICKSTART.read_text()
    field = (
        'message_amount = refund.field("customer_amount", Field.number(), '
        'title="Amount the customer asked for", source="untrusted:customer")\n'
    )
    source = source.replace("\nreview = refund.task(", f"\n{field}\nreview = refund.task(", 1)
    return source.replace('"amount": approved}', '"amount": message_amount}', 1)


def test_each_problem_is_said_at_the_line_of_the_call_that_made_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The negative test: the path and the code are validation's, the line is the builder call's.
    source = untrusted_amount()
    line = source.splitlines().index("pay = refund.activity(") + 1
    monkeypatch.chdir(a_project(tmp_path, refund=source))
    assert main(["check"]) == 1
    said = capsys.readouterr().out.splitlines()
    assert said[0].startswith(f"cases/refund.py:{line}: steps.pay.inputs.amount INPUT_POLICY: ")
    assert said[1:] == ["✗ refund is refused: 1 error.", "Nothing was written."]
    assert not (tmp_path / "packages").exists()


def test_the_quickstarts_refusal_reads_as_the_quickstart_shows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, refund=untrusted_amount()))
    assert main(["check"]) == 1
    printed = capsys.readouterr().out
    guide = (ROOT / "docs" / "QUICKSTART.md").read_text()
    shown = guide.split("## 6. When Ventoux says no")[1].split("```text\n")[1].split("```")[0]
    # The guide's line names the call as its file's 19th line; this file has the new field above.
    assert printed.replace("cases/refund.py:21:", "cases/refund.py:19:") == shown


def test_a_shape_the_reader_refuses_is_said_at_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = (
        QUICKSTART.read_text()
        .replace(
            "refund.sequence(review, pay)", "refund.sequence(review, pay)\nrefund.closes_when(paid)"
        )
        .replace(
            'refund = Case("refund", title="Customer refund")\n',
            """refund = Case("refund", title="Customer refund")
paid = Milestone("paid")
""",
        )
        .replace(
            "from ventoux import Approval, Case, Field, Outcome",
            "from ventoux import Approval, Case, Field, Outcome\nfrom ventoux.tooling.builder.entries import Milestone",
        )
    )
    line = source.splitlines().index("refund.closes_when(paid)") + 1
    monkeypatch.chdir(a_project(tmp_path, refund=source))
    assert main(["check"]) == 1
    said = capsys.readouterr().out
    assert f"cases/refund.py:{line}: closes_when REFUSED: paid is not a milestone" in said


def test_a_problem_no_call_wrote_is_said_at_the_cases_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An undeclared outcome is said on the step; a whole-case problem, here a rule-free case that
    # stays open with no close reason, on `Case(...)`'s line.
    source = QUICKSTART.read_text().replace(
        'Case("refund", title="Customer refund")',
        'Case("refund", title="Customer refund", stays_open=True)',
    )
    line = (
        source.splitlines().index(
            'refund = Case("refund", title="Customer refund", stays_open=True)'
        )
        + 1
    )
    monkeypatch.chdir(a_project(tmp_path, refund=source))
    assert main(["check"]) == 1
    said = capsys.readouterr().out
    assert (
        f"cases/refund.py:{line}: stays_open REFUSED: a case that stays open names close_reasons"
        in said
    )


def test_nothing_is_written_unless_every_package_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claim = (ROOT / "examples" / "builder" / "claim.py").read_text()
    monkeypatch.chdir(a_project(tmp_path, refund=untrusted_amount(), claim=claim))
    assert main(["check"]) == 1
    assert "✗ refund is refused" in capsys.readouterr().out
    assert not (tmp_path / "packages").exists()  # the claim passed, and wasn't written either


def test_every_package_is_written_where_git_keeps_it_as_the_builder_writes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claim = (ROOT / "examples" / "builder" / "claim.py").read_text()
    monkeypatch.chdir(a_project(tmp_path, refund=QUICKSTART.read_text(), claim=claim))
    assert main(["check"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert "✓ refund is valid (3 steps): packages/refund/" in printed
    assert "✓ claim is valid (3 steps): packages/claim/" in printed
    committed = ROOT / "examples" / "quickstart" / "packages" / "refund" / "case.json"
    assert (tmp_path / "packages" / "refund" / "case.json").read_text() == committed.read_text()
    guide = (ROOT / "docs" / "QUICKSTART.md").read_text()
    shown = guide.split("## 3. Check it")[1].split("```text\n")[1].split("```")[0]
    assert shown.strip() in printed


def test_a_folder_holds_exactly_its_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A plan no step names any more is removed, as a release refuses any other file in a package
    # (brief, D50); a folder no builder file defines is left, and said.
    monkeypatch.chdir(a_project(tmp_path, refund=QUICKSTART.read_text()))
    stale = tmp_path / "packages" / "refund" / "plans" / "refund-order.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    other = tmp_path / "packages" / "old" / "case.json"
    other.parent.mkdir(parents=True)
    other.write_text("{}")
    assert main(["check"]) == 0
    assert not stale.exists()
    assert other.read_text() == "{}"
    assert "packages/old: no builder file defines this package; left as it is" in (
        capsys.readouterr().out
    )


def test_two_cases_of_one_name_are_refused_naming_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(
        a_project(tmp_path, refund=QUICKSTART.read_text(), again=QUICKSTART.read_text())
    )
    assert main(["check"]) == 2
    said = capsys.readouterr().err
    assert "cases/refund.py and cases/again.py both define the case refund" in said
    assert "Nothing was written." in said


def test_a_plans_shape_the_reader_refuses_is_said_at_the_plans_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A plan's refusal names paths inside the plan; they are said under `plans.<reference>`, at
    # the call that wrote the state.
    source = (
        (ROOT / "examples" / "cases" / "refund.py")
        .read_text()
        .replace(
            'refund_order.final("failed", "failed")',
            'refund_order.final("failed", "maybe")  # type: ignore[arg-type]',
        )
    )
    line = (
        source.splitlines().index('refund_order.final("failed", "maybe")  # type: ignore[arg-type]')
        + 1
    )
    monkeypatch.chdir(a_project(tmp_path, refund=source))
    assert main(["check"]) == 1
    said = capsys.readouterr().out
    assert (
        f"cases/refund.py:{line}: plans.refund-order@1.states.failed.final REFUSED: a final "
        "state is succeeded or failed"
    ) in said
