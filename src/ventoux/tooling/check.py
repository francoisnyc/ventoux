"""`ventoux check`: run the builder files, check each package as `ventoux release` checks it, say
each problem at the line of Python that made it, and write the packages only if all pass
(layer 14c) (brief, D59).

The builder files are the team's own code, reviewed like any code: a file named on the command
line, or one in the configured `cases` folder, never a file a definition, a story or a package
names, and never model output (brief, D58). What is checked is the JSON they write, never the
Python. See docs/layers/14-builder.md, choices 29 to 33.
"""

import runpy
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from traceback import extract_tb

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.releases import PackageRefused, read_json
from ventoux.case.releases import package as read_package
from ventoux.core.catalog import Catalog
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.tooling.builder.case import Case
from ventoux.tooling.builder.written import package
from ventoux.tooling.releases import issues_of


class CheckRefused(Exception):
    """A builder file that can't be run, or two packages of one name: nothing is checked."""


@dataclass(frozen=True)
class Problem:
    """One problem, said where the builder call that made it was written."""

    where: str  # `cases/refund.py:24`
    path: str  # where in the definition, as validation says it: `steps.pay.inputs.amount`
    code: str  # which rule it breaks, `INPUT_POLICY`; `REFUSED` for a shape the reader refuses
    message: str
    warning: bool = False

    def __str__(self) -> str:
        kind = " (warning)" if self.warning else ""
        at = f" {self.path}" if self.path else ""
        return f"{self.where}:{at} {self.code}{kind}: {self.message}"


@dataclass(frozen=True)
class Checked:
    """One package, checked: its files as they would be written, and its problems."""

    name: str
    steps: int  # how many steps its case has, to say so
    files: Mapping[str, str]  # by path in its folder: `case.json`, `plans/refund-order.json`
    problems: Sequence[Problem] = field(default_factory=tuple)

    @property
    def refused(self) -> bool:
        return any(not problem.warning for problem in self.problems)


def built(paths: Sequence[Path], root: Path) -> list[Case]:
    """Every case at the top level of each builder file, in order. A file that raises is refused
    at the line inside it where it raised (brief, D59)."""
    found: list[Case] = []
    named: dict[str, Path] = {}
    sys.path.insert(0, str(root))  # the team's own modules, as its tests import them
    try:
        for path in paths:
            for case in cases_in(path):
                if case.name in named:
                    raise CheckRefused(
                        f"{shown(path)} and {shown(named[case.name])} both define the case "
                        f"{case.name}: a package is known by its case's name, so keep one"
                    )
                named[case.name] = path
                found.append(case)
    finally:
        sys.path.remove(str(root))
    return found


def cases_in(path: Path) -> list[Case]:
    """The cases `path` defines at its top level, found by type, never by name."""
    if not path.is_file():
        raise CheckRefused(f"{shown(path)}: no such builder file")
    try:
        # Python: `run_path` runs a file as a script and gives back its top-level names. The file
        # is the team's own builder code, reviewed in a pull request (brief, D58).
        names = runpy.run_path(str(path), run_name="__ventoux_check__")
    # Any error in the team's file is said, at its line, whatever it is: nothing is checked then.
    except Exception as error:  # noqa: BLE001
        line = raised_at(error, path)
        raise CheckRefused(f"{shown(path)}:{line}: {type(error).__name__}: {error}") from None
    return [value for value in names.values() if isinstance(value, Case)]


def raised_at(error: BaseException, path: Path) -> int | str:
    """The line inside `path` where `error` was raised: the last frame of the traceback in it."""
    lines = [
        frame.lineno
        for frame in extract_tb(error.__traceback__)
        if Path(frame.filename).resolve() == path.resolve()
    ]
    return lines[-1] if lines and lines[-1] is not None else "?"


def check(case: Case, catalog: Catalog) -> Checked:
    """`case`'s package: its files, and each problem with it at the line that made it. The issues
    are `issues_of`'s, the list `ventoux release` refuses on, never a second set of rules."""
    files = package(case)
    where = recorded(case)
    steps = len(case.steps)
    shape = shape_problems(files, where)
    if shape:
        return Checked(case.name, steps, files, shape)
    plans = [text for name, text in files.items() if name != "case.json"]
    try:
        released = read_package(files["case.json"], plans)
    except PackageRefused as refused:
        return Checked(case.name, steps, files, said_at(str(refused), where))
    problems = [
        Problem(
            at(issue.path, where),
            issue.path,
            issue.code,
            issue.message,
            issue.severity == "warning",
        )
        for issue in issues_of(released, catalog)
    ]
    return Checked(case.name, steps, files, problems)


def recorded(case: Case) -> dict[str, str]:
    """Where each entry of `case`'s package was written, by its path, plans under
    `plans.<reference>`, as validation's issues name them."""
    where = dict(case.where)
    for reference, plan in case.plans.items():
        for path, location in plan.where.items():
            where[f"plans.{reference}" + (f".{path}" if path else "")] = location
    return where


def shape_problems(files: Mapping[str, str], where: Mapping[str, str]) -> list[Problem]:
    """What the engine's reader refuses in the files, each line at the entry it names."""
    problems: list[Problem] = []
    try:
        parse_case(read_json(files["case.json"], "case.json"))
    except CaseInvalid as invalid:
        problems += said_at(str(invalid), where)
    for name, text in files.items():
        if name == "case.json":
            continue
        data = read_json(text, name)
        reference = f"{data.get('plan')}@{data.get('version')}"
        try:
            parse_plan(data)
        except PlanInvalid as invalid:
            problems += said_at(str(invalid), where, prefix=f"plans.{reference}.")
    return problems


def said_at(lines: str, where: Mapping[str, str], prefix: str = "") -> list[Problem]:
    """Each line of a reader's refusal (`path: message`), at the entry its path names."""
    problems: list[Problem] = []
    for line in lines.splitlines():
        path, colon, message = line.partition(": ")
        if not colon or " " in path:
            path, message = "", line  # a line that names no path: said at the case
        path = prefix + path if path else prefix.rstrip(".")
        problems.append(Problem(at(path, where), path, "REFUSED", message))
    return problems


def at(path: str, where: Mapping[str, str]) -> str:
    """Where the builder call that wrote `path`'s entry was made: the longest recorded path it
    starts with, or the case's own line, never dropped."""
    found = ""
    for recorded_path in where:
        inside = path == recorded_path or path.startswith(
            (f"{recorded_path}.", f"{recorded_path}[")
        )
        if recorded_path and inside and len(recorded_path) > len(found):
            found = recorded_path
    return shown(where[found])


def write(checked: Sequence[Checked], packages: Path) -> None:
    """Write each package into `packages/<case>/`, holding exactly its files: a `.json` file there
    the package no longer writes is removed, as a release refuses any other file (brief, D50)."""
    for each in checked:
        folder = packages / each.name
        for old in sorted(folder.rglob("*.json")) if folder.exists() else []:
            if str(old.relative_to(folder)) not in each.files:
                old.unlink()
        for name, text in each.files.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)


def shown(location: str | Path) -> str:
    """A file, or a `file:line`, as a person reads it: relative to the current folder when it is
    inside it."""
    text = str(location)
    here = f"{Path.cwd()}/"
    return text.removeprefix(here)
