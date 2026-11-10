# Shows which names the quickstart and the guides tell a team to call that src/ventoux/public.json, the list of supported imports, does not hold.
"""Run from the repository root: uv run python reviews/2026-11/probes/p5_public_names.py

D82: "The supported imports are a committed list, src/ventoux/public.json: the names the guides
tell teams to import, the builder's __all__, and the protocols a deployment implements." The
repository's own test reads `import` lines in the guides. This probe also reads the quickstart, and
the functions the guides tell a team to call in prose or in a snippet with no import line.
"""
import importlib
import json
import re
from pathlib import Path

PUBLIC = json.loads(Path("src/ventoux/public.json").read_text())
SUPPORTED = {(module, name) for module, names in PUBLIC.items() for name in names}

# (module, name, where a document tells the reader to use it)
TOLD = [
    ("ventoux.testing", "run_case", "docs/QUICKSTART.md", "from ventoux.testing import run_case"),
    ("ventoux.testing", "CATALOG", "docs/QUICKSTART.md", 'catalog = "ventoux.testing:CATALOG"'),
    ("ventoux.core.catalog", "Catalog", "docs/guides/activities.md", "catalog.register(payments_refund)"),
    ("ventoux.temporal.registry", "registry_worker", "docs/guides/releases.md", "registry_worker(client)"),
    ("ventoux.temporal.registry", "open_cases", "docs/guides/releases.md", "open_cases(client,"),
    ("ventoux.temporal.cases", "propose", "docs/guides/cases.md", "`propose(case, step, by, roles)`"),
    ("ventoux.temporal.cases", "retry", "docs/guides/cases.md", "`retry(case, entry, by, roles)`"),
    ("ventoux.temporal.cases", "close", "docs/guides/cases.md", "`close(case, reason, by,"),
    ("ventoux.temporal.cases", "view", "docs/guides/cases.md", "`view(case, roles)`"),
    ("ventoux.temporal.cases", "shown", "docs/guides/cases.md", "`shown(case, field,"),
    ("ventoux.temporal.cases", "propose_change", "docs/guides/deployment.md", "`propose_change`"),
    ("ventoux.temporal.sandbox", "SANDBOX", "docs/guides/case-data.md", "`SANDBOX` from `ventoux.temporal.sandbox`"),
    ("ventoux.tooling.audit", "same", "docs/guides/audit.md", "`ventoux.tooling.audit.same`"),
]
missing = 0
for module, name, document, text in TOLD:
    said = text in Path(document).read_text()
    exists = hasattr(importlib.import_module(module), name)
    listed = (module, name) in SUPPORTED
    print(f"{module}.{name}: the document says it ({document}: {text!r}): {said}; exists: {exists}; "
          f"in public.json: {listed}")
    if said and exists and not listed:
        missing += 1

readme = Path("README.md").read_text()
stale = "There is no code yet" in readme
print(f'README.md still says "There is no code yet ... Nothing here is ready to use": {stale}')
quickstart = Path("docs/QUICKSTART.md").read_text()
draft = "none of it is built yet" in quickstart
print(f'docs/QUICKSTART.md still says "none of it is built yet": {draft}')
server = any(re.search(r"start-dev|temporal server", Path(p).read_text())
             for p in ["README.md", "docs/QUICKSTART.md", *map(str, Path("docs/guides").glob("*.md"))])
print(f"some document says how to start a local Temporal server: {server}")

if missing:
    print(f"RESULT: BROKEN - {missing} names the documents tell a team to use exist and are not in public.json, "
          "so they are 'internal: importable, unsupported, free to change' (D82)")
else:
    print("RESULT: HELD - every name the documents tell a team to use is in public.json")
