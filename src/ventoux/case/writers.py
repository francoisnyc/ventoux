"""What each value of a case could be stamped with, read from its definition alone (layer 10c).

The opening, a person, a contract and a sender stamp what they write with sources that don't
depend on what they read (brief, D34) (brief, D36). A rule's `set` doesn't: a value it writes
comes from everything its rule read (brief, D42), so where a value could come from is grown
from nothing, round after round, until nothing changes. Case validation reads it for every
value; the runtime reads it for a value nobody has set yet, which has no recorded sources, so a
condition naming it is judged on what it could be (brief, D39).
"""

from collections.abc import Callable, Mapping

from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, TaskStep
from ventoux.case.state import CaseState
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.expressions import Expression
from ventoux.core.output_sources import output_sources
from ventoux.core.provenance import answering, fields_read, is_trusted

# Where the case file's first values came from when a system opened the case (brief, D12).
OPENER = "system:opener"


def sending(event: str) -> str:
    """The static check's source for a value a person sends with `event`: a person, trusted,
    though nobody knows who until it arrives. At runtime it is who sent it, `person:ana`."""
    return f"person:sending {event}"


def case_sources(
    case: CaseDefinition, contracts: Mapping[str, Contract], opener: str
) -> dict[str, frozenset[str]]:
    """Where each value of `case` may come from, by the name an expression reads it with, when
    `opener` opens it: the union of what each of its writers may stamp (brief, D34). A field
    rules set comes from what its rules read, so it is grown from nothing until a round changes
    nothing; it ends, since each round only adds, out of finitely many fields and sources
    (brief, D42)."""
    sources = stamped(case, contracts, opener)
    computed = rule_writes(case)
    for field in computed:
        sources[field] = frozenset()
    while True:
        grown = {
            field: frozenset(
                source
                for reads, mark in writes
                for source in (*mark, *(s for read in reads for s in sources.get(read, ())))
            )
            for field, writes in computed.items()
        }
        if all(grown[field] == sources[field] for field in computed):
            return sources
        sources |= grown


def always(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    opener: str,
    refused: Callable[[frozenset[str]], bool],
) -> frozenset[str]:
    """Each value of `case`, opened by `opener`, that `refused` refuses whichever writer wrote
    it: what a check may claim of every case (brief, D34). A refusal looks for one source it
    refuses, and a value a rule sets comes from the union of what it read, so a rule's write is
    refused when its field's mark is, or a value it reads always is. Grown from nothing, so two
    fields set from each other vouch for nothing (brief, D42)."""
    found = {name for name, sources in stamped(case, contracts, opener).items() if refused(sources)}
    computed = rule_writes(case)
    while True:
        more = {
            field
            for field, writes in computed.items()
            if field not in found
            and all(refused(mark) or any(read in found for read in reads) for reads, mark in writes)
        }
        if not more:
            return frozenset(found)
        found |= more


def rule_writes(case: CaseDefinition) -> dict[str, list[tuple[frozenset[str], frozenset[str]]]]:
    """Each field rules set, and for each rule setting it, the values it reads (its value's and
    its condition's) and the field's mark."""
    found: dict[str, list[tuple[frozenset[str], frozenset[str]]]] = {}
    for rule in case.rules.values():
        for field, expression in rule.then.set.items():
            read = [expression, *([rule.when] if rule.when is not None else [])]
            reads = frozenset(name for e in read for name in fields_read(e))
            source = case.fields[field].source
            mark = frozenset({source} if source else set())
            found.setdefault(field, []).append((reads, mark))
    return found


