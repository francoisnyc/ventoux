"""The semantic diff in plain language: the one change list, read (layer 13c).

Each entry a change is about (a step, a field, a rule, an event, a close reason, a plan's state)
is read before and after, as D45 reads rules (D56), then each of its changes is said in its
verdict's words. The verdict is the change's: nothing here compares or judges again (brief, D55).
Markdown, so the CI step can show it as it is (13e). Given no case file: it quotes nothing a case
holds. See docs/layers/13-diff.md (13c) and docs/guides/releases.md, "What changed: the diff".
"""

from ventoux.case.changes import Change
from ventoux.case.diff import Diff, quoted
from ventoux.case.reading import EntryReading, PatternReading, Reading, read_entry
from ventoux.case.releases import Package
from ventoux.core.catalog import Catalog
from ventoux.core.plan import ActivityState, ApprovalState

# Each verdict's words, the same everywhere: a doubt reads as possibly looser (brief, D55).
WORDS = {
    "looser": "Looser",
    "stricter": "Stricter",
    "not proven": "Changed, not proven either way (read it as possibly looser)",
}

# The sections of a case whose entries are read one by one; anything else of the case is about
# how it closes, or the case as a whole.
ENTRIES = ("fields", "steps", "events", "close_reasons", "rules")
CLOSING = ("closes_when", "stays_open", "forgetting")


def plain(found: Diff, before: Package, after: Package, catalog: Catalog) -> str:
    """The plain form of `found`, the diff from `before` to `after`: each entry, in the change
    list's order, read before and after, then its changes in their verdicts' words; what is
    written otherwise, then the wording, apart."""
    lines = [f"## {found.name}: what changes", "", f"{counts(found)}."]
    for entry, changes in grouped(found.changes):
        lines += ["", f"### {entry}", ""]
        lines += read_as("Before", entry, before, catalog)
        lines += read_as("After", entry, after, catalog)
        lines += [
            f"- **{WORDS[change.verdict]}** (`{change.path}`): {said(change)}."
            for change in changes
        ]
        lines += known_limit(changes, after)
    if found.rewritten:
        lines += ["", "### Written otherwise, the same decisions", ""]
        lines += [f"- `{line.path}`: {line.said}." for line in found.rewritten]
    if found.wording:
        lines += ["", "### Wording", ""]
        lines += [
            f"- `{line.path}`: {quoted(line.before)} -> {quoted(line.after)}."
            for line in found.wording
        ]
    return "\n".join(lines) + "\n"


def counts(found: Diff) -> str:
    """The summary line, without the package's name, which the heading says."""
    return found.summary().removeprefix(f"{found.name}: ")


def said(change: Change) -> str:
    """What the change says, and why, for a change derived from another."""
    return f"{change.said} (because {change.because})" if change.because else change.said


def entry_of(path: str) -> str:
    """The entry a change at `path` is about: `steps.pay` for `steps.pay.approval.count`."""
    parts = path.split(".")
    if parts[0] in ENTRIES and len(parts) > 1:
        return ".".join(parts[:2])
    if parts[0] == "plans" and len(parts) >= 4 and parts[2] in ("states", "fields"):
        return ".".join(parts[:4])
    if parts[0] == "plans":
        return ".".join(parts[:2])
    return "closing" if parts[0] in CLOSING else parts[0]


def grouped(changes: tuple[Change, ...]) -> list[tuple[str, list[Change]]]:
    """The changes by entry, each entry where its first change is: the change list's order."""
    found: dict[str, list[Change]] = {}
    for change in changes:
        found.setdefault(entry_of(change.path), []).append(change)
    return list(found.items())


def read_as(when: str, entry: str, version: Package, catalog: Catalog) -> list[str]:
    """`- Before: …` and its fine print, or nothing if the version has no such entry."""
    reading = read_entry(entry, version.case, version.plans, catalog)
    if reading is None:
        return []
    sentence, fine = parts_of(reading)
    return [f"- {when}: {sentence}", *(f"  - {line}" for line in fine)]


def parts_of(reading: object) -> tuple[str, tuple[str, ...]]:
    """A reading's sentence and its fine print, whichever kind it is."""
    if isinstance(reading, EntryReading | Reading):
        return reading.sentence, reading.fine_print
    if isinstance(reading, PatternReading):
        return f"{reading.sentence} It expands to {', '.join(reading.rules)}.", ()
    raise TypeError(f"no reading of the kind {type(reading).__name__}")  # fail closed


def known_limit(changes: list[Change], after: Package) -> list[str]:
    """13b's known limit, said where it applies: a plan's approved activity moved to another
    contract has its approvers compared by the approval's roles, never again for the new risk
    (13c, choice 37). A sentence about what the diff did, true of every case."""
    notes: list[str] = []
    for change in changes:
        parts = change.path.split(".")
        if not (parts[0] == "plans" and len(parts) == 5 and parts[2] == "states"):
            continue
        if parts[4] != "activity" or parts[1] not in after.plans:
            continue
        plan, state = after.plans[parts[1]], parts[3]
        target = plan.states.get(state)
        approving = [
            name
            for name, found in plan.states.items()
            if isinstance(found, ApprovalState) and found.approval.of == state
        ]
        if not isinstance(target, ActivityState) or not approving:
            continue
        by = " and ".join(approving)
        note = (
            f"- Note: who may approve {state} in the plan was compared by {by}'s roles, not "
            f"again for {target.activity}'s risk: read {by}'s roles."
        )
        if note not in notes:
            notes.append(note)
    return notes
