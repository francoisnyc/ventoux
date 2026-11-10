# Shows whether an outsider can take a case of their own (an equipment loan) through opening, a step, a wait for a person, an approval and closing, in memory and on Temporal, and which names outside public.json that needed.
"""Run from the repository root: uv run python reviews/2026-11/probes/p5_own_case.py

The project is written to a temporary folder as a newcomer would lay it out (loans/catalog.py,
loans/workflows.py, cases/loan.py, pyproject.toml), checked with `ventoux check`, played in memory,
then run on Temporal's local development server (Temporal's own `WorkflowEnvironment.start_local`).
Names used that are NOT in src/ventoux/public.json are listed at the end.
"""
import asyncio
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

CATALOG_PY = r"""from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel

from ventoux.core.catalog import Catalog  # GUESSED: no guide shows where Catalog comes from
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.policy import trusted_only


class ReserveInput(BaseModel):
    item: str
    deposit: Annotated[Decimal, trusted_only()]
    idempotency_key: str


class ReserveOutput(BaseModel):
    reservation_id: str


inventory_reserve = ActivityContract(
    name="inventory.reserve",
    version=1,
    input=ReserveInput,
    output=ReserveOutput,
    risk="high",
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=["unavailable"],
    display=Display(
        title="Reserve an item",
        description="Reserves an item of equipment in the inventory.",
        outcomes={"unavailable": "The item is not available"},
    ),
)

CATALOG = Catalog()
CATALOG.register(inventory_reserve)
CATALOG.register_role("desk")
CATALOG.register_role("manager", approves="high")
PLANS = {}
RESERVED = []


def reserve(inputs):
    RESERVED.append(inputs)
    return {"reservation_id": "res-1"}
"""
WORKFLOWS_PY = r"""from temporalio import workflow

from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow
from ventoux.temporal.workflow import PlanStart, PlanWorkflow, RunReport
from loans.catalog import CATALOG, PLANS


@workflow.defn(name="ventoux.plan")
class LoanPlans(PlanWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: PlanStart) -> RunReport:
        return await self.interpret(start)


@workflow.defn(name="ventoux.case")
class LoanCases(CaseWorkflow):
    catalog = CATALOG
    plans = PLANS

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)
"""
CASE_PY = r"""from ventoux import Approval, Case, Field, Outcome

loan = Case("loan", title="Equipment loan")

item = loan.field("item", Field.string(), title="Item")
days = loan.field("days", Field.number(), title="Days asked for")
deposit = loan.field("deposit", Field.number(), title="Deposit")

assessed = loan.milestone("assessed", title="Request assessed")
reserved = loan.milestone("reserved", title="Item reserved")

assess = loan.task(
    "assess",
    title="Assess the loan request",
    roles=["desk"],
    outcomes={
        "accept": Outcome("Accept the loan", sets=[deposit], reaches=[assessed]),
        "refuse": Outcome("Refuse the loan"),
    },
)

reserve = loan.activity(
    "reserve",
    "inventory.reserve@1",
    title="Reserve the item",
    inputs={"item": item, "deposit": deposit},
    when=assess.outcome == "accept",
    approval=Approval(roles=["manager"], reason="A reservation needs a manager"),
    reaches=[reserved],
)

loan.sequence(assess, reserve)

tell = loan.task(
    "tell_borrower",
    title="Tell the borrower the item is unavailable",
    roles=["desk"],
    requires=[reserve],
    when=reserve.outcome == "unavailable",
    outcomes={"told": Outcome("Borrower told")},
)
"""
PYPROJECT = '[project]\nname = "loans"\nversion = "0.0.0"\n\n[tool.ventoux]\ncatalog = "loans.catalog:CATALOG"\n'

OUTSIDE = [
    "ventoux.core.catalog.Catalog (no guide shows an import for it; guessed)",
    "ventoux.testing.run_case (docs/QUICKSTART.md line 149 imports it; public.json lists only run_plan and check_workflow_contract under ventoux.testing)",
]


