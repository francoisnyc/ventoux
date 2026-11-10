# Shows statements in the brief's top matter, the README, the quickstart, a guide and two layer notes beside what the code at this commit does.
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VENTOUX = ROOT / ".venv/bin/ventoux"


def text(path: str) -> str:
    return (ROOT / path).read_text()


def has(path: str, sentence: str) -> bool:
    return " ".join(sentence.split()) in " ".join(text(path).split())


def commands() -> set[str]:
    usage = subprocess.run([str(VENTOUX), "--help"], capture_output=True, text=True).stdout
    return set(re.search(r"\{([^}]+)\}", usage).group(1).split(","))  # type: ignore[union-attr]


broken: list[str] = []


def check(title: str, doc_says: str, observed: str, untrue: bool) -> None:
    print(f"\n{title}\n  the document: {doc_says}\n  observed:     {observed}")
    print("  ->", "UNTRUE NOW" if untrue else "agrees")
    if untrue:
        broken.append(title)


from ventoux.case.engine import ENGINE  # noqa: E402
from ventoux.core.catalog import Catalog  # noqa: E402

brief = text("docs/BRIEF.md")
decisions = [int(n) for n in re.findall(r"^### D(\d+)\.", brief, flags=re.M)]
schema = json.loads(text("src/ventoux/schema/case.schema.json"))
kinds = sorted(set(re.findall(r'"kind": \{"const": "(\w+)"', json.dumps(schema))))
cli = commands()
python_files = len(list((ROOT / "src/ventoux").rglob("*.py")))

# 1. The brief's status line.
line = brief.splitlines()[2]
check(
    "BRIEF.md line 3, the status line",
    line,
    f"the brief holds D1 to D{max(decisions)} ({len(decisions)} decisions)",
    "D1–D26" in line and max(decisions) != 26,
)

# 2. The glossary's Step row and the Simplifications' kinds of step.
step_row = next(row for row in brief.splitlines() if row.startswith("| Step |"))
check(
    "BRIEF.md glossary, 'Step'",
    step_row,
    f"the published case schema reads these kinds of step: {kinds}",
    "wait" not in step_row or "child case" not in step_row.lower(),
)

# 3. The glossary's Catalog row.
catalog_row = next(row for row in brief.splitlines() if row.startswith("| Catalog |"))
holds = sorted(n for n in dir(Catalog) if not n.startswith("_"))
check(
    "BRIEF.md glossary, 'Catalog'",
    catalog_row,
    f"Catalog's public names: {holds}; resolvers are registered in "
    f"tooling/resolvers.py (exists: {(ROOT / 'src/ventoux/tooling/resolvers.py').exists()})",
    "resolvers" in catalog_row and not any("resolver" in n for n in holds),
)

# 4. README's status.
says = "Design stage. There is no code yet"
check(
    "README.md, 'Status'",
    says + " ... Nothing here is ready to use.",
    f"src/ventoux holds {python_files} Python files; `ventoux` has {len(cli)} commands; "
    "CHANGELOG.md describes release 0.1.0",
    has("README.md", says) and python_files > 0,
)

# 5. The quickstart's banner and its commands.
banner = "none of it is built yet"
asked = sorted(
    set(re.findall(r"ventoux (init|dev|start|check|map|diff|import)\b", text("docs/QUICKSTART.md")))
)
missing = [c for c in asked if c not in cli and c != "import"]
check(
    "QUICKSTART.md, the banner and the commands it tells the reader to run",
    f"'{banner}'; it runs `ventoux` {asked}",
    f"commands that exist: {sorted(c for c in asked if c in cli)}; that don't: {missing}; "
    "tests/test_quickstart.py runs its case (built)",
    has("docs/QUICKSTART.md", banner) or bool(missing),
)

# 6. D13: `ventoux init` generates no plan.
check(
    "BRIEF.md D13",
    "`ventoux init` generates no plan",
    f"`init` is a command: {'init' in cli}",
    "init" not in cli,
)

# 7. The cases guide's `$id`.
said = re.search(
    r"https://ventoux\.dev/schema/engine-(\d+)/case\.schema\.json", text("docs/guides/cases.md")
)
assert said
check(
    "guides/cases.md, 'The schema'",
    f"{said.group(0)} 'is the format engine version {said.group(1)} reads'",
    f"the committed schema's $id is {schema['$id']}; ENGINE is {ENGINE}",
    said.group(0) != schema["$id"],
)

# 8. The deployment guide's `ventoux version` output.
printed = subprocess.run([str(VENTOUX), "version"], capture_output=True, text=True).stdout
guide_line = next(
    row for row in text("docs/guides/deployment.md").splitlines() if row.startswith("ventoux 0.1.0")
)
check(
    "guides/deployment.md, `$ ventoux version`",
    guide_line,
    repr(printed),
    guide_line.strip() != printed.strip(),
)

# 9. Two rows of Promises tables naming tests that no longer exist.
tests = "\n".join(p.read_text() for p in (ROOT / "tests").glob("*.py"))
for note, name in [
    (
        "docs/layers/18-lifecycle.md",
        "test_after_a_switch_a_child_terminated_unheard_is_noticed_within_a_day",
    ),
    (
        "docs/layers/20-deployment.md",
        "test_pydantic_is_bounded_to_the_minor_version_the_hashes_were_made_with",
    ),
]:
    in_table = any(row.startswith("|") and name in row for row in text(note).splitlines())
    check(
        f"{note}, a row of its Promises table",
        f"names the test `{name}`",
        f"a test of that name is defined in tests/: {f'def {name}(' in tests}",
        in_table and f"def {name}(" not in tests,
    )

# 10. "The Ventoux API" after D79 (v1.0 ships no API).
counts = {
    p.name: len(re.findall(r"(?i)\bVentoux\s+API\b", p.read_text()))
    for p in sorted((ROOT / "docs/guides").glob("*.md"))
}
counts = {k: v for k, v in counts.items() if v}
sources = sum(
    len(re.findall(r"(?i)\bVentoux\s+API\b", p.read_text()))
    for p in (ROOT / "src/ventoux").rglob("*.py")
)
check(
    "guides and docstrings naming 'the Ventoux API' as the caller",
    f"guides: {counts}; docstrings and comments in src/ventoux: {sources}",
    "D79: 'in v1.0 the trusted caller is the integrator's own service, not a Ventoux API'",
    bool(counts),
)

print()
if broken:
    print(
        f"RESULT: BROKEN - {len(broken)} statement(s) describe what was later changed: "
        + "; ".join(broken)
    )
else:
    print("RESULT: HELD - every statement checked agrees with the code")
