# Workflow classes for the p1c_* probes (imported afresh by Temporal's workflow sandbox, so kept apart from the harness).
"""Not a probe itself: `SwitchingCases` continues as new every 2 events; `ImpatientCases` gives up
its export after 2 tries. Each only lowers a bound `CaseWorkflow` documents as a class variable
"a test's workflow lowers"."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow

with workflow.unsafe.imports_passed_through():
    from ventoux.testing import CATALOG


# Temporal: a case workflow that continues as new after every 2 events (a deployment keeps 1000).
@workflow.defn(name="ventoux.case")
class SwitchingCases(CaseWorkflow):
    catalog = CATALOG
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


# Temporal: a case workflow whose export gives up after 2 tries, so a store that is down is
# said failed within a test (a deployment keeps 10).
@workflow.defn(name="ventoux.case")
class ImpatientCases(CaseWorkflow):
    catalog = CATALOG
    export_retries = RetryPolicy(
        maximum_attempts=2,
        maximum_interval=timedelta(seconds=1),
        non_retryable_error_types=["ExportRefused", "AuditRefused", "KeyRefused"],
    )

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


# Temporal: a deployment's case workflow in the environment `production`, whose registry each
# case asks as it opens (brief, D54).
@workflow.defn(name="ventoux.case")
class ProductionCases(CaseWorkflow):
    catalog = CATALOG
    environment = "production"

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)
