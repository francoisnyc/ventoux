"""The checks a case asks before it takes an answer: whether a system holds an option
(brief, D67), and whether a document store issued an ID (brief, D68).

The platform team registers one check per system; a definition names the system, never the
check. Both kinds keep the same rules, each refusing with what is wrong, then what to do: a check
only reads, takes one value, a reference to its system, and gives one truth value, from that
system. Only the names differ, so each kind is a `Shape`.
"""

from dataclasses import dataclass

from ventoux.core.contract import Contract
from ventoux.core.expressions import AttachmentType, OptionType
from ventoux.core.output_sources import output_sources
from ventoux.core.references import references


@dataclass(frozen=True)
class Shape:
    """What one kind of check is called, and the names of its one input and its one output."""

    type: str  # the field type it checks, as a definition writes it: "option"
    of: str  # how a message names a field of that type, before its system: "an option of"
    kind: str  # how a message names the check: "an option's check"
    asked: str  # its one input: the value a person gave, "option"
    answer: str  # its one output: whether the system vouches for it, "held"
    says: str  # what it says of its system, after "whether documents": "holds a value"


OPTION = Shape("option", "an option of", "an option's check", "option", "held", "holds a value")
DOCUMENT = Shape(
    "attachment",
    "an attachment in",
    "a document store's check",
    "attachment",
    "issued",
    "issued an ID",
)


def checked(declared: object) -> tuple[Shape, str] | None:
    """The kind of check a field of the type `declared` waits for, and the system it asks; None
    for a type nothing checks."""
    if isinstance(declared, OptionType):
        return OPTION, declared.system
    if isinstance(declared, AttachmentType):
        return DOCUMENT, declared.store
    return None


def check_problem(shape: Shape, system: str, check: Contract) -> str | None:
    """Why `check` can't be `system`'s check of this `shape`, or None if it can."""
    # It only asks: an answer is checked, never acted on, and replay reads what it said.
    effect = getattr(check, "effect", None)
    if effect != "read":
        return (
            f"{check.reference} is effect: {effect}, and {shape.kind} only reads: register a "
            f"read-only activity that says whether {system} {shape.says}"
        )
    return input_problem(shape, system, check) or output_problem(shape, system, check)


def input_problem(shape: Shape, system: str, check: Contract) -> str | None:
    """Why `check` doesn't take exactly one value, a reference to `system`; or None."""
    takes = list(check.input.model_fields)
    if takes == [shape.asked] and references(check.input).get(shape.asked) == system:
        return None
    return (
        f"{check.reference} takes {', '.join(takes) or 'nothing'}, and {shape.kind} takes "
        f"one value, {shape.asked}, a reference to {system}: declare it "
        f'Annotated[str, reference("{system}")]'
    )


def output_problem(shape: Shape, system: str, check: Contract) -> str | None:
    """Why `check` doesn't give exactly one truth value, from the system; or None."""
    sources = output_sources(check.output)
    fields = check.output.model_fields
    # The system's own word, nobody else's: the answer is what `system` says (brief, D29).
    one_truth_value = list(fields) == [shape.answer] and fields[shape.answer].annotation is bool
    if one_truth_value and sources[shape.answer] == f"system:{system}":
        return None
    gives = ", ".join(f"{name} ({source})" for name, source in sources.items()) or "nothing"
    return (
        f"{check.reference} gives {gives}, and {shape.kind} gives one truth value, "
        f"{shape.answer}, from system:{system}: declare it "
        f'Annotated[bool, source("system:{system}")]'
    )
