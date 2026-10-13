"""The check before an activity: what an activity is given, checked with the real sources of
each value, before it is scheduled (layer 5).

The static check (`validate`, layer 4) reads where a plan's fields are declared to come from; this
one reads where each value really came from. Used by the interpreter and the case runtime.
See docs/layers/05-interpreter.md.
"""

from collections.abc import Mapping
from decimal import Decimal

from pydantic import ValidationError

from ventoux.core.contract import Contract
from ventoux.core.expressions import (
    Expression,
    ExpressionError,
    FieldType,
    ReferenceType,
    Var,
    evaluate,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.policy import refusal
from ventoux.core.provenance import NoSources, provenance
from ventoux.core.references import references


class InputRefused(Exception):
    """An activity's inputs the engine won't give it: what is wrong."""


def checked_inputs(
    contract: Contract,
    inputs: Mapping[str, Expression],
    values: Mapping[str, object],
    sources: Mapping[str, frozenset[str]],
    key: str,
    types: Mapping[str, FieldType],
) -> dict[str, object]:
    """The inputs `contract`'s activity gets, evaluated from `values`, with the idempotency `key`
    if it takes one; or `InputRefused`.

    `sources` are where each value really came from, never only what a definition declared;
    `types` are the declared fields' types, which say which system each reference names.
    """
    # A reference input takes a reference of its system, before anything else is read: an ID from
    # the wrong system can look exactly like a right one (brief, D30).
    for field, system in references(contract.input).items():
        if field in inputs and (wrong := not_a_reference_to(system, inputs[field], types)):
            raise InputRefused(
                f"{contract.reference} takes {field} as a reference to {system}, and is given "
                f"{wrong}"
            )
    # Every policy on every input, before anything else (brief, D21): the injection is refused
    # on where the value came from, whatever it says.
    for field, expression in inputs.items():
        try:
            found = provenance(expression, sources)
        except NoSources as unset:
            # Fail closed: a field nobody has set yet (a form not answered) has no value to check.
            raise InputRefused(f"{field} can't be evaluated: {unset}") from None
        for policy in contract.policies(field):
            if policy.refuses(found) is not None:
                raise InputRefused(refusal(contract.reference, field, policy, expression, sources))
    given = {field: evaluated(field, expression, values) for field, expression in inputs.items()}
    # The engine fills the key, never a definition: the same for a retry, new for each run of the
    # step (brief, D17).
    if contract.idempotency_key is not None:
        given[contract.idempotency_key] = key
    # Fail closed: Pydantic ignores a field the model doesn't declare; an activity never gets one.
    unknown = sorted(set(given) - set(contract.input.model_fields))
    if unknown:
        raise InputRefused(
            f"{contract.reference} doesn't take these inputs: "
            + "; ".join(f"{name}: not an input it takes" for name in unknown)
        )
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        contract.input.model_validate(given)
    except ValidationError as error:
        raise InputRefused(
            f"{contract.reference} doesn't take these inputs: {one_line(error)}"
        ) from None
    return given


def one_line(error: ValidationError) -> str:
    """Pydantic's errors as one line: `status: Field required; amount: …`."""
    return "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()
    )


def evaluated(field: str, expression: Expression, values: Mapping[str, object]) -> object:
    """The input's value, or `InputRefused`: one that can't be evaluated never gets a default."""
    try:
        return evaluate(expression, values)
    except ExpressionError as error:
        raise InputRefused(f"{field} can't be evaluated: {error}") from None


def not_a_reference_to(
    system: str, expression: Expression, types: Mapping[str, FieldType]
) -> str | None:
    """What `expression` gives instead of a reference to `system`, or None if it gives one."""
    # Only a field read as it is: a computed value has no system, whatever it looks like.
    if not isinstance(expression, Var):
        if isinstance(expression, Decimal | str | bool):
            return "a value written in the definition"
        return "a computed value"
    declared = types.get(expression.var)
    if declared is None:
        # An outcome or an output (`assess.outcome`, `pay.refund_id`): never a reference.
        return f"{expression.var}, which is not a reference"
    if isinstance(declared, ReferenceType) and declared.system == system:
        return None
    return f"{expression.var}, {a_type(declared)}"
