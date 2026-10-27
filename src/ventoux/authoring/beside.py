"""The step advisor beside a running case: it reads by query and never signals (brief, D62).

What it is shown is computed in the worker, and each answer is checked by admission there, on a
copy of the case's state. Only a person's proposal, made after, reaches the case (brief, D61).
"""

from typing import Any

from temporalio.client import WorkflowHandle

from ventoux.authoring.advisor import Advice, Shown, advise
from ventoux.authoring.provider import Provider
from ventoux.temporal.cases import refused_proposal, shown_to_advisor


async def advise_case(
    case: WorkflowHandle[Any, Any], by: str, roles: list[str], provider: Provider, at: int
) -> Advice:
    """What `provider`'s model suggests to `by`, who has `roles`, on the running `case` at
    `at`. Queries only: nothing is decided, and nothing is recorded in the case's history."""
    shown = Shown.of(await shown_to_advisor(case, by, roles, at))

    async def refused(step: str) -> str | None:
        return await refused_proposal(case, step, by, roles, at)

    return await advise(shown, provider, refused)
