"""The `ventoux` command: `ventoux simulate STORY.json` (layer 11g2), `ventoux release FOLDER
--releases DIR --commit SHA` (layer 12a), an environment's commands (layer 12e): `ventoux
environment create|harden|check`, `ventoux activate`, `ventoux retire`, `ventoux manifest publish`,
`ventoux diff OLD NEW [--plain]` (layers 13a, 13c), `ventoux map FOLDER` (layer 13c), and
`ventoux notes PACKAGE RELEASE --releases DIR`, `ventoux promises` and `ventoux hashes --lock
FILE [--before PROMISES]` (layer 13d), and `ventoux summary`, CI's job summary (layer 13e).

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
from ventoux.case.diff import Diff, diff
from ventoux.case.notes import NotesRefused, as_diff, told
from ventoux.case.plain import plain
from ventoux.case.reading import ReadingRefused
from ventoux.case.releases import (
    PackageRefused,
    PackageUnreadable,
    RecordRefused,
    Reworded,
    SameAs,
    Unchanged,
    stored,
)
from ventoux.case.sheet import SheetRefused, case_map, never_sheet
from ventoux.case.simulate import StoryRefused, simulate
from ventoux.case.story import Story, StoryInvalid, parse_story
from ventoux.core.catalog import Catalog
from ventoux.core.hash_check import check_hashes
from ventoux.core.promise import promise_of
from ventoux.tooling.advising import advise_command
from ventoux.tooling.check import (
    Checked,
    CheckRefused,
    built,
    by_hand_checked,
    check,
    differences,
    shown,
    write,
)
from ventoux.tooling.deployment import (
    Configuration,
    Unconfigured,
    configuration,
    deployment_catalog,
    read,
)
from ventoux.tooling.environments import environment_command
from ventoux.tooling.releases import FolderStore, Run, read_package, release, said
from ventoux.tooling.schema import write_schemas
from ventoux.tooling.summary import LIMIT, cant_be_read, for_summary_file, summarize

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
    checking = commands.add_parser(
        "check",
        help="run the builder files, check each package, and write them if every one passes",
    )
    checking.add_argument(
        "files", type=Path, nargs="*", help="builder files, your own code (else the cases folder)"
    )
    checking.add_argument(
        "--unchanged",
        action="store_true",
        help="write nothing: fail if any package differs from its committed files (for CI)",
    )
    publishing = commands.add_parser(
        "schema", help="write the JSON Schema of a case and of a plan, from the engine's models"
    )
    publishing.add_argument(
        "--out", type=Path, default=Path("schema"), help="the folder to write into (schema/)"
    )
    publishing.add_argument(
        "--unchanged",
        action="store_true",
        help="write nothing: fail if a committed schema differs from the models (for CI)",
    )
    simulating = commands.add_parser(
        "simulate", help="play a story on the in-memory engine, and check what it expects"
    )
    simulating.add_argument("story", type=Path, help="the story's JSON file")
    releasing = commands.add_parser(
        "release", help="release a package whose behaviour changed, or record its new wording"
    )
    releasing.add_argument("package", type=Path, help="the package's folder")
    releasing.add_argument(
        "--releases", type=Path, help="where records are kept (else pyproject.toml's releases)"
    )
    releasing.add_argument("--commit", required=True, help="the commit CI releases from")
    diffing = commands.add_parser("diff", help="what changed between two versions of a package")
    diffing.add_argument("old", type=Path, help="the package's folder before")
    diffing.add_argument("new", type=Path, help="the package's folder after")
    diffing.add_argument("--plain", action="store_true", help="in plain language, as Markdown")
    mapping = commands.add_parser(
        "map", help="what a case of a package can do, and what it will never do"
    )
    mapping.add_argument("package", type=Path, help="the package's folder")
    noting = commands.add_parser("notes", help="a release's notes, as its record keeps them")
    noting.add_argument("package", help="the package: refund")
    noting.add_argument("release", type=int, help="its release number")
    noting.add_argument("--wording", type=int, default=1, help="one of its wording revisions")
    noting.add_argument(
        "--releases", type=Path, help="where records are kept (else pyproject.toml's releases)"
    )
    noting.add_argument("--plain", action="store_true", help="in plain language, as Markdown")
    promising = commands.add_parser(
        "promises", help="each contract's promise, as the contract hash reads it"
    )
    hashing = commands.add_parser(
        "hashes", help="check each contract against contracts.lock.json, saying what changed"
    )
    hashing.add_argument("--lock", type=Path, required=True, help="contracts.lock.json")
    hashing.add_argument(
        "--before", type=Path, help="the base commit's promises, from its `ventoux promises`"
    )
    summing = commands.add_parser(
        "summary", help="what merging a pull request changes, for CI's job summary"
    )
    summing.add_argument("--base", type=Path, required=True, help="the base commit's checkout")
    summing.add_argument("--head", type=Path, required=True, help="the merge commit's checkout")
    summing.add_argument(
        "--packages", action="append", required=True, help="a folder of packages, in both"
    )
    summing.add_argument("--lock", type=Path, required=True, help="contracts.lock.json")
    summing.add_argument(
        "--base-lock", type=Path, required=True, help="the base checkout's contracts.lock.json"
    )
    summing.add_argument(
        "--before", type=Path, required=True, help="the base commit's `ventoux promises`"
    )
    summing.add_argument("--summary-file", type=Path, required=True, help="$GITHUB_STEP_SUMMARY")
    summing.add_argument("--base-commit", help="the base's commit, to name it")
    summing.add_argument("--head-commit", help="the merge commit, to name it")
    summing.add_argument("--limit", type=int, default=LIMIT, help="bytes the summary may hold")
    for taking in (
        checking,
        simulating,
        releasing,
        diffing,
        mapping,
        noting,
        promising,
        hashing,
        summing,
    ):
        taking.add_argument(
            "--catalog", help="the deployment's catalog, module:NAME (else pyproject.toml's)"
        )
    environments(commands)
    advising = commands.add_parser(
        "advise", help="what the step advisor suggests to a person on a running case"
    )
    advising.add_argument("case", help="the case's workflow ID")
    advising.add_argument("--by", required=True, help="the person it is asked for")
    advising.add_argument(
        "--role", action="append", default=[], help="a role they hold (once per role)"
    )
    advising.add_argument("--model", help="the model to ask (else pyproject.toml's model)")
    advising.add_argument("--recording", type=Path, help="replay a recording instead of a model")
    advising.add_argument("--at", type=int, help="the time, in seconds since the epoch (now)")
    advising.add_argument("--address", default="localhost:7233", help="Temporal's frontend")
    advising.add_argument("--namespace", default="default")
    arguments = parser.parse_args(argv)
    if arguments.command in ("environment", "activate", "retire", "manifest"):
        return environment_command(arguments)
    if arguments.command == "advise":
        try:
            found = configuration(Path.cwd())
        except Unconfigured as refused:
            print(refused, file=sys.stderr)
            return CANT_READ
        return advise_command(arguments, found)  # needs no catalog: the case's worker has it
    if arguments.command == "schema":
        return write_schemas(arguments.out, arguments.unchanged)  # needs no catalog: shape only
    # Every other command reads contracts or roles: the deployment's catalog, named in
    # configuration, never guessed (brief, D59).
    try:
        found = configuration(Path.cwd())
        catalog = deployment_catalog(arguments.catalog, found)
    except Unconfigured as refused:
        print(refused, file=sys.stderr)
        return CANT_READ
    if arguments.command == "check":
        return check_files(arguments.files, found, catalog, arguments.unchanged)
    if arguments.command in ("release", "notes"):
        # Where the deployment keeps its records: the flag, or the configuration; neither is
        # refused, never a default folder (brief, D59).
        try:
            releases = releases_folder(arguments.releases, found)
        except Unconfigured as refused:
            print(refused, file=sys.stderr)
            return CANT_READ
    if arguments.command == "release":
        return release_package(arguments.package, releases, arguments.commit, catalog)
    if arguments.command == "diff":
        return diff_packages(arguments.old, arguments.new, catalog, arguments.plain)
    if arguments.command == "map":
        return map_package(arguments.package, catalog)
    if arguments.command == "notes":
        return print_notes(
            arguments.package,
            arguments.release,
            arguments.wording,
            releases,
            arguments.plain,
            catalog,
        )
    if arguments.command == "summary":
        head_catalog = arguments.catalog if arguments.catalog is not None else found.catalog
        return summarize_merge(arguments, catalog, head_catalog)
    if arguments.command == "promises":
        return print_promises(catalog)
    if arguments.command == "hashes":
        return check_lockfile(arguments.lock, arguments.before, catalog)
    return simulate_story(arguments.story, catalog)


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


def releases_folder(flag: Path | None, found: Configuration) -> Path:
    """The folder release records are kept in: `--releases`, or the configuration's `releases`,
    relative to the project's root. The tool reads and writes that folder only; keeping it is the
    deployment's (brief, D59)."""
    if flag is not None:
        return flag
    if found.releases is None:
        raise Unconfigured(
            "no releases folder is named: name where the deployment keeps its records in "
            'pyproject.toml, [tool.ventoux] releases = "releases", or with --releases DIR'
        )
    root = found.root if found.root is not None else Path.cwd()
    return root / found.releases


