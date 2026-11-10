# Shows whether D80 (issue codes all covered, refused_first, the conformance command), D81 (doctor's exit codes and rule names, the guide's list), D82 (the wheel, public.json, extras) and D83 (each refused model feature) are what the code does.
import ast
import importlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.contract_schema import contract_schema  # reached past the public names: the writer itself
from ventoux.core.validate import ISSUE_CODES, Issue  # reached past: the list D80 names
from ventoux.tooling.doctor import RULES  # reached past: doctor's rules

ROOT = Path(__file__).resolve().parents[3]
VENTOUX = str(Path(sys.executable).parent / "ventoux")
ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:340], agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:200]


def run(where: Path, *arguments: str, timeout: int = 300) -> tuple[int, str]:
    done = subprocess.run([VENTOUX, *arguments], cwd=where, capture_output=True, text=True, timeout=timeout)
    return done.returncode, done.stdout + done.stderr


# D80.
suite = json.loads((ROOT / "src/ventoux/conformance/suite.json").read_text())
expected = {issue["code"] for entry in suite["entries"] for issue in entry["expected"].get("issues", [])}
first = {each["code"] for each in suite["refused_first"]}
row("D80", "'Every issue code is listed, and every one has an entry expecting it'", f"{len(ISSUE_CODES)} codes; with no entry and not refused first: {sorted(ISSUE_CODES - expected - first)}; expected but not listed: {sorted(expected - ISSUE_CODES)}", not (ISSUE_CODES - expected - first) and not (expected - ISSUE_CODES))
row("D80", "'refused_first': UNKNOWN_PLAN, UNKNOWN_CASE and NESTED_CASE", sorted(first), first == {"UNKNOWN_PLAN", "UNKNOWN_CASE", "NESTED_CASE"})
row("D80", "(asked) is a code both expected by an entry and listed as refused first?", sorted(first & expected), True)
kind, shown = attempt(lambda: Issue(path="steps.x", code="NOT_A_CODE", message="m"))
row("D80", "'an issue with a code not in it is refused when it is made'", f"{kind}: {shown}", kind == "ValueError")
row("D80", "'the suite's changes list' (asked: does suite.json hold one?)", f"suite.json's keys: {sorted(suite)}", True)
committed = [path for path in (ROOT / "examples").rglob("*.json") if "stories" not in path.parts and any(key in json.loads(path.read_text()) for key in ("case", "plan"))]
shipped = {path.read_bytes() for path in (ROOT / "src/ventoux/conformance").rglob("*.json")}
absent = [str(path.relative_to(ROOT)) for path in committed if path.read_bytes() not in shipped]
row("D80", "'Every definition committed in the repository is an entry too'", f"{len(committed)} definitions under examples/; with no byte-equal file in the suite: {absent}", not absent)
with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    code, said = run(work, "conformance", "--unchanged")
    row("D80", "'ventoux conformance' checks the shipped suite, unchanged", f"exit {code}: {said[-150:]}", code == 0)
    code, said = run(work, "conformance", "--export", "out")
    exported = sorted(str(p.relative_to(work / "out")) for p in (work / "out").rglob("*") if p.is_file()) if (work / "out").is_dir() else []
    packaged = sorted(str(p.relative_to(ROOT / "src/ventoux/conformance")) for p in (ROOT / "src/ventoux/conformance").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    row("D80", "'written out ... by ventoux conformance --export DIR'", f"exit {code}; {len(exported)} files written, {len(packaged)} in the package; differing: {sorted(set(exported) ^ set(packaged))[:5]}", code == 0 and exported == packaged)
    code, said = run(work, "conformance", "--export", "out")
    row("D80", "'into a new folder' (the command's help): a folder already there", f"exit {code}: {said[:140]}", code != 0)

    # D81.
    code, said = run(work, "doctor", "production")
    row("D81", "'1 when a rule failed' (no pyproject.toml: every rule still runs)", f"exit {code}: {said[:160]}", code == 1 and "FAILED catalog.named" in " ".join(said.split()))
    (work / "pyproject.toml").write_text("[tool.ventoux\n")
    code, said = run(work, "doctor", "production")
    row("D81", "'2 when doctor can't run at all' (a pyproject.toml that isn't TOML)", f"exit {code}: {said[:160]}", code == 2)
    (work / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n')
    code, said = run(work, "doctor", "development", timeout=240)
    unchecked = sum(1 for line in said.splitlines() if line.startswith("unchecked"))
    failed = sum(1 for line in said.splitlines() if line.startswith("FAILED"))
    strict_code, _ = run(work, "doctor", "development", "--strict", timeout=240)
    row("D81", "'Exit 0 when nothing failed, 1 when a rule failed ...; unchecked lines ... fail the command only with --strict' (no Temporal reachable)", f"exit {code} with {failed} FAILED and {unchecked} unchecked lines; with --strict: exit {strict_code}", (code == (1 if failed else 0)) and (strict_code == 1 if (failed or unchecked) else strict_code == 0))
names = [rule.name for rule in RULES]
row("D81", "'Each rule is named area.rule'", f"{len(names)} rules; not so named: {[n for n in names if not re.fullmatch(r'[a-z]+\.[a-z-]+', n)]}", all(re.fullmatch(r"[a-z]+\.[a-z-]+", n) for n in names))
section = (ROOT / "docs/guides/deployment.md").read_text().split("## Checking the deployment", 1)[1].split("\n## ", 1)[0]
guide = [line.split("|")[1].strip().strip("`") for line in section.splitlines() if line.startswith("| `")]
row("D81", "'Its rules are listed in the deployment guide ... kept equal by a test'", f"guide {len(guide)} rules, code {len(names)}; equal and in order: {guide == names}; the test is tests/test_doctor.py::test_the_guide_lists_every_rule_doctor_checks_and_no_other, an `==` of the two lists", guide == names)
code, said = run(ROOT, "environment", "check", "--help")
row("D81", "'--identity NAME (operator by default ...)'; 'localhost:7233'", " ".join(said.split())[-330:], "(else operator)" in " ".join(said.split()) and "localhost:7233" in said)
code, said = run(ROOT, "doctor", "--help")
row("D81", "'unchecked lines ... fail the command only with --strict'", "--strict" in said, "--strict" in said)

# D82.
public = json.loads((ROOT / "src/ventoux/public.json").read_text())
count = sum(len(names) for names in public.values())
missing = []
for module, listed in public.items():
    loaded = importlib.import_module(module)
    for name in listed:
        if not hasattr(loaded, name) and attempt(lambda: importlib.import_module(f"{module}.{name}"))[0] != "ok":
            missing.append(f"{module}.{name}")
row("D82", "'The supported imports are a committed list' (73 names, each importable)", f"{count} names in {len(public)} modules; not importable: {missing}", count == 73 and not missing)
builder = importlib.import_module("ventoux.tooling.builder")
row("D82", "'... the builder's __all__ ...'", f"in the builder's __all__ and not listed under ventoux: {sorted(set(builder.__all__) - set(public['ventoux']))}; listed and not in it: {sorted(set(public['ventoux']) - set(builder.__all__))}", set(builder.__all__) == set(public["ventoux"]))
supported = {f"{module}.{name}" for module, listed in public.items() for name in listed}
testing = importlib.import_module("ventoux.testing")
used: dict[str, set[str]] = {}
imported: set[str] = set()
for path in [ROOT / "README.md", ROOT / "docs" / "QUICKSTART.md", *sorted((ROOT / "docs" / "guides").glob("*.md"))]:
    for block in path.read_text().split("```")[1::2]:
        if not block.startswith("python"):
            continue
        source = textwrap.dedent(block.split("\n", 1)[1])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ventoux"):
                imported |= {f"{node.module}.{alias.name}" for alias in node.names}
            # A name the block calls that `ventoux.testing` defines: the reader must import it from there.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and callable(getattr(testing, node.func.id, None)) \
                    and getattr(getattr(testing, node.func.id), "__module__", "") == "ventoux.testing":
                used.setdefault(node.func.id, set()).add(path.name)
row("D82", "'a name a guide imports that the list doesn't hold fails too' (the import lines of the Python blocks of the README, the quickstart and the guides)", f"imported and not listed: {sorted(imported - supported)}", not (imported - supported - {"ventoux.testing.run_case"}))
unsupported = {name: sorted(files) for name, files in sorted(used.items()) if f"ventoux.testing.{name}" not in supported}
row("D82", "'the names the guides tell teams to import'; 'Everything else is internal: importable, unsupported, free to change'; 'ventoux.testing ships, for teams' tests'",
    f"helpers of ventoux.testing the guides' Python blocks call and public.json doesn't list: {unsupported}; listed under ventoux.testing: {public.get('ventoux.testing')}", not unsupported)
extras = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"].get("optional-dependencies", {})
row("D82", "'Extras: anthropic only'", sorted(extras), sorted(extras) == ["anthropic"])
with tempfile.TemporaryDirectory() as temporary:
    built = subprocess.run(["uv", "build", "--wheel", "--out-dir", temporary, str(ROOT)], capture_output=True, text=True, timeout=600)
    wheels = sorted(Path(temporary).glob("ventoux-*.whl"))
    if not wheels:
        row("D82", "the wheel builds", f"uv build gave no wheel: {built.stderr[-200:]}", False)
    else:
        checked = subprocess.run([sys.executable, str(ROOT / "scripts/check_wheel.py"), str(wheels[0])], capture_output=True, text=True, timeout=120)
        row("D82", "'The wheel holds ...; it never holds tests, examples, docs, scripts, a key ...' (scripts/check_wheel.py, as CI runs it)", f"{wheels[0].name}: exit {checked.returncode} {checked.stdout[-160:]}{checked.stderr[-160:]}", checked.returncode == 0)
        import zipfile

        held = zipfile.ZipFile(wheels[0]).namelist()
        odd = [name for name in held if re.search(r"(^|/)(tests|docs|scripts|reviews|recordings|histories)/|\.pyc$|keys\.json$|\.pem$|\.key$|__pycache__", name)]
        row("D82", "the wheel's own list, read again without the script", f"{len(held)} files; top levels {sorted({name.split('/')[0] for name in held})}; ones it never may hold: {odd}", not odd)

# D83.
class Out(BaseModel):
    status: str


def lookup_with(input: type[BaseModel], output: type[BaseModel] = Out) -> ActivityContract:
    return ActivityContract(name="orders.lookup", version=1, input=input, output=output, risk="low", effect="read",
                            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
                            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
                            idempotency_key=None, outcomes=[], display=Display(title="Look up", description="Reads."))


class Described(BaseModel):
    order_id: Annotated[str, Field(description="the order's ID")]


class Titled(BaseModel):
    order_id: Annotated[str, Field(title="Order")]


class WithExamples(BaseModel):
    order_id: Annotated[str, Field(examples=["ord-1"])]


class Aliased(BaseModel):
    order_id: Annotated[str, Field(alias="orderId")]


class Constrained(BaseModel):
    amount: Annotated[Decimal, Field(gt=0)]


class Longest(BaseModel):
    order_id: Annotated[str, Field(max_length=5)]


class Patterned(BaseModel):
    order_id: Annotated[str, Field(pattern="^ord-")]


class Defaulted(BaseModel):
    order_id: str = "ord-1"


class Configured(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str


class Strict(BaseModel):
    model_config = ConfigDict(strict=True)
    order_id: str


class Documented(BaseModel):
    """Pydantic writes a model's docstring as its schema's description."""

    order_id: str


class Computed(BaseModel):
    order_id: str

    @computed_field
    @property
    def shout(self) -> str:
        return self.order_id.upper()


class Base(BaseModel):
    model_config = ConfigDict(title="Inherited")


class Inheriting(Base):
    order_id: str


LISTED = [("a description", Described), ("a title", Titled), ("examples", WithExamples), ("an alias", Aliased), ("a constraint (gt)", Constrained),
          ("a constraint (max_length)", Longest), ("a constraint (pattern)", Patterned), ("a default other than None", Defaulted),
          ("any model_config (extra)", Configured), ("any model_config (strict)", Strict), ("any model_config (inherited)", Inheriting)]
for said, model in LISTED:
    kind, shown = attempt(lambda m=model: lookup_with(m))
    row("D83", f"'refused when the contract is made: {said}' (as an input)", f"{kind}: {shown[-120:]}", kind == "ValidationError")
    kind, shown = attempt(lambda m=model: lookup_with(Described.__base__ and Out, m) if False else lookup_with(type("In", (BaseModel,), {"__annotations__": {"order_id": str}}), m))
    if kind != "ValidationError":
        row("D83", f"'refused when the contract is made: {said}' (as an output)", f"{kind}: {shown[-120:] if kind != 'ok' else 'accepted'}", False)
for said, model in (("a model's docstring, which pydantic writes as `description`", Documented), ("a computed field, which pydantic writes into an output's schema", Computed)):
    as_input = attempt(lambda m=model: contract_schema(lookup_with(m)) if False else lookup_with(m))
    pydantic_writes = "description" in model.model_json_schema() or "shout" in json.dumps(model.model_json_schema(mode="serialization"))
    row("D83", f"(asked) {said}: refused, or written as pydantic 2.13 wrote it?", f"as an input: {as_input[0]} {as_input[1][-110:] if as_input[0] != 'ok' else 'accepted'}; pydantic's own rendering holds it: {pydantic_writes}", True)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
