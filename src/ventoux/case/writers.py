"""What each value of a case could be stamped with, read from its definition alone (layer 10c).

Every writer stamps what it writes with sources that don't depend on what it read, so where a
value could come from is known in one pass (brief, D34) (brief, D36). Case validation reads it
for every value; the runtime reads it for a value nobody has set yet, which has no recorded
sources, so a condition naming it is judged on what it could be (brief, D39).
"""

from collections.abc import Mapping

from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, TaskStep
from ventoux.case.state import CaseState
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.expressions import Expression
from ventoux.core.output_sources import output_sources
from ventoux.core.provenance import answering, fields_read, is_trusted

# Where the case file's first values came from when a system opened the case (brief, D12).
OPENER = "system:opener"


def case_sources(
    case: CaseDefinition, contracts: Mapping[str, Contract], opener: str
) -> dict[str, frozenset[str]]:
    """Where each value of `case` comes from, by the name an expression reads it with, when
    `opener` opens it: the union of what each of its writers stamps (brief, D34)."""
    # A field a task's form sets comes from whoever answers; any other, from the opening, which
    # never gives a field a form sets.
    answered: dict[str, set[str]] = {}
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            for outcome in step.outcomes.values():
                for set_field in outcome.sets:
                    answered.setdefault(set_field, set()).add(answering(name))
    sources: dict[str, frozenset[str]] = {}
    for name, field in case.fields.items():
        writers = answered.get(name, {opener})
        # A mark adds distrust, never removes it, whoever writes the field (brief, D12).
        sources[name] = frozenset(writers | ({field.source} if field.source else set()))
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


def writers_of(
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
            could = could if could is not None else writers_of(case, catalog, state.opened_by)
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
