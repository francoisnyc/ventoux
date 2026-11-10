# Shows, claim by claim, whether D58 (the builder's refusals, the same JSON byte for byte), D60 (the published schemas: $id, unknown keys, the four readings refused) and D79 (the client functions it names) are what the code does.
import copy
import importlib
import json
import runpy
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux import Approval, Case, Field, Outcome, literal
from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.case.engine import ENGINE  # not public: this code's engine version
from ventoux.core.plan import parse_plan  # not public
from ventoux.tooling.builder.written import package, written  # not public: what `ventoux check` writes with

ROWS: list[tuple[str, str, str, bool]] = []
# The `ventoux` command, as its entry point runs it (`ventoux.tooling.cli:main`), on this interpreter.
VENTOUX = [sys.executable, "-c", "import sys; from ventoux.tooling.cli import main; sys.exit(main())"]


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:430], agrees))


def attempt(action: Any) -> tuple[str, str]:
    try:
        return "ok", " ".join(str(action()).split())[:150]
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:170]


def small() -> tuple[Case, Any, Any]:
    case = Case("probe", title="Probe")
    amount = case.field("amount", Field.number(), title="Amount")
    flag = case.field("flag", Field.boolean(), title="Flag") if hasattr(Field, "boolean") else None
    return case, amount, flag


# D58
case, amount, flag = small()
asked = {
    "an if": lambda: 1 if amount > 1 else 0,
    "and": lambda: (amount > 1) and (amount < 5),
    "or": lambda: (amount > 1) or (amount < 5),
    "not": lambda: not (amount > 1),
    "a chained comparison": lambda: 1 < amount < 5,
    "bool()": lambda: bool(amount == 1),
}
results = {name: attempt(action) for name, action in asked.items()}
row("D58", "'Asking an Expr for a bool (an if, and, or, not, a chained comparison) raises'", {name: kind for name, (kind, _) in results.items()} | {"says": results["an if"][1]},
    all(kind != "ok" for kind, _ in results.values()))
numbers = {
    "amount > 1.5": lambda: amount > 1.5, "amount + 1.5": lambda: amount + 1.5, "literal(1.5)": lambda: literal(1.5),  # type: ignore[call-overload]
    "amount > True": lambda: amount > True, "amount + True": lambda: amount + True, "amount == True": lambda: amount == True,  # noqa: E712
    "amount > 2": lambda: amount > 2, "amount > Decimal('2.5')": lambda: amount > Decimal("2.5"),
}
results = {name: attempt(action)[0] for name, action in numbers.items()}
row("D58", "'Numbers are int or Decimal, never float and never bool'", results, all((kind == "ok") == (name in ("amount > 2", "amount > Decimal('2.5')")) for name, kind in results.items()))


def with_when(when: Any) -> str:
    case = Case("probe", title="Probe")
    case.task("review", title="Review", roles=["support"], when=when, outcomes={"done": Outcome("Done")})
    return written(case)


for value in (True, 250, "yes", None):
    kind, shown = attempt(lambda: json.loads(with_when(value))["steps"]["review"].get("when", "<no when key>"))
    read = attempt(lambda: parse_case(json.loads(with_when(value), parse_float=Decimal)).steps["review"].when)[0] if kind == "ok" else "-"
    row("D58", f"ASKED: 'the parameter is typed Expr, so a plain True or 250 fails the type check': and at run time, when={value!r}?", f"the builder: {kind}: {shown}; the engine reads what it wrote: {read}", True)

for source, folder in (("examples/quickstart/cases/refund.py", "examples/quickstart/packages/refund"), ("examples/cases/refund.py", "examples/packages/refund")):
    built = runpy.run_path(source)["refund"]
    files = package(built)
    committed = {str(path.relative_to(folder)): path.read_text() for path in Path(folder).rglob("*.json")}
    row("D58", f"'The same JSON, byte for byte' ({source} against {folder}/)", f"written: {sorted(files)}; committed: {sorted(committed)}; equal: {files == committed}", files == committed)
done = subprocess.run([*VENTOUX, "check", "--unchanged"], cwd="examples/quickstart", capture_output=True, text=True)
row("D58", "'CI writes the JSON again and fails on any difference' (`ventoux check --unchanged` in examples/quickstart)", f"exit {done.returncode}: {(done.stdout + done.stderr).strip().splitlines()[-1:]}", done.returncode == 0)

text = written(runpy.run_path("examples/quickstart/cases/refund.py")["refund"])
row("D58", "'One layout, the standard library's indent=2 ... a key at its default left out unless given'", f"equal to json.dumps(json.loads(text), indent=2) + newline: {text == json.dumps(json.loads(text), indent=2) + chr(10)}; 'automatic' written: {'automatic' in text}",
    "automatic" not in text and text.rstrip("\n") == json.dumps(json.loads(text), indent=2))
