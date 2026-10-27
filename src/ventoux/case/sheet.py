"""The case map and the "will never do" sheet of a package (layer 13c) (brief, D56).

The map reads every entry of the package in the format's order, judging nothing. The sheet says
what no case of the package will ever do: the engine's own guarantees once, above it, then each
line a proof for every case of this package, from a check that already proves it, out of a closed
list (`NEVERS`), each kind with a witness. Both are given the package and the catalog, never a
case file, so they quote nothing a case holds. Markdown, for the CI step to show as it is (13e).
See docs/layers/13-diff.md (13c) and docs/guides/cases.md, "What a case can do, and will never do".
"""

from dataclasses import dataclass

from ventoux.case.definition import CallStep, Rule, WorkflowStep
from ventoux.case.guards import excluded_every_time, whoever
from ventoux.case.markdown import text
from ventoux.case.reading import (
    EVERY_RULE,
    EntryReading,
    listed_and,
    read_closing,
    read_entry,
    read_patterns,
    read_rule,
)
from ventoux.case.releases import Package
from ventoux.case.visibility import roles_named, seen_by
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.plan import ActivityState
from ventoux.core.policy import SYSTEMS, TRUSTED, accepted

# What Ventoux's engine guarantees for every definition, said once above a sheet, each with the
# decisions it comes from; the tests that prove each are named in docs/layers/13-diff.md (13c).
ENGINE_WIDE = (
    (
        (
            "run anything written in its definition as code, or read a clock, randomness or "
            "outside data in a condition"
        ),
        "(brief, D20)",
    ),
    (
        "call anything the catalog doesn't hold: a definition names a contract, never defines one",
        "(brief, D5)",
    ),
    ("let untrusted data reach a milestone or stop a step", "(brief, D38)"),
    (
        (
            "let anyone approve a step their own answer feeds, or one they proposed, or one in a "
            "case they opened"
        ),
        "(brief, D11) (brief, D25)",
    ),
    ("let one approval unlock more than one run of one step", "(brief, D11)"),
    ("skip a failed step by itself: it waits for a person", "(brief, D17)"),
    ("give a sensitive value to a workflow step, or write one out", "(brief, D31)"),
)

# The kinds of line a sheet may say of a package, a closed list: each is proven for every case by
# a check that already proves it, and has a witness (brief, D56).
NEVERS = (
    "calls only",  # the engine calls only what a step or a state names (brief, D5)
    "changes the world only through",  # by the contracts' declared effect, never a name
    "input policy",  # every value an input takes is checked against its policies (brief, D21)
    "who sees",  # a field, an outcome or an output, seen by registered roles only (brief, D30)
    "sensitive",  # a sensitive value is never given to a workflow step (brief, D31)
    "who may not approve",  # nobody approves a step their own answer feeds (brief, D11)
    "runs only approved",  # an approval with no `when` is asked on every run (brief, D11)
    "forgetting",  # what the definition keeps (brief, D32)
)

# What a contract may do to the world, by its declared effect (brief, D5).
CHANGES_THE_WORLD = ("write", "notify")


@dataclass(frozen=True)
class Never:
    """One line of a sheet: what no case of the package will ever do, and which kind of proof."""

    kind: str  # one of NEVERS
    line: str  # as the sheet says it, after "will never"


# --- The case map --------------------------------------------------------------------------------


def case_map(package: Package, catalog: Catalog) -> str:
    """What a case of `package` can do: every entry read, in the format's order (brief, D56)."""
    case = package.case
    # Every piece a definition or the catalog writes is shown, never rendered: `text` escapes it
    # where Markdown is written (brief, D56, as amended in 13e).
    lines = [f"# {text(package.name)}: what a case can do"]

    def section(title: str, entries: list[str], above: str = "") -> None:
        nonlocal lines
        if not entries:
            return
        lines += ["", f"## {title}", ""]
        if above:
            lines += [above, ""]
        lines += entries

    section("Fields", [read(f"fields.{name}", package, catalog) for name in case.fields])
    section("Steps", [read(f"steps.{name}", package, catalog) for name in case.steps])
    section("Rules", rules_read(package), EVERY_RULE if case.written else "")
    section("Events", [read(f"events.{name}", package, catalog) for name in case.events])
    section(
        "Close reasons",
        [read(f"close_reasons.{name}", package, catalog) for name in case.close_reasons],
    )
    section("Closing", [bullet(read_closing(case))])
    for reference in package.plans:
        section(f"Plan {text(reference)}", plan_read(reference, package, catalog))
    return "\n".join(lines) + "\n"


