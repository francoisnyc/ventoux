# Shows a package file with a JSON key written twice being released and read with the last one, silently, where a model's drafted answer with a key twice is refused.
"""Run: uv run python reviews/2026-11/probes/p3_duplicate_keys_last_wins.py

`case.json` of the repository's refund package, with the task `review` given `roles` twice: first
`["support"]`, at the top of the step where a reader sees it, then `["adjuster"]` after its
outcomes. `ventoux release`, `ventoux map` and `ventoux check --unchanged` (for a package listed
in `by_hand`) all take it; the engine runs the last one. The authoring loop refuses the same thing
from a model (`no_key_twice`, src/ventoux/authoring/answers.py). Only the `ventoux` command and
`ventoux.authoring.answers.one_object` (not a supported name) are used.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ventoux.authoring.answers import NotOneObject, one_object

ROOT = Path(__file__).resolve().parents[3]
VENTOUX = Path(sys.executable).parent / "ventoux"

with tempfile.TemporaryDirectory() as folder:
    project = Path(folder)
    (project / "pyproject.toml").write_text(
        '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\nby_hand = ["refund"]\n'
    )
    (project / "cases").mkdir()
    shutil.copytree(ROOT / "examples" / "packages", project / "packages")
    case = project / "packages" / "refund" / "case.json"
    text = case.read_text()
    first = '      "roles": [\n        "support"\n      ],\n      "outcomes": {'
    assert text.count(first) == 1
    at = text.index('    "settle": {')
    end = text.rindex("}", 0, at)  # the brace closing the step `review`
    twice = text[:end] + '  ,"roles": ["adjuster"]\n    ' + text[end:]
    case.write_text(twice)
    step = twice[twice.index('"review": {') : twice.index('    "settle": {')]
    print("`roles` is written", step.count('"roles"'), "times in the step review")

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(VENTOUX), *arguments],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    checked = run("check", "--unchanged")
    print("ventoux check --unchanged:", checked.returncode, checked.stdout.strip()[:120])
    released = run("release", "packages/refund", "--releases", "releases", "--commit", "c1")
    print("ventoux release:", released.returncode, (released.stdout + released.stderr).strip()[:90])
    mapped = run("map", "packages/refund")
    answered = [
        line for line in mapped.stdout.splitlines() if "review" in line and "answer" in line
    ]
    print("ventoux map says of who answers:", answered[:2])
    try:
        one_object(twice)
        model = "accepted"
    except NotOneObject as refused:
        model = f"refused ({refused})"
    print("the same text as a model's answer:", model)

took = checked.returncode == 0 and released.returncode == 0
if took and any("adjuster" in line for line in answered) and model.startswith("refused"):
    print(
        "RESULT: BROKEN - a definition with a key written twice is checked, released and run with "
        "the last one, nothing said; the first, which a reader meets, decides nothing"
    )
else:
    print("RESULT: HELD - a key written twice in a package file is refused")