def check_files(
    files: Sequence[Path], found: Configuration, catalog: Catalog, unchanged: bool = False
) -> int:
    """Run the builder files, check every package, and write them all, or nothing (brief, D59).
    With `unchanged`, write nothing: compare each package with its committed files instead, and
    fail on any difference (brief, D1)."""
    root = found.root if found.root is not None else Path.cwd()
    paths = [path.resolve() for path in files] or sorted((root / found.cases).glob("*.py"))
    try:
        cases = built(paths, root)
        for case in cases:
            if case.name in found.by_hand:
                raise CheckRefused(
                    f"{case.name} is listed in by_hand, and "
                    f"{shown(case.where[''].rpartition(':')[0])} defines it: one or the other"
                )
        checked = [check(case, catalog) for case in cases]
        packages = root / found.packages
        for name in found.by_hand:
            # A misspelled entry would hide a stale folder (from the tutor review of #61).
            if not (packages / name).is_dir():
                raise CheckRefused(
                    f"by_hand lists {name}, and {shown(packages / name)}/ doesn't exist: "
                    "a misspelling, or a folder not committed"
                )
    except CheckRefused as refused:
        print(f"{refused}\nNothing was written.", file=sys.stderr)
        return CANT_READ
    # A folder no builder case defines: written by hand, if listed; else it may be stale output.
    others = [
        folder
        for folder in (sorted(packages.glob("*/")) if packages.is_dir() else [])
        if folder.is_dir() and folder.name not in {each.name for each in checked}
    ]
    if unchanged:
        checked += [by_hand_checked(f, catalog) for f in others if f.name in found.by_hand]
    for each in checked:
        for problem in each.problems:
            print(problem)
    not_valid = [each for each in checked if each.refused]
    if not_valid:
        for each in not_valid:
            errors = sum(not problem.warning for problem in each.problems)
            print(f"✗ {each.name} is refused: {errors} error{'s' if errors > 1 else ''}.")
        print("Nothing was written.")
        return FAILS
    if unchanged:
        stale = [f for f in others if f.name not in found.by_hand]
        return compared(checked, packages, stale)
    write(checked, packages)
    for each in checked:
        print(f"✓ {each.name} is valid ({each.steps} steps): {shown(packages / each.name)}/")
    for folder in others:
        if folder.name in found.by_hand:
            print(f"{shown(folder)}: written by hand; left as it is")
        else:
            print(f"{shown(folder)}: {STALE}; left as it is")
    return HOLDS