def plan_read(reference: str, package: Package, catalog: Catalog) -> list[str]:
    """The plan `reference` of `package`: where it starts, then each field and state read, as
    the map and "Approve this plan" show it (brief, D56) (brief, D64)."""
    plan = package.plans[reference]
    entries = [f"- It starts at {text(plan.initial)}."]
    entries += [read(f"plans.{reference}.fields.{name}", package, catalog) for name in plan.fields]
    entries += [read(f"plans.{reference}.states.{name}", package, catalog) for name in plan.states]
    return entries


def read(path: str, package: Package, catalog: Catalog) -> str:
    """The entry at `path`, as a list item with its fine print."""
    reading = read_entry(path, package.case, package.plans, catalog)
    assert isinstance(reading, EntryReading)  # every path here names an entry the package has
    return bullet(reading)


def bullet(reading: EntryReading) -> str:
    """`- sentence`, and each line of fine print under it."""
    lines = [f"- {text(reading.sentence)}", *(f"  - {text(line)}" for line in reading.fine_print)]
    return "\n".join(lines)


def rules_read(package: Package) -> list[str]:
    """Each rule as written: a raw rule's reading, or a pattern's, with the rules it expands to
    (brief, D46)."""
    case = package.case
    patterns = {reading.name: reading for reading in read_patterns(case)}
    found: list[str] = []
    for name, entry in case.written.items():
        if isinstance(entry, Rule):
            reading = read_rule(name, case.rules[name], case)
            found.append(f"- **{text(name)}**: {text(reading.sentence)}")
            found += [f"  - {text(line)}" for line in reading.fine_print]
        else:
            pattern = patterns[name]
            found.append(f"- **{text(name)}**: {text(pattern.sentence)} It expands to:")
            for rule in pattern.rules:
                sentence = read_rule(rule, case.rules[rule], case).sentence
                found.append(f"  - **{text(rule)}**: {text(sentence)}")
    return found


# --- The "will never do" sheet -------------------------------------------------------------------


def never_sheet(package: Package, catalog: Catalog) -> str:
    """What no case of `package` will ever do: the engine's guarantees once, then the package's
    own lines, each a proof for every case (brief, D56)."""
    lines = [f"# {text(package.name)} will never", "", "## For every case, by Ventoux's engine", ""]
    lines += [f"- {line} {decisions}." for line, decisions in ENGINE_WIDE]
    # The package's own lines hold while a case runs this release: a migration moves a case to
    # the target release's definition (brief, D53) (13c, choice 48).
    lines += ["", f"## For every case of {text(package.name)}, while it runs this release", ""]
    lines += [f"- {text(never.line)}." for never in nevers(package, catalog)]
    return "\n".join(lines) + "\n"


def nevers(package: Package, catalog: Catalog) -> list[Never]:
    """The package's own lines, in the order of NEVERS, each only where it is proven."""
    called = contracts_called(package, catalog)
    return [
        *calls_only(called),
        *changes_only_through(called),
        *input_policies(called),
        *who_sees(package, catalog),
        *sensitive(package),
        *who_may_not_approve(package),
        *runs_only_approved(package),
        *forgetting(package),
    ]


def contracts_called(package: Package, catalog: Catalog) -> list[Contract]:
    """Every contract the package's steps and plans call, in the order they are written."""
    references = [step.called for step in package.case.steps.values() if isinstance(step, CallStep)]
    for plan in package.plans.values():
        references += [s.activity for s in plan.states.values() if isinstance(s, ActivityState)]
    found: list[Contract] = []
    for reference in dict.fromkeys(references):
        try:
            found.append(catalog.lookup(reference))
        except NotInCatalog as missing:
            raise SheetRefused(f"{missing} A sheet reads what each contract promises.") from None
    return found


class SheetRefused(Exception):
    """A sheet that can't be made whole: a line it can't prove is never left out quietly."""


def named(contract: Contract) -> str:
    """`payments.refund@2 (high risk, it writes)`."""
    effects = {"read": "reads", "compute": "computes", "write": "writes", "notify": "notifies"}
    return f"{contract.reference} ({contract.risk} risk, it {effects[contract.effect]})"


def calls_only(called: list[Contract]) -> list[Never]:
    """The engine calls only what a step or a plan's state names (brief, D5)."""
    if not called:
        return [Never("calls only", "call any contract")]
    return [Never("calls only", f"call anything but {listed_and([named(c) for c in called])}")]