async def on_temporal(folder: Path) -> list[str]:
    from temporalio.testing import WorkflowEnvironment

    from loans.catalog import reserve
    from loans.workflows import LoanCases, LoanPlans
    from ventoux.temporal.cases import answer, report, start_case
    from ventoux.temporal.converter import data_converter
    from ventoux.temporal.worker import case_worker
    from ventoux.tooling.audit import FileAudit, read_audit
    from ventoux.tooling.keys import FileKeys

    seen: list[str] = []
    keys = FileKeys(str(folder / "keys.json"))
    store = FileAudit(str(folder / "audit"))
    loan = json.loads((folder / "packages/loan/case.json").read_text())
    async with await WorkflowEnvironment.start_local(data_converter=data_converter(keys)) as env:
        with ThreadPoolExecutor() as executor:
            worker = case_worker(env.client, "loans", LoanCases, LoanPlans,
                                 {"inventory.reserve@1": reserve}, activity_executor=executor,
                                 audit=store)
            async with worker:
                case = await start_case(env.client, LoanCases, loan,
                                        file={"item": "projector", "days": Decimal("3")},
                                        id="loan-1", task_queue="loans")
                seen.append(f"opened: waiting at {(await report(case)).waiting_at}")
                await answer(case, "assess#1", "accept", by="max", roles=["desk", "manager"],
                             form={"deposit": Decimal("50")})
                seen.append(f"after the task: waiting at {(await report(case)).waiting_at}")
                await answer(case, "reserve.approval#1", "approve", by="max", roles=["desk", "manager"])
                now = await report(case)
                seen.append(f"same person approves: {now.history[-1]}")
                assert now.waiting_at == ["reserve.approval#1"], now.waiting_at
                assert "refused max" in now.history[-1], now.history[-1]
                await answer(case, "reserve.approval#1", "approve", by="lee", roles=["manager"])
                final = await case.result()
                seen.append(f"closed: {final.status}; last line: {final.history[-1]}")
                assert final.status == "closed"
                assert "reached reserved" in final.history
    records = list(read_audit(store, "loan-1", roles=["desk"], keys=keys))
    seen.append(f"audit export: {[(r['number'], r['act']['kind']) for r in records]}")
    assert records and records[-1]["act"]["kind"] == "completed"
    return seen


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "loans").mkdir()
        (folder / "cases").mkdir()
        (folder / "loans/__init__.py").write_text("")
        (folder / "loans/catalog.py").write_text(CATALOG_PY)
        (folder / "loans/workflows.py").write_text(WORKFLOWS_PY)
        (folder / "cases/loan.py").write_text(CASE_PY)
        (folder / "pyproject.toml").write_text(PYPROJECT)
        ventoux = str(Path(sys.executable).parent / "ventoux")
        check = subprocess.run([ventoux, "check"], cwd=folder, capture_output=True, text=True)
        print("ventoux check:", check.stdout.strip(), check.stderr.strip())
        if check.returncode != 0:
            print("RESULT: BROKEN - ventoux check refused the outsider's own case")
            return
        sys.path.insert(0, str(folder))
        try:
            from loans.catalog import CATALOG, reserve
            from ventoux.testing import run_case

            definition = json.loads((folder / "packages/loan/case.json").read_text())
            people = {"dee": ["desk"], "max": ["desk", "manager"]}
            run = run_case(definition, file={"item": "projector", "days": 3},
                           answers=[("assess", "accept", "dee", {"deposit": 50}),
                                    ("reserve", "approve", "max")],
                           people=people, activities={"inventory.reserve@1": reserve}, catalog=CATALOG)
            print("in memory: closed", run.closed, "reached reserve", run.reached("reserve"))
            assert run.closed and run.reached("reserve")
            for line in asyncio.run(on_temporal(folder)):
                print("on Temporal:", line)
        except Exception as error:  # the probe reports, whatever broke
            print(f"RESULT: BROKEN - {type(error).__name__}: {error}")
            return
    print("names needed outside public.json:")
    for name in OUTSIDE:
        print("  -", name)
    print("RESULT: HELD - an outsider's own case opens, runs a step, waits for a person, refuses the "
          "same person's approval, takes another's and closes, in memory and on Temporal; but it "
          f"needed {len(OUTSIDE)} names outside public.json (listed above)")


main()
