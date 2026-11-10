# Shared workflow classes for p2_time_travel.py: the classes the fixtures' tests replay with, written so that an older checkout of the code can import them too.
"""Not a probe itself. Each class is what the test that owns the fixture defines (tests/
test_temporal_approvals.py `EveryEventCases`, test_temporal_case.py `SwitchingCases`,
test_temporal_registry.py `ProductionCases`), repeated here because an older tree's tests don't
all hold them."""

from collections.abc import Mapping
from typing import Any, ClassVar

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow
    from ventoux.testing import CATALOG, DevelopmentCases, DevelopmentForget

    try:
        from ventoux.temporal.registry import RegistryWorkflow
    except ImportError:  # before 12e
        RegistryWorkflow = None  # type: ignore[assignment,misc]
    try:
        from ventoux.temporal.bindings import Binding
    except ImportError:
        Binding = None  # type: ignore[assignment,misc]


@workflow.defn(name="ventoux.case")
class EveryEventCases(CaseWorkflow):
    catalog = CATALOG
    events_per_run = 1

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class SwitchingCases(CaseWorkflow):
    catalog = CATALOG
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class ProductionCases(CaseWorkflow):
    catalog = CATALOG
    environment = "production"
    workflows: ClassVar[Mapping[str, Any]] = (
        {} if Binding is None else {"kyc.check@1": Binding(workflow="KycCheck", task_queue="kyc")}
    )

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class SwitchesSooner(CaseWorkflow):
    """The development cases, as a deployment that lowered the count would run them
    (p2_class_settings_decide_replay.py)."""

    catalog = CATALOG
    events_per_run = 2  # the default is 1000

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class HoldsSooner(CaseWorkflow):
    catalog = CATALOG
    audit_bound = 1024  # the default is 256 KB

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


__all__ = [
    "DevelopmentCases", "DevelopmentForget", "EveryEventCases", "HoldsSooner", "ProductionCases",
    "RegistryWorkflow", "SwitchesSooner", "SwitchingCases",
]
