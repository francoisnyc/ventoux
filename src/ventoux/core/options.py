"""An option's check: the read-only activity that says whether a system holds a value (brief, D67).

The platform team registers one per system; a definition names the system, never the check. These
are the rules a check must keep, each refusing with what is wrong, then what to do.
"""

from ventoux.core.contract import Contract
from ventoux.core.output_sources import output_sources
from ventoux.core.references import references

ASKED = "option"  # the one input: the value a person gave
HELD = "held"  # the one output: whether the system holds it


def option_check_problem(system: str, check: Contract) -> str | None:
    """Why `check` can't be `system`'s option check, or None if it can."""
    # It only asks: an answer is checked, never acted on, and replay reads what it said.
    effect = getattr(check, "effect", None)
    if effect != "read":
        return (
            f"{check.reference} is effect: {effect}, and an option's check only reads: register "
            f"a read-only activity that says whether {system} holds a value"
        )
    return input_problem(system, check) or output_problem(system, check)


def input_problem(system: str, check: Contract) -> str | None:
    """Why `check` doesn't take exactly one value, `option`, a reference to `system`; or None."""
    takes = list(check.input.model_fields)
    if takes == [ASKED] and references(check.input).get(ASKED) == system:
        return None
    return (
        f"{check.reference} takes {', '.join(takes) or 'nothing'}, and an option's check takes "
        f"one value, {ASKED}, a reference to {system}: declare it "
        f'Annotated[str, reference("{system}")]'
    )


def output_problem(system: str, check: Contract) -> str | None:
    """Why `check` doesn't give exactly one truth value, `held`, from the system; or None."""
    sources = output_sources(check.output)
    fields = check.output.model_fields
    # The system's own word, nobody else's: the answer is what `system` holds (brief, D29).
    one_truth_value = list(fields) == [HELD] and fields[HELD].annotation is bool
    if one_truth_value and sources[HELD] == f"system:{system}":
        return None
    gives = ", ".join(f"{name} ({source})" for name, source in sources.items()) or "nothing"
    return (
        f"{check.reference} gives {gives}, and an option's check gives one truth value, {HELD}, "
        f'from system:{system}: declare it Annotated[bool, source("system:{system}")]'
    )
