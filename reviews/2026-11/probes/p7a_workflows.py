# The case workflow for p7a_validator_message_on_temporal.py: the catalog of p3_validator_message_in_history.py, served on Temporal (imported afresh by Temporal's workflow sandbox, so kept apart from the probe).
"""Not a probe itself. A deployment's case workflow names its own catalog, as `DevelopmentCases`
names the development one; this one names the in-memory probe's catalog, whose two contracts'
models carry a validator that quotes the value it refuses."""

import contextlib
import io

from temporalio import workflow

from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow

# Temporal: modules imported here are the worker's own, not copies made for the sandbox. The
# in-memory probe runs as it is imported; what it prints is dropped.
with workflow.unsafe.imports_passed_through(), contextlib.redirect_stdout(io.StringIO()):
    import p3_validator_message_in_history as in_memory


@workflow.defn(name="ventoux.case")
class ValidatedCases(CaseWorkflow):
    catalog = in_memory.catalog

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)
