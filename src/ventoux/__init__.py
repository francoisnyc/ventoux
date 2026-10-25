"""Ventoux: case management and human-in-the-loop workflows for Temporal."""

from typing import TYPE_CHECKING, Any

# The builder's names, as the quickstart imports them (`from ventoux import Case`). The builder
# never runs inside the engine (brief, D58), so it is loaded only when one of its names is asked
# for: a worker importing `ventoux.temporal` runs this file and never loads the builder.
# Written out, not computed: mypy reads what a module exports only from a literal `__all__`.
__all__ = ["Approval", "Case", "Expr", "Field", "Outcome", "and_", "literal", "not_", "or_"]

if TYPE_CHECKING:
    # Python: `TYPE_CHECKING` is true only for the type checker, which reads the names from here.
    from ventoux.tooling.builder import (
        Approval,
        Case,
        Expr,
        Field,
        Outcome,
        and_,
        literal,
        not_,
        or_,
    )


# Python: a module's `__getattr__` runs only for a name the module doesn't hold (PEP 562), so the
# builder is imported the first time `ventoux.Case` or `from ventoux import Case` asks for it.
def __getattr__(name: str) -> Any:
    if name in __all__:
        from ventoux.tooling import builder

        return getattr(builder, name)
    raise AttributeError(f"module 'ventoux' has no attribute {name!r}")
