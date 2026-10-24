"""The `ventoux` command: `ventoux simulate STORY.json` (layer 11g2), `ventoux release FOLDER
--releases DIR --commit SHA` (layer 12a), an environment's commands (layer 12e): `ventoux
environment create|harden|check`, `ventoux activate`, `ventoux retire`, `ventoux manifest publish`,
`ventoux diff OLD NEW [--plain]` (layers 13a, 13c) and `ventoux map FOLDER` (layer 13c).

Reading files and printing happen here, never in `core` or `case`, which read no clock and do no
I/O (brief, D45). `ventoux check` comes with the Python builder (brief, D34).
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.changes import DiffRefused
from ventoux.case.definition import CaseDefinition, CaseInvalid, parse_case
from ventoux.case.diff import diff
from ventoux.case.plain import plain
from ventoux.case.reading import ReadingRefused
from ventoux.case.releases import (
    PackageRefused,
    PackageUnreadable,
    RecordRefused,
    Reworded,
    SameAs,
    Unchanged,
)
from ventoux.case.sheet import SheetRefused, case_map, never_sheet
from ventoux.case.simulate import StoryRefused, simulate
from ventoux.case.story import Story, StoryInvalid, parse_story
from ventoux.testing import CATALOG
from ventoux.tooling.environments import environment_command
from ventoux.tooling.releases import FolderStore, Run, read_package, release, said

# What `ventoux simulate` exits with.
HOLDS = 0  # what the story expects holds, or it expects nothing
FAILS = 1  # what it expects doesn't hold: the first difference is printed
CANT_READ = 2  # the story or its definition can't be read, or can't run


class Unreadable(Exception):
    """A file that can't be read as what it should be: one line per problem, each naming it."""

    def __init__(self, path: Path, problems: str) -> None:
        super().__init__("\n".join(f"{path}: {line}" for line in problems.splitlines()))


def main(argv: Sequence[str] | None = None) -> int:
    """Run `ventoux` with `argv` (the command line's own when None), and say how it ended."""
    # argparse: the standard library's command-line parser; it prints `--help` and refuses an
    # unknown command by itself.
    parser = argparse.ArgumentParser(prog="ventoux", description="Ventoux, from the command line.")
    commands = parser.add_subparsers(dest="command", required=True)
    simulating = commands.add_parser(
        "simulate", help="play a story on the in-memory engine, and check what it expects"
    )
    simulating.add_argument("story", type=Path, help="the story's JSON file")
    releasing = commands.add_parser(
        "release", help="release a package whose behaviour changed, or record its new wording"
    )
    releasing.add_argument("package", type=Path, help="the package's folder")
    releasing.add_argument("--releases", type=Path, required=True, help="where records are kept")
    releasing.add_argument("--commit", required=True, help="the commit CI releases from")
    diffing = commands.add_parser("diff", help="what changed between two versions of a package")
    diffing.add_argument("old", type=Path, help="the package's folder before")
    diffing.add_argument("new", type=Path, help="the package's folder after")
    diffing.add_argument("--plain", action="store_true", help="in plain language, as Markdown")
    mapping = commands.add_parser(
        "map", help="what a case of a package can do, and what it will never do"
    )
    mapping.add_argument("package", type=Path, help="the package's folder")
    environments(commands)
    arguments = parser.parse_args(argv)
    if arguments.command in ("environment", "activate", "retire", "manifest"):
        return environment_command(arguments)
    if arguments.command == "release":
        return release_package(arguments.package, arguments.releases, arguments.commit)
    if arguments.command == "diff":
        return diff_packages(arguments.old, arguments.new, arguments.plain)
    if arguments.command == "map":
        return map_package(arguments.package)
    return simulate_story(arguments.story)


def environments(commands: Any) -> None:
    """The commands that talk to an environment's registry on Temporal (layer 12e)."""
    environment = commands.add_parser("environment", help="create, harden or check an environment")
    actions = environment.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="create an environment's registry, once")
    create.add_argument("name", help="the environment: production")
    create.add_argument("--development", action="store_true", help="drafts open there")
    harden = actions.add_parser("harden", help="make a development environment production")
    harden.add_argument("name")
    harden.add_argument("--by", required=True, help="who does it")
    check = actions.add_parser("check", help="check every release that is active or has open cases")
    check.add_argument("name")
    activate = commands.add_parser("activate", help="make a release the one new cases open on")
    retire = commands.add_parser("retire", help="retire a release with no open cases, for good")
    for each in (activate, retire):
        each.add_argument("package", help="the package: refund")
        each.add_argument("release", type=int, help="its release number")
        each.add_argument("--environment", required=True)
        each.add_argument("--releases", type=Path, required=True, help="where records are kept")
        each.add_argument("--by", required=True, help="who does it")
    activate.add_argument("--task-queue", required=True, help="where its new cases run")
    manifest = commands.add_parser("manifest", help="publish a worker's manifest")
    manifest.add_argument("action", choices=["publish"])
    manifest.add_argument("file", type=Path, help="the manifest, as JSON")
    for each in (create, harden, check, activate, retire, manifest):
        each.add_argument("--address", default="localhost:7233", help="Temporal's frontend")
        each.add_argument("--namespace", default="default")