# A package folder neither a builder case defines nor `by_hand` lists (brief, D58).
STALE = (
    "no builder file defines it and by_hand doesn't list it: stale output of a removed case, or a "
    "hand-written package not yet listed"
)


def compared(checked: Sequence[Checked], packages: Path, stale: Sequence[Path]) -> int:
    """Say each file of each package that isn't the committed one, and fail if any (brief, D1).
    A package written by hand (no files to compare) is said checked; a `stale` folder is refused."""
    failed = bool(stale)
    for folder in stale:
        print(f"{shown(folder)}: {STALE}")
    for each in checked:
        if not each.files:
            print(
                f"✓ {each.name} is valid ({each.steps} steps): written by hand, checked, not compared"
            )
            continue
        found = differences(each, packages)
        for difference in found:
            print(difference)
        if found:
            failed = True
            count = len(found)
            print(f"✗ {each.name}: {count} file{'s differ' if count > 1 else ' differs'}.")
        else:
            print(
                f"✓ {each.name} is unchanged: {shown(packages / each.name)}/ is what {each.source} writes"
            )
    if failed:
        print("Run `ventoux check` and commit what it writes.")
        return FAILS
    return HOLDS


def simulate_story(path: Path, catalog: Catalog) -> int:
    """Print the story's simulation, then whether what it expects holds."""
    try:
        story, case = read_story(path)
        simulation = simulate(story, case, catalog)
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


