"""The page "Approve this plan": what a person reads before keeping a plan a model drafted
(brief, D64).

Only a draft that passes is shown, and the sheet checks it again itself, in its package, with the
function `ventoux release` checks with: never on the record's word. What it shows is read from the
parsed plan, the package and the record's settled fields, never from the model's own text, and
every piece a definition or a person writes is escaped where it is written (brief, D56). Pure:
it asks no model and reads no file.
"""

import json
from dataclasses import dataclass
from decimal import Decimal

from ventoux.case.checked import is_error, issues_of, said
from ventoux.case.diff import diff
from ventoux.case.markdown import code, text
from ventoux.case.plain import plain
from ventoux.case.releases import Package, PackageRefused, package
from ventoux.case.sheet import never_sheet, plan_read
from ventoux.core.catalog import Catalog
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.validate import Issue


class NotApprovable(Exception):
    """The draft can't be shown for approval: it doesn't read, or doesn't pass its package's
    check. The message says why."""


@dataclass(frozen=True)
class Drafted:
    """A drafted plan and its provenance, as its record settled it (brief, D63)."""

    text: str  # the draft's JSON text, as the drafts folder holds it
    path: str  # where the draft is, as a person reads it: `drafts/refund-order@1.json`
    asked_by: str  # who asked for it, an identifier (brief, D22)
    provider: str  # the provider, as it names itself: `anthropic:<model>`, `recorded`
    goal: str  # the goal, in the person's words
    rounds: int  # how many rounds it took


def approve_this_plan(drafted: Drafted, before: Package, folder: str, catalog: Catalog) -> str:
    """The page "Approve this plan" for `drafted`, a plan of `before`, the package at `folder`;
    refused with `NotApprovable` unless the package with the draft in place passes its check."""
    reference = reference_of(drafted.text)
    after = with_draft(before, reference, drafted.text)
    # Checked again here, never on the record's word: only a draft that passes is shown, and
    # only errors refuse, as for a release (brief, D50) (brief, D64).
    issues = issues_of(after, catalog)
    errors = [said(issue) for issue in issues if is_error(issue)]
    if errors:
        refused = (
            f"{reference} doesn't pass the check of {before.name}, so it is never shown for "
            "approval: draft it again"
        )
        raise NotApprovable("\n".join([refused, *errors]))
    found = diff(before, after, catalog)
    # Every piece a definition, the catalog or a person writes is shown, never rendered: `text`
    # and `code` escape it where Markdown is written (brief, D56, as amended in 13e).
    sections = [
        provenance(drafted, reference, before.name),
        plain(found, before, after, catalog),
        as_drafted(reference, after, catalog),
        one_level_down(never_sheet(after, catalog)),
        warnings_of(issues, reference, drafted.path, folder),
        HOW,
    ]
    return "\n".join(sections)


def provenance(drafted: Drafted, reference: str, package_name: str) -> str:
    """The title, and who drafted it for whom, from which goal: the record's settled fields
    only, the goal on one quoted line. No pronoun is guessed (brief, D14)."""
    rounds = "1 round" if drafted.rounds == 1 else f"{drafted.rounds} rounds"
    by = f"{code(drafted.provider)} for {text(drafted.asked_by)}, in {rounds}"
    lines = [
        f"# Approve this plan: {text(reference)}, for {text(package_name)}",
        "",
        f"Drafted by {by}, from the goal:",
        "",
        f"> {text(drafted.goal)}",
    ]
    return "\n".join(lines) + "\n"


def as_drafted(reference: str, after: Package, catalog: Catalog) -> str:
    """The whole plan as drafted, every field and state, as the case map reads it: the diff
    shows only what changed, and an approver reads the whole plan (brief, D56)."""
    lines = [f"## Plan {text(reference)}, as drafted", "", *plan_read(reference, after, catalog)]
    return "\n".join(lines) + "\n"


def warnings_of(issues: list[Issue], reference: str, draft: str, folder: str) -> str:
    """The warnings, each as `ventoux check` writes one for a package written by hand, at the
    file the issue is in; "None." when there are none, so the section never reads as unchecked
    (brief, D59) (brief, D64)."""
    lines = [
        f"- {text(f'{file_of(issue.path, reference, draft, folder)}: {as_checked(issue)}')}"
        for issue in issues
        if not is_error(issue)
    ]
    return "\n".join(["## Warnings", "", *(lines or ["None."])]) + "\n"


def as_checked(issue: Issue) -> str:
    """A warning after its file, as `ventoux check` writes it: `path CODE (warning): message`."""
    return f"{issue.path} {issue.code} (warning): {issue.message}"


def file_of(path: str, reference: str, draft: str, folder: str) -> str:
    """The file an issue at `path` is in: the draft, for the drafted plan's; the package's plan
    file, for another plan's (named as `ventoux check` names it); else the case's."""
    if path.startswith(f"plans.{reference}."):
        return draft
    if path.startswith("plans."):
        return f"{folder}/plans/{path.split('.')[1].partition('@')[0]}.json"
    return f"{folder}/case.json"


def one_level_down(page: str) -> str:
    """`page`'s headings one level down, under this page's title. Every value on it is escaped,
    so a line starting with `#` is always one of its headings (brief, D56)."""
    return "".join(
        f"#{line}" if line.startswith("#") else line for line in page.splitlines(keepends=True)
    )


# How a kept draft becomes real: a person's pull request, a release, an activation (brief, D50)
# (brief, D54).
HOW = (
    "## How it becomes real\n"
    "\n"
    "This is a draft. It runs nowhere until a pull request is reviewed and merged, a release is "
    "made, and an environment activates it.\n"
)


def reference_of(text: str) -> str:
    """The plan's reference, `refund-order@1`, read from the draft as a plan."""
    try:
        plan = parse_plan(json.loads(text, parse_float=Decimal))
    except (ValueError, RecursionError, PlanInvalid) as unread:
        raise NotApprovable(f"the draft doesn't read as a plan: {unread}") from None
    return f"{plan.plan}@{plan.version}"


def with_draft(before: Package, reference: str, text: str) -> Package:
    """`before` with the draft in place of its plan of the same reference, or added to it."""
    others = [written for name, written in before.written.plans.items() if name != reference]
    try:
        return package(before.written.case, [*others, text])
    except PackageRefused as refused:
        raise NotApprovable(f"{reference} doesn't fit {before.name}: {refused}") from None