def changes_only_through(called: list[Contract]) -> list[Never]:
    """By what its contracts declare, never by their names (brief, D56)."""
    changing = [c.reference for c in called if c.effect in CHANGES_THE_WORLD]
    if not changing:
        return [
            Never(
                "changes the world only through",
                "change the world, by what its contracts declare: they only read and compute",
            )
        ]
    line = f"change the world, by what its contracts declare, but through {listed_and(changing)}"
    return [Never("changes the world only through", line)]


def input_policies(called: list[Contract]) -> list[Never]:
    """Each input with a policy, said as what it refuses: every value is checked (brief, D21)."""
    found: list[Never] = []
    for contract in called:
        refused: dict[str, list[str]] = {}
        for name in contract.input.model_fields:
            shape, systems = accepted(contract.policies(name))
            if shape == TRUSTED:
                refused.setdefault("from untrusted data", []).append(name)
            elif shape == SYSTEMS:
                source = (
                    f"from anything but {' or '.join(sorted(systems))}" if systems else "at all"
                )
                refused.setdefault(source, []).append(name)
        for source, inputs in refused.items():
            given = " or ".join(f"its {name}" for name in inputs)
            found.append(Never("input policy", f"give {contract.reference} {given} {source}"))
    return found


def who_sees(package: Package, catalog: Catalog) -> list[Never]:
    """Who sees each field, and every outcome and output: registered roles only (brief, D30)."""
    case = package.case
    registered = [role for role in roles_named(case) if role in catalog.roles]
    groups: dict[tuple[str, ...], list[str]] = {}
    for name in case.fields:
        seen = tuple(role for role in seen_by(case, name) if role in catalog.roles)
        groups.setdefault(seen, []).append(name)
    found = [
        Never("who sees", f"show {listed_or(fields)} to {anyone_but(seen)}")
        for seen, fields in groups.items()
    ]
    if case.steps:
        line = f"show any step's outcome or outputs to {anyone_but(tuple(registered))}"
        found.append(Never("who sees", line))
    return found


def listed_or(parts: list[str]) -> str:
    """`a`, `a or b`, `a, b or c`."""
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} or {parts[-1]}"


def anyone_but(roles: tuple[str, ...]) -> str:
    """`anyone but support or support-lead`, or `anyone` when no role sees it."""
    return f"anyone but {' or '.join(roles)}" if roles else "anyone"


def sensitive(package: Package) -> list[Never]:
    """Each sensitive field, never given to a workflow step (brief, D31)."""
    case = package.case
    workflows = [name for name, step in case.steps.items() if isinstance(step, WorkflowStep)]
    if not workflows:
        return []
    return [
        Never("sensitive", f"give {name} to a workflow step ({listed_and(workflows)})")
        for name, field in case.fields.items()
        if field.sensitive
    ]


def who_may_not_approve(package: Package) -> list[Never]:
    """For each step with an approval, whoever is excluded from approving it in every run: a
    person whose answer it reads now may not approve it (brief, D11), and only a task's outcome,
    read directly, stays theirs whatever happens after (13c, choice 45)."""
    found: list[Never] = []
    for name, step in package.case.steps.items():
        if not isinstance(step, CallStep) or step.approval is None:
            continue
        people = excluded_every_time(package.case, step)
        if people:
            found.append(Never("who may not approve", f"let {whoever(people)} approve {name}"))
    return found


def runs_only_approved(package: Package) -> list[Never]:
    """A step whose approval has no `when` is asked for it on every run; with a `when`, it may run
    unapproved where it is false, so nothing is said (brief, D11)."""
    found: list[Never] = []
    for name, step in package.case.steps.items():
        if (
            not isinstance(step, CallStep)
            or step.approval is None
            or step.approval.when is not None
        ):
            continue
        roles, count = " or ".join(step.approval.roles), step.approval.count
        who = f"one {roles} approves" if count == 1 else f"{count} people, each a {roles}, approve"
        found.append(Never("runs only approved", f"run {name} unless {who} it"))
    return found


def forgetting(package: Package) -> list[Never]:
    """What the definition keeps (brief, D32)."""
    keeps = {
        "never": "forget a case's records",
        "while_open": "forget a closed case's records",
    }
    rule = package.case.forgetting
    return [Never("forgetting", keeps[rule])] if rule in keeps else []
