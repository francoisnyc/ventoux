"""A plan as a Temporal workflow: the same interpreter, with Temporal's activities, signals and
timers (layer 6).

A workflow only decides; Temporal replays it from its history after a crash, so it must ask for
the same things in the same order every time. The interpreter reads no clock, randomness or I/O
(`tests/test_layers.py`), and everything it asks for goes through `call` and `wait` below.
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.exceptions import ApplicationError

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run, to keep runs
# apart; modules passed through are imported once and shared. `core` is deterministic (the
# boundary test holds it to that), so it is shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.core.catalog import Catalog
    from ventoux.core.interpreter import Answer, RunRefused, interpret
    from ventoux.core.plan import PlanInvalid, parse_plan
    from ventoux.core.provenance import sourced


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
        raise NotImplementedError("activities come in the next slice")

    async def wait(
        self, state: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        raise NotImplementedError("waits come in a later slice")
