"""What each value of a case could be stamped with, read from its definition alone (layer 10c).

The opening, a person, a contract and a sender stamp what they write with sources that don't
depend on what they read (brief, D34) (brief, D36). A rule's `set` doesn't: a value it writes
comes from everything its rule read (brief, D42), so where a value could come from is grown
from nothing, round after round, until nothing changes. Nor does a step's start: what steers it
is what its conditions read, and it passes that on to its outcome, its outputs and the rules on
its start (brief, D43), so it is grown with them, as `started <step>`. Case validation reads it
for every value; the runtime reads it for a value nobody has set yet, which has no recorded
sources, so a condition naming it is judged on what it could be (brief, D39).
"""

from collections.abc import Callable, Mapping

from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, Rule, Started, TaskStep
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.expressions import Expression
from ventoux.core.output_sources import output_sources
from ventoux.core.provenance import answering, fields_read, is_trusted

# Where the case file's first values came from when a system opened the case (brief, D12).
OPENER = "system:opener"

# How a value is written, for the fixpoint: what it reads, and the sources its writer stamps on
# it whatever it read (its mark), or None for a step's start, which only passes on what it read.
type Write = tuple[frozenset[str], frozenset[str] | None]


def start_of(step: str) -> str:
    """The name the fixpoint gives to what steers a step's runs: the moment of its start, as a
    rule's `on` says it, `started goodbye`. Never a field's name: a name holds no space."""
    return f"started {step}"


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
    computed = computed_writes(case, contracts)
    for field in computed:
        sources[field] = frozenset()
    while True:
        grown = {
            field: frozenset(
                source
                for reads, mark in writes
                for source in (*(mark or ()), *(s for read in reads for s in sources.get(read, ())))
                # A start passes on only what it doesn't trust: a person's answer that let a
                # step start vouches for nothing it gives (brief, D43).
                if mark is not None or not is_trusted(source)
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
    computed = computed_writes(case, contracts)
    while True:
        more = {
            field
            for field, writes in computed.items()
            if field not in found
            and all(
                (mark is not None and refused(mark)) or any(read in found for read in reads)
                for reads, mark in writes
            )
        }
        if not more:
            return frozenset(found)
        found |= more


def computed_writes(
    case: CaseDefinition, contracts: Mapping[str, Contract]
) -> dict[str, list[Write]]:
    """Each value whose sources depend on what was read, with each of its writes: the fields
    rules set, each step's start, and each steered call's or plan's outcome and outputs."""
    found = rule_writes(case)
    for name in case.steps:
        found[start_of(name)] = start_writes(case, name)
    stamps = stamped(case, contracts, OPENER)  # who opens it stamps no outcome or output
    for name, step in case.steps.items():
        # A call's or a plan's outcome and outputs carry what steered the run, beside what its
        # contract or plan stamps; a task's answer is a person's, where steering ends
        # (brief, D43).
        if isinstance(step, PlanStep | CallStep):
            for value in [f"{name}.outcome", *outputs_of(name, contracts)]:
                if value in stamps:
                    found[value] = [(frozenset({start_of(name)}), stamps[value])]
    return found


def outputs_of(name: str, contracts: Mapping[str, Contract]) -> list[str]:
    """The case file's names for the outputs of the step `name`'s contract, if it has one."""
    if name not in contracts:
        return []
    return [f"{name}.{output}" for output in output_sources(contracts[name].output)]


def rule_writes(case: CaseDefinition) -> dict[str, list[Write]]:
    """Each field rules set, and for each rule setting it, the values it reads (its value's, its
    condition's, and what steered the start it fires on) and the field's mark."""
    found: dict[str, list[Write]] = {}
    for rule in case.rules.values():
        for field, expression in rule.then.set.items():
            reads = frozenset(fields_read(expression)) | rule_reads(rule)
            source = case.fields[field].source
            mark = frozenset({source} if source else set())
            found.setdefault(field, []).append((reads, mark))
    return found


def rule_reads(rule: Rule) -> frozenset[str]:
    """What a rule's acts count as read: what its condition reads, and, on a step's start, what
    steered that start (brief, D43)."""
    reads = set(fields_read(rule.when)) if rule.when is not None else set()
    if isinstance(rule.on, Started):
        reads.add(start_of(rule.on.started))
    return frozenset(reads)


def start_writes(case: CaseDefinition, name: str) -> list[Write]:
    """Each way the step `name` may start, as what steers a run started that way: its own
    condition and what steered the runs it requires (unless a task's), in every way; and for each
    rule that may start it, that rule's condition and moment too (brief, D43). A step nobody can
    start gets its own reads alone: it never runs, and `NEVER_RUNS` says why."""
    own = steered_by_itself(case, name)
    ways: list[Write] = []
    step = case.steps[name]
    if step.automatic or step.proposed_by:
        ways.append((own, None))
    for rule in case.rules.values():
        if name in rule.then.start:
            ways.append((own | rule_reads(rule), None))
    return ways or [(own, None)]


def steered_by_itself(case: CaseDefinition, name: str) -> frozenset[str]:
    """What steers every run of the step `name`, however it starts: its own condition, and what
    steered the runs of the steps it requires, unless a task's, whose answer is a person's."""
    step = case.steps[name]
    reads = set(fields_read(step.when)) if step.when is not None else set()
    for required in requirements(case)[name]:
        if required in case.steps and not isinstance(case.steps[required], TaskStep):
            reads.add(start_of(required))
    return frozenset(reads)


def starts_said(case: CaseDefinition) -> dict[str, list[str]]:
    """Each step's ways of starting, as a warning names them, in `start_writes`'s order."""
    said: dict[str, list[str]] = {}
    for name, step in case.steps.items():
        ways: list[str] = []
        if step.automatic and step.proposed_by:
            ways.append("it starts by itself or a person proposes it")
        elif step.automatic:
            ways.append("it starts by itself")
        elif step.proposed_by:
            ways.append("a person proposes it")
        ways += [f"{rule} starts it" for rule, r in case.rules.items() if name in r.then.start]
        said[name] = ways
    return said


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
    rules whose writes may be refused, and those whose writes never are (brief, D42). For a
    step's start, or what its run gives, it depends on how the step started (brief, D43)."""
    if (step := steered_step(case, contracts, field)) is not None:
        return how_started(case, contracts, opener, step, refused)
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


def steered_step(case: CaseDefinition, contracts: Mapping[str, Contract], value: str) -> str | None:
    """The step whose start `value` is, or whose run gives it (its outcome, an output), if a
    start steers it; None for any other value."""
    for name, step in case.steps.items():
        if value == start_of(name):
            return name
        if isinstance(step, PlanStep | CallStep) and value in (
            f"{name}.outcome",
            *outputs_of(name, contracts),
        ):
            return name
    return None


def how_started(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    opener: str,
    step: str,
    refused: Callable[[frozenset[str]], bool],
) -> str:
    """How a warning says that whether the step's start is refused depends on how it started:
    the ways whose start may be refused, and those whose never is (brief, D43)."""
    sources = case_sources(case, contracts, opener)
    some: list[str] = []
    others: list[str] = []
    for (reads, _), said in zip(start_writes(case, step), starts_said(case)[step], strict=False):
        steering = frozenset(
            s for read in reads for s in sources.get(read, ()) if not is_trusted(s)
        )
        (some if steering and refused(steering) else others).append(said)
    if not some or not others:
        return "depending on who wrote what its conditions read"
    return f"when {' or '.join(some)}, and not when {' or '.join(others)}"