unreadable = {"Decimal('NaN')": Decimal("NaN"), "Decimal('Infinity')": Decimal("Infinity"), "Decimal('1E+7000')": Decimal("1E+7000"), "Decimal('1E+3')": Decimal("1E+3"), "Decimal('-0')": Decimal("-0")}
results = {}
for name, value in unreadable.items():
    def build(value: Any = value) -> str:
        case = Case("probe", title="Probe")
        amount = case.field("amount", Field.number(), title="Amount")
        note = case.field("note", Field.string(), title="Note")
        when = (note == value) if isinstance(value, str) else (amount > value)
        case.task("review", title="Review", roles=["support"], when=when, outcomes={"done": Outcome("Done")})
        return written(case)
    results[name] = attempt(build)
row("D58", "'a value that doesn't read back the same is refused'", {name: f"{kind}: {said[:70]}" for name, (kind, said) in results.items()}, all(kind not in ("ok", "AttributeError") for kind, _ in results.values()))
def surrogate() -> str:
    case = Case("probe", title="Probe")
    note = case.field("note", Field.string(), title="Note")
    case.task("review", title="Review", roles=["support"], when=note == "\ud800", outcomes={"done": Outcome("Done")})
    return written(case)
kind, _ = attempt(surrogate)
encoded = attempt(lambda: len(surrogate().encode("utf-8")))
row("D58", "(a text holding a lone surrogate can't be written to a UTF-8 file, so it can't read back: what the builder's `written` does with it)", f"written(): {kind}; its text as UTF-8: {encoded[0]}: {encoded[1][:70]}", True)
with tempfile.TemporaryDirectory() as folder:
    project = Path(folder)
    (project / "cases").mkdir()
    (project / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n')
    (project / "cases" / "odd.py").write_text(
        'from ventoux import Case, Field, Outcome\n\nodd = Case("odd", title="Odd")\nnote = odd.field("note", Field.string(), title="Note")\n'
        'odd.task("review", title="Review", roles=["support"], when=note == "\\ud800", outcomes={"done": Outcome("Done")})\n')
    done = subprocess.run([*VENTOUX, "check"], cwd=project, capture_output=True, text=True)
    last = (done.stdout + done.stderr).strip().splitlines()[-1:]
    left = {str(path.relative_to(project)): path.stat().st_size for path in project.rglob("*.json")}
    row("D58", "MINOR: 'a value that doesn't read back the same is refused' (`ventoux check` on a case whose condition holds a lone surrogate: a refusal saying what is wrong, or a traceback?)",
        f"exit {done.returncode}; a traceback: {'Traceback' in done.stderr}; last line: {last}; files left: {left}", "Traceback" not in done.stderr)
done = subprocess.run([sys.executable, "-c", "import sys; from ventoux import Case, Field, Approval, package, written; import ventoux.tooling.builder; print(sorted(m for m in sys.modules if m.split('.')[0] == 'temporalio')[:3])"], capture_output=True, text=True)
row("D58", "'It lives in tooling, its names re-exported from ventoux, and imports no Temporal'", f"temporalio modules loaded after `from ventoux import Case, ...`: {done.stdout.strip() or done.stderr.strip()[-200:]}", done.stdout.strip() == "[]")
four_eyes = Case("probe", title="Probe")
order = four_eyes.reference("order_id", system="orders", title="Order")
paid = four_eyes.field("paid", Field.number(), title="Paid")
four_eyes.activity("pay", "payments.refund@2", title="Pay", inputs={"order_id": order, "amount": paid}, approval=Approval(count=2, roles=["support-lead"], reason="Two people"))
row("D58", "'four_eyes is Approval(count=2)'", json.loads(written(four_eyes))["steps"]["pay"]["approval"], json.loads(written(four_eyes))["steps"]["pay"]["approval"].get("count") == 2)

# D60
schemas = {name: json.loads(Path(f"src/ventoux/schema/{name}.schema.json").read_text()) for name in ("case", "plan")}
ids = {name: schema.get("$id") for name, schema in schemas.items()}
row("D60", f"'Named by the engine version that parses the format, in each schema's $id: https://ventoux.dev/schema/engine-N/case.schema.json' (this code's engine is {ENGINE})", ids,
    ids == {name: f"https://ventoux.dev/schema/engine-{ENGINE}/{name}.schema.json" for name in schemas})
row("D60", "'JSON Schema draft 2020-12'", {name: schema.get("$schema") for name, schema in schemas.items()}, all("2020-12" in str(schema.get("$schema")) for schema in schemas.values()))
row("D60/D82", "'schema/case.schema.json ... and schema/plan.schema.json' (D60), 'the schemas moving from schema/ at the root to src/ventoux/schema/' (D82)", f"schema/ exists at the repository's root: {Path('schema').exists()}; src/ventoux/schema/ holds {sorted(p.name for p in Path('src/ventoux/schema').glob('*.json'))}",
    not Path("schema").exists() and len(list(Path("src/ventoux/schema").glob("*.json"))) == 2)


def open_objects(node: Any, path: str = "") -> list[str]:
    """Every object schema that declares properties and doesn't refuse an unknown key."""
    found: list[str] = []
    if isinstance(node, dict):
        if "properties" in node and node.get("additionalProperties") is not False:
            found.append(path or "<root>")
        for key, value in node.items():
            found += open_objects(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += open_objects(value, f"{path}/{index}")
    return found


extras = {name: open_objects(schema) for name, schema in schemas.items()}
row("D60", "'They describe the JSON as written: every key, with an unknown key refused' (object schemas with properties and no additionalProperties: false)", extras, extras == {"case": [], "plan": []})
done = subprocess.run([*VENTOUX, "schema", "--unchanged"], capture_output=True, text=True)
row("D60", "'ventoux schema --unchanged ... regenerates and compares them byte for byte'", f"exit {done.returncode}: {(done.stdout + done.stderr).strip().splitlines()[-1:]}", done.returncode == 0)

REFUND = json.loads(Path("examples/refund/refund.json").read_text(), parse_float=Decimal)
PLAN = json.loads(Path("docs/guides/plans.md").read_text().split("```json\n")[1].split("```")[0], parse_float=Decimal)
readings: dict[str, str] = {}
for version in ("1", Decimal("1.0"), True):
    readings[f"plan version {version!r}"] = attempt(lambda: parse_plan({**copy.deepcopy(PLAN), "version": version}))[0]
listed = copy.deepcopy(REFUND)
listed["fields"]["lines"] = {"type": "list", "display": {"title": "Lines"}, "fields": {"sku": {}}}
readings["a list's field with no type"] = attempt(lambda: parse_case(listed))[0]
for key, where in (("automatic", ("steps", "review")), ("repeatable", ("steps", "review")), ("sensitive", ("fields", "amount")), ("stays_open", ())):
    for value in ("no", "on", Decimal("1.0"), 1, 0):
        changed = copy.deepcopy(REFUND)
        node = changed
        for part in where:
            node = node[part]
        node[key] = value
        readings[f"{key}: {value!r}"] = attempt(lambda: parse_case(changed))[0]
accepted = sorted(name for name, kind in readings.items() if kind == "ok")
row("D60", "'14e refused four such readings: a plan's version written as \"1\", 1.0 or true; a list's field with no type; a boolean (automatic, repeatable, sensitive, stays_open) written as a word or a number'",
    f"{len(readings)} readings tried; accepted: {accepted}", accepted == [])
tests = Path("tests/test_schema.py").read_text()
names = [name for name in ("test_every_committed_case_is_accepted_by_the_schema_as_by_the_parser", "test_every_committed_plan_is_accepted_by_the_schema_as_by_the_parser",
                           "test_a_wrong_case_is_refused_by_the_schema_as_by_the_parser", "test_a_wrong_plan_is_refused_by_the_schema_as_by_the_parser") if f"def {name}(" in tests]
row("D60", "'Proven on a corpus, both ways' (the four tests exist; run with `uv run pytest -q -p no:cacheprovider tests/test_schema.py`, see the notes)", names, len(names) == 4)

# D79
public = json.loads(Path("src/ventoux/public.json").read_text())
named = {"start_case": "ventoux.temporal.cases", "answer": "ventoux.temporal.cases", "close": "ventoux.temporal.cases", "propose_change": "ventoux.temporal.cases",
         "propose_forget": "ventoux.temporal.forget", "answer_forget": "ventoux.temporal.forget"}
there = {name: (callable(getattr(importlib.import_module(module), name, None)), name in public.get(module, [])) for name, module in named.items()}
row("D79", "'calling Ventoux's client functions (start_case, answer, close, propose_change and the others in ventoux.temporal.cases; propose_forget and answer_forget)': each exists", {name: exists for name, (exists, _) in there.items()}, all(exists for exists, _ in there.values()))
row("D79", "ASKED: which of them are supported names (src/ventoux/public.json)? (the report's finding 5.3 already lists the gap)", {name: listed for name, (_, listed) in there.items()}, True)
others = sorted(name for name in ("propose", "retry", "claim", "assign", "unassign", "give_back", "propose_migration", "preview_migrations", "send_event", "view", "approval_sheet", "shown") if name not in public["ventoux.temporal.cases"])
row("D79", "ASKED: 'and the others in ventoux.temporal.cases': the other client functions there that public.json doesn't list", others, True)

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
