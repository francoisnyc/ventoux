# Shows whether `core` and `case` import no Temporal or LLM library, whether anything in src/ can run code a definition names, and whether D27's key format, D31's "no `/` in a case ID" and D41's refused event on a closing case are what the code does.
import asyncio
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from ventoux.testing import close, finish, run_case, send

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "ventoux"
ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:360], agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:170]


# CLAUDE.md: core and case free of Temporal and LLM dependencies, by a run in a clean interpreter.
modules = sorted(".".join(path.relative_to(SRC.parent).with_suffix("").parts) for folder in ("core", "case") for path in (SRC / folder).rglob("*.py"))
modules = [name.removesuffix(".__init__") for name in modules]
script = "import importlib, sys\nfor name in %r:\n    importlib.import_module(name)\nprint(sorted(m for m in sys.modules if m.split('.')[0] in ('temporalio', 'anthropic', 'httpx', 'openai')))" % modules
done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=300)
row("CLAUDE.md", "'Keep ventoux.core and ventoux.case free of Temporal and LLM dependencies'", f"{len(modules)} modules imported in a fresh interpreter; such libraries loaded: {done.stdout.strip() or done.stderr[-200:]}", done.stdout.strip() == "[]")
script = "import sys\nimport ventoux.temporal.cases, ventoux.temporal.workflow, ventoux.temporal.worker, ventoux.temporal.forget\nprint(sorted(m for m in sys.modules if m.split('.')[0] == 'anthropic' or m.startswith('ventoux.authoring')))"
done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=300)
row("D62", "'No module of temporal imports authoring or an LLM SDK'", done.stdout.strip() or done.stderr[-200:], done.stdout.strip() == "[]")

# CLAUDE.md: never eval, exec, compile, importlib or pickle anything from a definition.
WORDS = re.compile(r"\b(eval|exec|compile)\(|\bimportlib\b|__import__|\bpickle\b|\bmarshal\b|yaml\.load|\bsubprocess\b|os\.system|\brunpy\b")
hits = []
for path in sorted(SRC.rglob("*.py")):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        code = line.split("#", 1)[0]
        if WORDS.search(code) and "re.compile(" not in code:
            hits.append(f"{path.relative_to(SRC)}:{number}: {code.strip()}")
# Each place read by hand: what decides the name that is imported or the file that is run.
EXPLAINED = {
    "__init__.py": "imports the fixed module ventoux.tooling.builder, for a name Python code asks of the package",
    "tooling/check.py": "runs the builder files named on the command line or found in the configured cases folder: the team's code (D59)",
    "tooling/deployment.py": "imports the catalog, key service or audit store by the name in pyproject.toml or --catalog (D59, D81)",
    "tooling/cli.py": "importlib.metadata, to read the installed package's version",
}
unexplained = [hit for hit in hits if not any(hit.startswith(name + ":") for name in EXPLAINED)]
row("CLAUDE.md", "'Never eval, exec, compile, importlib or pickle anything from them [definitions]'", f"{len(hits)} lines in src/ use such a name, in {sorted({hit.split(':')[0] for hit in hits})}; in a file not read and explained: {unexplained}", not unexplained)
in_pure = [hit for hit in hits if hit.startswith(("core/", "case/", "temporal/", "authoring/"))]
row("CLAUDE.md", "... and none of them is in core, case, temporal or authoring, where definitions, stories, drafts and records are read", in_pure, not in_pure)

# D27: the key's form.
package = ROOT / "examples" / "packages" / "refund"
case = json.loads((package / "case.json").read_text(), parse_float=Decimal)
plan = json.loads((package / "plans" / "refund-order.json").read_text(), parse_float=Decimal)
kind, run = attempt(lambda: run_case(case, {"order_id": "ord-1", "amount": Decimal(40)}, [("review", "approve", "ana", {"approved_amount": Decimal(40)})],
                                     {"ana": ["support"], "sam": ["support-lead"]}, plans={"refund-order@1": plan}))
started = [line for line in (run.history if kind == "ok" else []) if line.startswith("started settle#1")]
row("D27", "'A plan step's keys add its own: <case key>/collect#1/pay#1' (in memory the case key is `memory`; only the plan run's own name is shown here, its activities' keys are pass 1c's probe)", started or run, kind == "ok" and any(line.endswith("run memory/settle#1") for line in started))
source = (SRC / "temporal" / "cases.py").read_text()
row("D27", "'<workflow ID>/<first run ID>/<entry>' (read in temporal/cases.py: no run without a server)", [line.strip() for line in source.splitlines() if "first_execution_run_id" in line][:2], 'f"{info.workflow_id}/{info.first_execution_run_id}"' in source)

# D31: a case ID has no `/`: refused by the client before anything is asked of Temporal.
from ventoux.temporal.cases import CaseWorkflow, start_case  # noqa: E402
from ventoux.temporal.client import start_plan  # noqa: E402
from ventoux.temporal.workflow import PlanWorkflow  # noqa: E402


class NoClient:  # anything asked of it fails: the refusal must come first
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the client was asked for {name}")


from ventoux.tooling.keys import FileKeys  # noqa: E402
import tempfile  # noqa: E402
import ventoux.temporal.cases as cases_module  # noqa: E402
import ventoux.temporal.client as client_module  # noqa: E402

with tempfile.TemporaryDirectory() as temporary:
    keys = FileKeys(Path(temporary) / "keys.json")
    cases_module.keys_of = lambda client: keys  # the probe's stand-in for the client's key provider
    client_module.keys_of = lambda client: keys
    kind, shown = attempt(lambda: asyncio.run(start_case(NoClient(), CaseWorkflow, case, {"order_id": "ord-1", "amount": Decimal(40)}, "claim-7/repair#1", "queue")))
    made = (Path(temporary) / "keys.json").exists() and "claim-7" in (Path(temporary) / "keys.json").read_text()
    row("D31", "'a case ID has no /' (start_case)", f"{kind}: {shown}; a key was made: {made}", kind == "ValueError" and not made)
    kind, shown = attempt(lambda: asyncio.run(start_plan(NoClient(), PlanWorkflow, plan, {}, "run-1/x", "queue")))
    row("D31", "'a case ID has no /' (start_plan)", f"{kind}: {shown}", kind == "ValueError")

# D41: a closing case refuses an event, records and flags it.
witness = json.loads((ROOT / "examples" / "witnesses" / "listening.json").read_text(), parse_float=Decimal)
witness["close_reasons"] = {"duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}}
kind, run = attempt(lambda: run_case(witness, {"order_id": "ord-1", "amount": Decimal(40)},
                                     [("review", "approve", "ana", {"approved_amount": Decimal(40)}), close("duplicate", "ana"), send("noted", {}, "system:portal")],
                                     {"ana": ["support"]}, held=["pay"]))
if kind != "ok":
    kind, run = attempt(lambda: run_case(witness, {"order_id": "ord-1", "amount": Decimal(40)},
                                         [("review", "approve", "ana", {"approved_amount": Decimal(40)}), close("duplicate", "ana"), send("noted", {}, "portal")],
                                         {"ana": ["support"]}, held=["pay"]))
if kind == "ok":
    lines = [line for line in run.history if line.startswith("refused noted")]
    row("D41", "'While the case is closing, an event is refused, recorded and flagged'", f"status {run.status}; history: {lines}; flags: {run.flags}", run.status == "closing" and bool(lines) and any("noted" in flag for flag in run.flags))
else:
    row("D41", "'While the case is closing, an event is refused, recorded and flagged'", f"{kind}: {run}", False)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
