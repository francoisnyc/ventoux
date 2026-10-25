"""The deployment's catalog: the platform team's code, named in configuration, never guessed
(layer 14c, choices 34 to 36). See docs/layers/14-builder.md.
"""

import json
import shutil
from pathlib import Path

import pytest

from ventoux.tooling.cli import main

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "examples" / "packages" / "refund"


def a_project(folder: Path, configuration: str | None) -> Path:
    """A project in `folder`: the refund package, and a `pyproject.toml` holding `configuration`
    if one is given."""
    shutil.copytree(PACKAGE, folder / "packages" / "refund")
    if configuration is not None:
        (folder / "pyproject.toml").write_text(configuration)
    return folder


def test_no_catalog_named_is_refused_never_read_as_the_development_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, "[project]\nname = 'refunds'\n"))
    assert main(["map", "packages/refund"]) == 2
    said = capsys.readouterr().err
    assert "no catalog is named" in said
    assert '[tool.ventoux] catalog = "module:NAME"' in said
    assert "--catalog" in said


def test_a_catalog_named_in_the_configuration_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuration = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'
    monkeypatch.chdir(a_project(tmp_path, configuration))
    assert main(["map", "packages/refund"]) == 0
    assert "refund" in capsys.readouterr().out


def test_the_flag_names_the_catalog_and_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuration = '[tool.ventoux]\ncatalog = "nowhere.at_all:CATALOG"\n'
    monkeypatch.chdir(a_project(tmp_path, configuration))
    assert main(["map", "packages/refund", "--catalog", "ventoux.testing:CATALOG"]) == 0


def test_a_name_that_is_no_catalog_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, None))
    assert main(["map", "packages/refund", "--catalog", "ventoux.testing:START"]) == 2
    assert "ventoux.testing:START is not a Catalog" in capsys.readouterr().err
    assert main(["map", "packages/refund", "--catalog", "nowhere.at_all:CATALOG"]) == 2
    assert "nowhere.at_all can't be imported" in capsys.readouterr().err
    assert main(["map", "packages/refund", "--catalog", "ventoux.testing"]) == 2
    assert 'a catalog is named "module:NAME"' in capsys.readouterr().err


def test_a_configuration_that_isnt_toml_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, "[tool.ventoux\n"))
    assert main(["map", "packages/refund"]) == 2
    assert "pyproject.toml isn't TOML" in capsys.readouterr().err


TEAM_CATALOG = """
from ventoux.core.catalog import Catalog
from ventoux.testing import payments_refund

# A team's own catalog: its refund contract, under its own name, which the development catalog
# doesn't hold.
CATALOG = Catalog()
CATALOG.register_system("orders")
CATALOG.register_role("support", edits=True)
CATALOG.register_role("support-lead", approves="high", edits=True)
CATALOG.register(payments_refund.model_copy(update={"name": "acme.refund"}))
"""


def a_team_project(folder: Path) -> Path:
    """A project naming its own catalog, `team_catalog:CATALOG`, a module of its own, and a story
    of the quickstart's refund paying through the team's `acme.refund@2`."""
    (folder / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "team_catalog:CATALOG"\n')
    (folder / "team_catalog.py").write_text(TEAM_CATALOG)
    refund = json.loads((ROOT / "examples" / "refund" / "refund.json").read_text())
    refund["steps"]["pay"]["activity"] = "acme.refund@2"
    (folder / "refund.json").write_text(json.dumps(refund))
    story = {
        "title": "A small refund, paid through the team's own contract",
        "definition": "refund.json",
        "file": {"order_id": "ord-1", "amount": 40},
        "people": {"ana": ["support"]},
        "fakes": {"acme.refund@2": {"gives": {"refund_id": "refund-1"}}},
        "timeline": [
            {
                "at": "day 0 09:00",
                "answer": {
                    "step": "review",
                    "outcome": "approve",
                    "by": "ana",
                    "form": {"approved_amount": 40},
                },
            }
        ],
    }
    (folder / "story.json").write_text(json.dumps(story))
    return folder


def test_a_story_simulates_against_the_teams_own_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The catalog gives contracts and roles; only the story's fakes run, so nothing real is
    # reached (brief, D45) (layer 14c, choice 38).
    monkeypatch.chdir(a_team_project(tmp_path))
    assert main(["simulate", "story.json"]) == 0
    printed = capsys.readouterr().out
    assert "scheduled pay#1: acme.refund@2" in printed
    assert "is not in the catalog" not in printed


def test_the_same_story_against_the_development_catalog_fails_its_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The development catalog holds no `acme.refund@2`: the step fails, as a case's would, and
    # waits for a person. Which catalog a story runs against changes what it shows.
    monkeypatch.chdir(a_team_project(tmp_path))
    assert main(["simulate", "story.json", "--catalog", "ventoux.testing:CATALOG"]) == 0
    assert "pay#1 failed: acme.refund@2 is not in the catalog" in capsys.readouterr().out


def test_an_unknown_setting_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A misspelled `packages` would otherwise write to the default folder, unnoticed (from the
    # tutor review of #58).
    configuration = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\npackage = "out"\n'
    monkeypatch.chdir(a_project(tmp_path, configuration))
    assert main(["map", "packages/refund"]) == 2
    assert "[tool.ventoux] has no setting package" in capsys.readouterr().err


# --- Where a deployment keeps its release records (layer 14d, choice 46) ----------------------


def test_release_and_notes_take_the_configured_releases_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuration = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\nreleases = "records"\n'
    monkeypatch.chdir(a_project(tmp_path, configuration))
    assert main(["release", "packages/refund", "--commit", "abc1234"]) == 0
    assert (tmp_path / "records" / "refund" / "1.json").is_file()
    assert main(["notes", "refund", "1"]) == 0
    assert "refund" in capsys.readouterr().out


def test_no_releases_folder_named_is_refused_never_a_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'))
    assert main(["release", "packages/refund", "--commit", "abc1234"]) == 2
    said = capsys.readouterr().err
    assert "no releases folder is named" in said
    assert '[tool.ventoux] releases = "releases"' in said
    assert "--releases" in said
    assert not (tmp_path / "releases").exists()
    assert main(["release", "packages/refund", "--commit", "abc1234", "--releases", "r"]) == 0