def stamped(
    case: CaseDefinition, contracts: Mapping[str, Contract], opener: str
) -> dict[str, frozenset[str]]:
    """What each writer that reads nothing to stamp a value stamps it with: the opening, a
    person, a contract, a sender. A field rules set is left out (brief, D42)."""
    # A field a task's form sets comes from whoever answers; a field rules set, from what they
    # read; any other, from the opening, which never gives a field a form or a rule sets.
    answered: dict[str, set[str]] = {}
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            for outcome in step.outcomes.values():
                for set_field in outcome.sets:
                    answered.setdefault(set_field, set()).add(answering(name))
    computed = rule_writes(case)
    sources: dict[str, frozenset[str]] = {}
    for name, field in case.fields.items():
        if name in computed:
            continue
        writers = answered.get(name, {opener})
        # A mark adds distrust, never removes it, whoever writes the field (brief, D12).
        sources[name] = frozenset(writers | ({field.source} if field.source else set()))
    # Each value an event carries comes from its one sender, and its field's mark adds to that
    # whoever sends it (brief, D12) (brief, D41).
    for name, event in case.events.items():
        system = event.sent_by.system
        sender = sending(name) if system is None else f"system:{system}"
        for carried_as, carried in event.payload.items():
            mark = {carried.source} if carried.source else set()
            sources[f"{name}.{carried_as}"] = frozenset({sender} | mark)
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            sources[f"{name}.outcome"] = frozenset({answering(name)})
        elif isinstance(step, PlanStep):
            sources[f"{name}.outcome"] = frozenset({f"system:{step.plan}"})
        elif name in contracts:
            contract = contracts[name]
            sources[f"{name}.outcome"] = frozenset({f"system:{contract.reference}"})
            # An output carries its contract's source, never one the activity sends (brief, D29).
            for output, source in output_sources(contract.output).items():
                sources[f"{name}.{output}"] = frozenset({source})
        # A step whose contract is missing gives nothing: reading it is already an issue (10b).
    return sources


def could_come_from(
    case: CaseDefinition, catalog: Catalog, opened_by: str | None
) -> dict[str, frozenset[str]]:
    """Where each value of a case `opened_by` opened (None: a system) could come from, with the
    contracts the catalog holds: what the runtime reads for a value nobody has set yet."""
    contracts: dict[str, Contract] = {}
    for name, step in case.steps.items():
        if isinstance(step, CallStep):
            try:
                contracts[name] = catalog.lookup(step.called)
            except NotInCatalog:
                continue  # it gives nothing: a step reading it fails, saying so
    opener = OPENER if opened_by is None else f"person:{opened_by}"
    return case_sources(case, contracts, opener)


def read_sources(
    case: CaseDefinition, catalog: Catalog, state: CaseState, expression: Expression | None
) -> dict[str, frozenset[str]]:
    """Where each value `expression` reads came from, in the order it reads them. A value nobody
    has set yet has no recorded sources: it counts what any of its writers could give, never "no
    sources" (fail closed) (brief, D39)."""
    read: dict[str, frozenset[str]] = {}
    could: dict[str, frozenset[str]] | None = None
    for field in [] if expression is None else fields_read(expression):
        sources = state.sources.get(field)
        if sources is None:
            could = could if could is not None else could_come_from(case, catalog, state.opened_by)
            sources = could.get(field, frozenset({f"no known source for {field}"}))
        read.setdefault(field, sources)
    return read


def untrusted_of(read: Mapping[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Each value read whose sources include one the engine doesn't trust, with those sources."""
    found: dict[str, frozenset[str]] = {}
    for field, sources in read.items():
        untrusted = frozenset(source for source in sources if not is_trusted(source))
        if untrusted:
            found[field] = untrusted
    return found


def writer_decides(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    opener: str,
    field: str,
    refused: Callable[[frozenset[str]], bool],
) -> str:
    """How a warning says that whether `field` is refused depends on which rule wrote it: the
    rules whose writes may be refused, and those whose writes never are (brief, D42)."""
    sources = case_sources(case, contracts, opener)
    stamps: dict[str, frozenset[str]] = {}
    for name, rule in case.rules.items():
        if field in rule.then.set:
            read = [rule.then.set[field], *([rule.when] if rule.when is not None else [])]
            mark = case.fields[field].source
            stamps[name] = frozenset({mark} if mark else set()).union(
                *(sources.get(f, frozenset()) for e in read for f in fields_read(e))
            )
    some = [name for name, stamp in stamps.items() if refused(stamp)]
    others = [name for name in stamps if name not in some]
    if not others:
        return "depending on which rules set what it is computed from"
    sets = "sets" if len(some) == 1 else "set"
    does = "does" if len(others) == 1 else "do"
    return f"when {' or '.join(some)} {sets} it, and not when {' or '.join(others)} {does}"