def release_package(folder: Path, releases: Path, commit: str, catalog: Catalog) -> int:
    """Print what releasing `folder` did: a release, a wording revision, or nothing; or why it
    was refused (brief, D50). Paths and names only, never a value."""
    try:
        run = release(folder, FolderStore(releases), commit, catalog)
    except (PackageRefused, RecordRefused, NotesRefused) as refused:
        print(Unreadable(folder, str(refused)), file=sys.stderr)
        return FAILS
    except (PackageUnreadable, OSError) as unreadable:
        print(Unreadable(folder, str(unreadable)), file=sys.stderr)
        return CANT_READ
    for issue in run.warnings:
        print(f"warning: {said(issue)}")
    print(what_it_did(run))
    if run.notes is not None and run.notes.against is not None:
        print(Diff(run.package, run.notes.changes, run.notes.wording, run.notes.rewritten), end="")
    return HOLDS


def diff_packages(old: Path, new: Path, catalog: Catalog, in_plain: bool = False) -> int:
    """Print what changed from the package in `old` to the one in `new`, by effect (brief, D55),
    in plain language if asked (brief, D56). Exit 0 when compared, whatever was found: a looser
    change is the reviewer's to judge."""
    folder = old
    try:
        before = read_package(old)
        folder = new
        after = read_package(new)
        found = diff(before, after, catalog)
        said = plain(found, before, after, catalog) if in_plain else str(found)
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


def map_package(folder: Path, catalog: Catalog) -> int:
    """Print what a case of the package in `folder` can do, then what it will never do
    (brief, D56). Exit 1 when the package or a reading is refused, 2 when it can't be read."""
    try:
        package = read_package(folder)
        said = f"{case_map(package, catalog)}\n{never_sheet(package, catalog)}"
    except (PackageRefused, ReadingRefused, SheetRefused) as refused:
        print(Unreadable(folder, str(refused)), file=sys.stderr)
        return FAILS
    except (PackageUnreadable, OSError) as unreadable:
        print(Unreadable(folder, str(unreadable)), file=sys.stderr)
        return CANT_READ
    print(said, end="")
    return HOLDS


def print_notes(
    name: str, number: int, wording: int, releases: Path, in_plain: bool, catalog: Catalog
) -> int:
    """Print a record's notes, as it keeps them: in the developer form, or the plain one, read
    from the two stored packages (brief, D57). Exit 1 when the record isn't there or a reading is
    refused, 2 when the records can't be read."""
    store = FolderStore(releases)
    try:
        kept = store.get(name, number, wording)
        said = told(kept)
        against = None if kept.notes is None else kept.notes.against
        if in_plain and against is not None:
            before = stored(store.get(name, against.release, against.wording), name)
            said = plain(as_diff(kept), before, stored(kept, name), catalog)
    except (RecordRefused, ReadingRefused) as refused:
        print(refused, file=sys.stderr)
        return FAILS
    except OSError as unreadable:
        print(f"{releases}: can't be read: {unreadable.strerror}", file=sys.stderr)
        return CANT_READ
    print(said, end="")
    return HOLDS


