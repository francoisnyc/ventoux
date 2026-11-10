# Shows five places where an outsider following the guides' own snippets gets something other than what the guide says (run_case under the wrong catalog, start_case given the builder's Case, environment_worker without audit=, report() just after start_case on a release, report() on a closed case's handle).
"""Run from the repository root: uv run python reviews/2026-11/probes/p5_first_hour_surprises.py

The project files (an equipment loan, its own catalog) are the ones in p5_own_case.py, read from
that file without running it. Temporal is its local development server, started by Temporal's own
`WorkflowEnvironment.start_local`.
"""
import ast
import asyncio
import inspect
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

SOURCE = ast.parse(Path("reviews/2026-11/probes/p5_own_case.py").read_text())
TEXTS = {
    node.targets[0].id: ast.literal_eval(node.value)
    for node in SOURCE.body
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
}
PROD_PY = '''
from temporalio import workflow
from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow
from loans.catalog import CATALOG


@workflow.defn(name="ventoux.case")
class LoanCasesInEnvironment(CaseWorkflow):
    catalog = CATALOG
    environment = "trial"

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)
'''
VENTOUX = str(Path(sys.executable).parent / "ventoux")
found: list[str] = []


def in_memory(folder: Path) -> None:
    from cases.loan import loan
    from loans.catalog import reserve
    from ventoux.testing import run_case

    # 1. The cases guide's "Testing a case" lists run_case's parameters and never names `catalog`.
    try:
        run_case(loan, file={"item": "projector", "days": 3},
                 answers=[("assess", "accept", "dee", {"deposit": 50})],
                 people={"dee": ["desk"]}, activities={"inventory.reserve@1": reserve})
        print("1. run_case without catalog=: ran")
    except Exception as error:
        print(f"1. run_case without catalog=: {type(error).__name__}: {error}")
        if "dee has no role" in str(error):
            found.append("run_case checks a case written for the project's catalog against the development "
                         "catalog, and says 'dee has no role' although people= gives dee the role desk")


