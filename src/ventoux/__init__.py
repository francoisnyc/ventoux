"""Ventoux: case management and human-in-the-loop workflows for Temporal."""

import importlib
from typing import TYPE_CHECKING, Any

# The builder's names, as the quickstart imports them (`from ventoux import Case`). The builder
# never runs inside the engine (brief, D58), so it is loaded only when one of its names is asked
# for: a worker importing `ventoux.temporal` runs this file and never loads the builder.
# Written out, not computed: mypy reads what a module exports only from a literal `__all__`.
__all__ = [
    "OPENED",
    "Approval",
    "Case",
    "Expr",
    "Field",
    "Outcome",
    "Payload",
    "Plan",
    "SentBy",
    "Then",
    "Transition",
    "after",
    "and_",
    "cat",
    "count",
    "exists",
    "four_eyes",
    "if_",
    "in_",
    "literal",
    "not_",
    "or_",
    "package",
    "string",
    "sum_",
    "written",
]

if TYPE_CHECKING:
    # Python: `TYPE_CHECKING` is true only for the type checker, which reads the names from here.
    from ventoux.tooling.builder import (
        OPENED,
        Approval,
        Case,
        Expr,
        Field,
        Outcome,
        Payload,
        Plan,
        SentBy,
        Then,
        Transition,
        after,
        and_,
        cat,
        count,
        exists,
        four_eyes,
        if_,
        in_,
        literal,
        not_,
        or_,
        package,
        string,
        sum_,
        written,
    )


# Python: a module's `__getattr__` runs only for a name the module doesn't hold (PEP 562), so the
# builder is imported the first time `ventoux.Case` or `from ventoux import Case` asks for it.
def __getattr__(name: str) -> Any:
    if name in __all__:
        # The module itself, by name, never `from ventoux.tooling import builder`: that reads the
        # `builder` attribute of the `ventoux.tooling` package, which Temporal's workflow sandbox
        # overwrites with its own copy of the builder each time it imports `ventoux.testing`
        # afresh. A `Case` from that copy is not the `Case` that `ventoux check` looks for
        # (found by the whole test suite, layer 14d).
        builder = importlib.import_module("ventoux.tooling.builder")
        return getattr(builder, name)
    raise AttributeError(f"module 'ventoux' has no attribute {name!r}")