def summarize_merge(
    arguments: argparse.Namespace, catalog: Catalog, head_catalog: str | None
) -> int:
    """Print what merging a pull request changes to the log, whole, and append it to the job
    summary, or where it is when it is too long (brief, D55, as amended in 13e). Exit 0 when
    everything is compared, 1 when something is refused, 2 when something can't be read."""
    commits = None
    if arguments.base_commit and arguments.head_commit:
        commits = (arguments.base_commit, arguments.head_commit)
    try:
        recorded = read_plain_json(arguments.lock)
        base_recorded = read_plain_json(arguments.base_lock)
        before = read_plain_json(arguments.before)
        given = (
            (arguments.lock, recorded),
            (arguments.base_lock, base_recorded),
            (arguments.before, before),
        )
        for path, found in given:
            if not isinstance(found, dict):
                raise Unreadable(path, "isn't a JSON object, by contract reference")
        # The base's catalog, by the name its configuration gives, read as text: nothing of the
        # base is imported here (brief, D59).
        base_configuration = arguments.base / "pyproject.toml"
        base_catalog = read(base_configuration).catalog if base_configuration.is_file() else None
    except Unconfigured as unconfigured:
        print(unconfigured, file=sys.stderr)
        failed = cant_be_read(str(unconfigured))
        with arguments.summary_file.open("a") as summary:
            summary.write(for_summary_file(failed, arguments.limit))
        return CANT_READ
    except Unreadable as unreadable:
        # Fail closed: said in the log and the summary, never read as nothing changed.
        print(unreadable, file=sys.stderr)
        failed = cant_be_read(str(unreadable))
        with arguments.summary_file.open("a") as summary:
            summary.write(for_summary_file(failed, arguments.limit))
        return CANT_READ
    found = summarize(
        arguments.base,
        arguments.head,
        arguments.packages,
        catalog,
        recorded,
        before,
        base_recorded,
        commits,
        (base_catalog, head_catalog),
    )
    print(found.text, end="")
    with arguments.summary_file.open("a") as summary:  # earlier steps' summaries are kept
        summary.write(for_summary_file(found, arguments.limit))
    return found.code


def print_promises(catalog: Catalog) -> int:
    """Print each contract's promise, by reference, as canonical JSON: what the base commit's
    code gives `ventoux hashes --before` (brief, D57)."""
    promises = {contract.reference: promise_of(contract) for contract in catalog.contracts()}
    print(json.dumps(promises, indent=2, sort_keys=True))
    return HOLDS


def check_lockfile(lock: Path, before: Path | None, catalog: Catalog) -> int:
    """Print the hash check: each contract changed without a new version, with what changed
    when `before` gives the base commit's promises (brief, D57). Exit 0 when every contract
    matches, 1 on any problem, 2 when a file can't be read."""
    try:
        recorded = read_plain_json(lock)
        given = None if before is None else read_plain_json(before)
    except Unreadable as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ
    for path, found in ((lock, recorded), (before, given)):
        if path is not None and not isinstance(found, dict):
            print(Unreadable(path, "isn't a JSON object, by contract reference"), file=sys.stderr)
            return CANT_READ
    problems = check_hashes(catalog, recorded, given)
    for problem in problems:
        print(problem)
    if problems:
        return FAILS
    print(f"every contract matches {lock.name}")
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


def read_plain_json(path: Path) -> Any:
    """The JSON in `path`, as plain JSON values: a promise and a hash are hashed as JSON gives
    them, so its numbers stay as JSON reads them."""
    try:
        return json.loads(path.read_text())
    except OSError as error:
        raise Unreadable(path, f"can't be read: {error.strerror}") from None
    except json.JSONDecodeError as error:
        raise Unreadable(path, f"isn't JSON: {error.msg}, at line {error.lineno}") from None


def read_json(path: Path) -> Any:
    """The JSON in `path`, numbers read as exact decimals, never binary floats (brief, D20)."""
    try:
        return json.loads(path.read_text(), parse_float=Decimal)
    except OSError as error:
        raise Unreadable(path, f"can't be read: {error.strerror}") from None
    except json.JSONDecodeError as error:
        raise Unreadable(path, f"isn't JSON: {error.msg}, at line {error.lineno}") from None