async def on_temporal(folder: Path) -> None:
    from temporalio.testing import WorkflowEnvironment

    from cases.loan import loan
    from loans.catalog import reserve
    from loans.prod import LoanCasesInEnvironment
    from loans.workflows import LoanCases, LoanPlans
    from ventoux.temporal.cases import answer, report, start_case
    from ventoux.temporal.converter import data_converter
    from ventoux.temporal.manifests import environment_worker
    from ventoux.temporal.registry import registry_worker  # not in public.json: releases guide names it, no import
    from ventoux.temporal.worker import case_worker
    from ventoux.tooling.audit import FileAudit
    from ventoux.tooling.keys import FileKeys
    from ventoux.tooling.releases import FolderStore

    keys = FileKeys(str(folder / "keys.json"))
    store = FileAudit(str(folder / "audit"))
    code = {"inventory.reserve@1": reserve}
    async with await WorkflowEnvironment.start_local(data_converter=data_converter(keys)) as env:
        client = env.client
        address = ["--address", client.service_client.config.target_host]
        with ThreadPoolExecutor() as executor:
            # 2. The cases guide: start_case(client, RefundCases, refund, ...), `refund` never said to be the JSON.
            try:
                await start_case(client, LoanCases, loan, file={"item": "projector", "days": Decimal("3")},
                                 id="loan-a", task_queue="loans")
                print("2. start_case with the builder's Case: started")
            except Exception as error:
                print(f"2. start_case with the builder's Case: {type(error).__name__}: {error}")
                if isinstance(error, AttributeError):
                    found.append("start_case given the builder's Case (which run_case accepts) raises a bare "
                                 "AttributeError, after spending the case's ID")

            # 3. The releases guide's environment_worker(...) call has no audit=.
            parameter = inspect.signature(environment_worker).parameters["audit"]
            print(f"3. environment_worker's audit parameter has a default: {parameter.default is not parameter.empty}")
            if parameter.default is parameter.empty:
                found.append("environment_worker as the releases guide calls it (no audit=) is a TypeError: "
                             "audit is required")

            # 4. The cases guide: `now = await report(case); assert (now.release, now.engine) == ("refund 1", 3)`.
            subprocess.run([VENTOUX, "release", "packages/loan", "--releases", "releases", "--commit", "4f2a9c1"],
                           cwd=folder, check=True, capture_output=True)
            async with registry_worker(client):
                made = subprocess.run([VENTOUX, "environment", "create", "trial", "--development", *address],
                                      cwd=folder, capture_output=True, text=True)
                print("  ", made.stdout.strip() or made.stderr.strip())
                worker = await environment_worker(client, "loans-trial", LoanCasesInEnvironment, LoanPlans, code,
                                                  build="4f2a9c1", identity="loans-a",
                                                  activity_executor=executor, audit=store)
                async with worker:
                    activated = await asyncio.to_thread(
                        subprocess.run,
                        [VENTOUX, "activate", "loan", "1", "--environment", "trial", "--task-queue",
                         "loans-trial", "--releases", "releases", "--by", "pia", *address],
                        cwd=folder, capture_output=True, text=True)
                    print("  ", activated.stdout.strip() or activated.stderr.strip())
                    loan_1 = FolderStore(folder / "releases").get("loan", 1)
                    case = await start_case(client, LoanCasesInEnvironment, loan_1,
                                            file={"item": "projector", "days": Decimal("3")},
                                            id="loan-b", task_queue="loans-trial")
                    first = await report(case)
                    print(f"4. report just after start_case on release loan 1: release={first.release!r} "
                          f"waiting_at={first.waiting_at} history={first.history}")
                    for _ in range(50):
                        later = await report(case)
                        if later.waiting_at:
                            break
                        await asyncio.sleep(0.2)
                    print(f"   a moment later: release={later.release!r} waiting_at={later.waiting_at}")
                    if first.release != "loan 1" and later.release == "loan 1":
                        found.append(f"report() just after start_case on a release says release={first.release!r} "
                                     "with an empty history, where the guide asserts the release at once")

            # 5. report() on a handle from the Temporal client: one type while open, another once closed.
            definition = json.loads((folder / "packages/loan/case.json").read_text())
            async with case_worker(client, "loans", LoanCases, LoanPlans, code, activity_executor=executor,
                                   audit=store):
                await start_case(client, LoanCases, definition, file={"item": "projector", "days": Decimal("3")},
                                 id="loan-c", task_queue="loans")
                handle = client.get_workflow_handle("loan-c")
                while_open = type(await report(handle)).__name__
                await answer(handle, "assess#1", "refuse", by="dee", roles=["desk"])
                await handle.result()
                once_closed = type(await report(handle)).__name__
                print(f"5. report(client.get_workflow_handle(id)): {while_open} while open, {once_closed} once closed")
                if while_open != once_closed:
                    found.append(f"report() gives a {while_open} while the case is open and a plain {once_closed} "
                                 "once it has closed, on the same handle")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name in ("loans", "cases"):
            (folder / name).mkdir()
        (folder / "loans/__init__.py").write_text("")
        (folder / "loans/catalog.py").write_text(TEXTS["CATALOG_PY"])
        (folder / "loans/workflows.py").write_text(TEXTS["WORKFLOWS_PY"])
        (folder / "loans/prod.py").write_text(PROD_PY)
        (folder / "cases/loan.py").write_text(TEXTS["CASE_PY"])
        (folder / "pyproject.toml").write_text(TEXTS["PYPROJECT"])
        subprocess.run([VENTOUX, "check"], cwd=folder, check=True, capture_output=True)
        sys.path.insert(0, str(folder))
        in_memory(folder)
        asyncio.run(on_temporal(folder))
    print()
    for line in found:
        print("-", line)
    if found:
        print(f"RESULT: BROKEN - {len(found)} of 5 guide snippets behave otherwise than the guide says")
    else:
        print("RESULT: HELD - the five snippets behave as the guides say")


main()
