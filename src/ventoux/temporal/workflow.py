"""A plan as a Temporal workflow: the same interpreter, with Temporal's activities, signals and
timers (layer 6).

A workflow only decides; Temporal replays it from its history after a crash, so it must ask for
the same things in the same order every time. The interpreter reads no clock, randomness or I/O
(`tests/test_layers.py`), and everything it asks for goes through `call` and `wait` below.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, FailureError

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run, to keep runs
# apart; modules passed through are imported once and shared. `core` is deterministic (the
# boundary test holds it to that), so it is shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.core.catalog import Catalog
    from ventoux.core.interpreter import Answer, Outcome, RunRefused, interpret
    from ventoux.core.plan import PlanInvalid, parse_plan
    from ventoux.core.provenance import sourced
    from ventoux.temporal.activities import OUTCOME


@dataclass
class Given:
    """A field's value, and where it came from."""

    value: Any  # the value: a number (exact), a text, a boolean
    sources: list[str]  # where it came from, such as `system:orders` (brief, D12)


@dataclass
class PlanStart:
    """What a run starts with."""

    plan: dict[str, Any]  # the plan, as stored data
    fields: dict[str, Given]  # every field the plan declares, with its sources


@dataclass
class RunReport:
    """How a run went: what `run_plan` reports in memory."""

    status: str | None  # succeeded, failed, waiting or stopped; None while it runs
    reason: str | None  # why it stopped, if it did
    history: list[str]  # every event, one line each


class ActivityFailed(Exception):
    """An activity that still failed after the retries its contract allows."""


class PlanWorkflow:
    """The code of a plan workflow. A deployment subclasses it to name its catalog, and registers
    the subclass (Temporal's SDK wants `@workflow.run` on the class it registers):

        @workflow.defn(name="ventoux.plan")
        class RefundPlans(PlanWorkflow):
            catalog = CATALOG

            @workflow.run
            async def run(self, start: PlanStart) -> RunReport:
                return await self.interpret(start)
    """

    catalog: ClassVar[Catalog]  # the contracts this deployment's plans may call

    async def run(self, start: PlanStart) -> RunReport:
        return await self.interpret(start)

    async def interpret(self, start: PlanStart) -> RunReport:
        try:
            plan = parse_plan(start.plan)
            fields = {
                name: sourced(given.value, *given.sources) for name, given in start.fields.items()
            }
            run = await interpret(
                plan, fields, self.catalog, self.call, self.wait, run_name=self.name()
            )
        except (RunRefused, PlanInvalid) as refused:
            # A run that can't start fails at once, saying why. Any other exception fails only the
            # workflow task, which Temporal retries until fixed code is deployed (brief, D17).
            raise ApplicationError(str(refused), type="RunRefused", non_retryable=True) from None
        return RunReport(run.status, run.reason, [str(event) for event in run.history])

    def name(self) -> str:
        """This run's name in its idempotency keys: the workflow's ID and run ID (brief, D17)."""
        info = workflow.info()  # recorded in history, so the same on replay
        return f"{info.workflow_id}/{info.run_id}"

    async def call(self, reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Schedule the activity, retried and timed out as its contract says (brief, D17)."""
        contract = self.catalog.get(reference)
        # Temporal: the result is recorded in history; on replay it is read back, never called
        # again.
        try:
            output: dict[str, Any] = await workflow.execute_activity(
                reference,
                inputs,
                start_to_close_timeout=timedelta(seconds=contract.timeouts.start_to_close),
                schedule_to_start_timeout=timedelta(seconds=contract.timeouts.schedule_to_start),
                retry_policy=RetryPolicy(
                    maximum_attempts=contract.retry.maximum_attempts,
                    initial_interval=timedelta(seconds=contract.retry.initial_interval),
                    backoff_coefficient=contract.retry.backoff_coefficient,
                ),
                result_type=dict,
            )
        except ActivityError as error:
            # Past its retries: the interpreter stops the step (brief, D17), and its reason says
            # what the activity itself said, not "Activity task failed".
            cause = error.cause
            if isinstance(cause, ApplicationError) and cause.type == OUTCOME:
                raise Outcome(cause.message) from None  # read as in memory: `declined`
            raise ActivityFailed(cause.message if isinstance(cause, FailureError) else str(error))
        return output

    async def wait(
        self, state: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        raise NotImplementedError("waits come in a later slice")