def simulate_story(path: Path) -> int:
    """Print the story's simulation, then whether what it expects holds."""
    try:
        story, case = read_story(path)
        simulation = simulate(story, case, CATALOG)
    except StoryRefused as refused:
        print(Unreadable(path, str(refused)), file=sys.stderr)
        return CANT_READ
    except Unreadable as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ
    print(simulation, end="")
    difference = simulation.difference()
    if difference is not None:
        print(difference)
        return FAILS
    return HOLDS


def release_package(folder: Path, releases: Path, commit: str) -> int:
    """Print what releasing `folder` did: a release, a wording revision, or nothing; or why it
    was refused (brief, D50). Paths and names only, never a value."""
    try:
        run = release(folder, FolderStore(releases), commit, CATALOG)
    except (PackageRefused, RecordRefused) as refused:
        print(Unreadable(folder, str(refused)), file=sys.stderr)
        return FAILS
    except (PackageUnreadable, OSError) as unreadable:
        print(Unreadable(folder, str(unreadable)), file=sys.stderr)
        return CANT_READ
    for issue in run.warnings:
        print(f"warning: {said(issue)}")
    print(what_it_did(run))
    return HOLDS


def diff_packages(old: Path, new: Path, in_plain: bool = False) -> int:
    """Print what changed from the package in `old` to the one in `new`, by effect (brief, D55),
    in plain language if asked (brief, D56). Exit 0 when compared, whatever was found: a looser
    change is the reviewer's to judge."""
    folder = old
    try:
        before = read_package(old)
        folder = new
        after = read_package(new)
        found = diff(before, after, CATALOG)
        said = plain(found, before, after, CATALOG) if in_plain else str(found)
    except PackageRefused as refused:
        print(Unreadable(folder, str(refused)), file=sys.stderr)
        return FAILS
    except (DiffRefused, ReadingRefused) as refused:
        print(f"{old} -> {new}: {refused}", file=sys.stderr)
        return FAILS
    except (PackageUnreadable, OSError) as unreadable:
        print(Unreadable(folder, str(unreadable)), file=sys.stderr)
        return CANT_READ
    print(said, end="")
    return HOLDS


def map_package(folder: Path) -> int:
    """Print what a case of the package in `folder` can do, then what it will never do
    (brief, D56). Exit 1 when the package or a reading is refused, 2 when it can't be read."""
    try:
        package = read_package(folder)
        said = f"{case_map(package, CATALOG)}\n{never_sheet(package, CATALOG)}"
    except (PackageRefused, ReadingRefused, SheetRefused) as refused:
        print(Unreadable(folder, str(refused)), file=sys.stderr)
        return FAILS
    except (PackageUnreadable, OSError) as unreadable:
        print(Unreadable(folder, str(unreadable)), file=sys.stderr)
        return CANT_READ
    print(said, end="")
    return HOLDS


def what_it_did(run: Run) -> str:
    """One line: `refund 2 released: digest 51aa… (method 1); behaviour changed at …`."""
    name, outcome = run.package, run.outcome
    if isinstance(outcome, Unchanged):
        return f"{name}: nothing changed since release {outcome.release}; nothing written"
    if isinstance(outcome, SameAs):
        return f"same behaviour as {name} {outcome.release}; nothing released"
    if isinstance(outcome, Reworded):
        paths = ", ".join(outcome.changed.wording)
        return f"{name} {outcome.release}, wording {outcome.wording}: {paths} changed; no release"
    digest = f"digest {run.digest.sha256[:12]} (method {run.digest.method})"
    line = f"{name} {outcome.release} released: {digest}"
    if outcome.changed.behaviour:
        line += f"; behaviour changed at {', '.join(outcome.changed.behaviour)}"
    if outcome.changed.wording:
        line += f"; wording changed at {', '.join(outcome.changed.wording)}"
    return line


def read_story(path: Path) -> tuple[Story, CaseDefinition]:
    """The story at `path`, and the definition it names, relative to the story's own file.
    Raises `Unreadable`, naming the file, for one that can't be read."""
    try:
        story = parse_story(read_json(path))
    except StoryInvalid as invalid:
        raise Unreadable(path, str(invalid)) from None
    definition = path.parent / story.definition
    try:
        case = parse_case(read_json(definition))
    except CaseInvalid as invalid:
        raise Unreadable(definition, str(invalid)) from None
    return story, case


def read_json(path: Path) -> Any:
    """The JSON in `path`, numbers read as exact decimals, never binary floats (brief, D20)."""
    try:
        return json.loads(path.read_text(), parse_float=Decimal)
    except OSError as error:
        raise Unreadable(path, f"can't be read: {error.strerror}") from None
    except json.JSONDecodeError as error:
        raise Unreadable(path, f"isn't JSON: {error.msg}, at line {error.lineno}") from None
