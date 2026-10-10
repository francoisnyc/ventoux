"""The contract test: a bound workflow, run on Temporal's test server, against its contract
(brief, D6). See docs/guides/activities.md, "The contract test".

A contract is a promise, not a proof: this checks the shape of what the workflow gives, never
whether a declared source is true, which is for review.
"""

import uuid
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import FailureError
from temporalio.exceptions import TimeoutError as TemporalTimeout  # not Python's own TimeoutError

from ventoux.core.before_activity import one_line
from ventoux.core.workflow_contract import WorkflowContract
from ventoux.temporal.bindings import Binding


async def check_workflow_contract(
    client: Client, contract: WorkflowContract, binding: Binding, input: dict[str, Any]
) -> list[str]:
    """Every way the bound workflow breaks its contract's promise, run with `input`; none if it
    keeps it. `input` must be one the contract accepts: the test checks the workflow, not you."""
    # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
    contract.input.model_validate(input)
    try:
        # Temporal: waiting on the result lets the time-skipping test server skip to the timeout.
        output: dict[str, Any] = await client.execute_workflow(
            binding.workflow,
            input,
            id=f"contract-test/{contract.reference}/{uuid.uuid4()}",  # a test, never a case
            task_queue=binding.task_queue,
            execution_timeout=timedelta(seconds=contract.timeout),
            result_type=dict,
        )
    except WorkflowFailureError as error:
        if isinstance(error.cause, TemporalTimeout):
            # A workflow step is automated: a workflow that waits, for a person or anything else,
            # breaks the promise (brief, D6).
            waited = (
                f"{contract.reference} didn't finish within its timeout of {contract.timeout}s: "
                "a workflow step must not wait for people"
            )
            return [waited]
        said = error.cause.message if isinstance(error.cause, FailureError) else str(error)
        return [f"{contract.reference} failed: {said}"]
    return output_problems(contract, output)


def output_problems(contract: WorkflowContract, output: dict[str, Any]) -> list[str]:
    """What is wrong with `output` against the contract: a field missing or of the wrong type, and
    each field it doesn't declare. A case drops an undeclared field; here it means the contract is
    out of date, which its owners should hear (8d, drafting 3)."""
    problems = []
    try:
        contract.output.model_validate(output)
    except ValidationError as error:
        problems.append(
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        )
    problems += [
        f"{contract.reference} gave {name}, which its contract doesn't declare"
        for name in output
        if name not in contract.output.model_fields
    ]
    return problems
