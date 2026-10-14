"""A sensitive value: kept wrapped wherever it goes, and never written out (layer 9b).

A field declared sensitive holds personal data a decision needs (brief, D8) (brief, D15). Its
value is wrapped in `Sensitive` in the state, so anything that formats it (a history line, a
refusal, a traceback) writes `‹sensitive›`. Crossing Temporal, the converter gives each wrapped value its
own part of the payload, which the codec encrypts with the case's key (brief, D31). Expressions
read the value inside: conditions and checks work on the real value.
See docs/layers/09-case-data.md (9b).
"""

from collections.abc import Mapping
from dataclasses import dataclass

# What a sensitive value reads as, wherever it would be written.
PLACEHOLDER = "‹sensitive›"


@dataclass(frozen=True)
class Sensitive:
    """A value nobody outside the worker reads in plain text."""

    value: object  # the plain value, of its field's type

    def __str__(self) -> str:
        return PLACEHOLDER

    # Python: `repr` too, which lists, dicts and tracebacks use to show a value.
    def __repr__(self) -> str:
        return PLACEHOLDER


def plain(value: object) -> object:
    """`value` without its wrapper, if it has one."""
    return value.value if isinstance(value, Sensitive) else value


def unwrapped(values: Mapping[str, object]) -> dict[str, object]:
    """Each value without its wrapper: what an activity's code is given."""
    return {name: plain(value) for name, value in values.items()}
