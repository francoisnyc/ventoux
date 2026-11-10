# Shows whether the advisor's answer forms and label (D61, D62), the live provider's address (D62), and `ventoux draft` / `draft-sheet` (D63, D64: exit codes, the record, a draft already there, the sheet's six parts, an edited draft) are what the code does. Uses recordings only: no key, no network.
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))  # the recorded provider and the drafts the tests use

from test_authoring import GOAL, SCHEMA, TO_THE_EMAIL, TO_THE_NOTE, refund_case, refund_plan, the_package, written  # noqa: E402

from ventoux.authoring.advisor import Advice, NotOneName, step_named  # noqa: E402  (reached past the public names)
from ventoux.authoring.loop import author  # noqa: E402
from ventoux.authoring.provider import Recorded, Recording  # noqa: E402
from ventoux.testing import CATALOG  # noqa: E402

VENTOUX = str(Path(sys.executable).parent / "ventoux")
PLAN = "refund-order@1"
ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:330], agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:160]


def run(where: Path, *arguments: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    done = subprocess.run([VENTOUX, *arguments], cwd=where, capture_output=True, text=True, timeout=300, env=env)
    return done.returncode, done.stdout + done.stderr


# D61: the forms of an answer.
ACCEPTED = {'{"step": "goodwill"}': "goodwill", '{"step": null}': None, '```json\n{"step": "goodwill"}\n```': "goodwill", '```\n{"step": null}\n```': None}
REFUSED = ['I suggest goodwill.', '["goodwill"]', '{"step": "goodwill", "amount": 50}', '{"step": 7}', '{"step": ["goodwill"]}', '{"step": true}',
           'Here you go:\n```json\n{"step": "goodwill"}\n```', '```json\n{"step": "goodwill"}\n```\n```json\n{"step": "pay"}\n```',
           '{"step": "goodwill"} {"step": "pay"}', '{"step": "goodwill", "step": "pay"}', '{"Step": "goodwill"}', '', '{}', '{"step": "Good Will"}', '{"step": ""}']
wrong = [answer for answer, named in ACCEPTED.items() if attempt(lambda a=answer: step_named(a)) != ("ok", named)]
wrong += [answer for answer in REFUSED if attempt(lambda a=answer: step_named(a))[0] != "NotOneName"]
row("D61", "'exactly {\"step\": \"<name>\"} or {\"step\": null}, at most inside one fenced block; anything else (prose, a list, a second key ..., a name that isn't text) suggests nothing'", f"{len(ACCEPTED)} forms accepted, {len(REFUSED)} refused; read the wrong way: {wrong}", not wrong)
kind, advice = attempt(lambda: Advice(step="goodwill", refused=None, by="recorded"))
if kind != "ok":
    import dataclasses

    names = [field.name for field in dataclasses.fields(Advice)]
    kind, advice = attempt(lambda: Advice(**{name: ("goodwill" if name == "step" else "untrusted:llm" if name == "source" else None) for name in names}))
label = attempt(lambda: advice.said())
row("D62", "'Suggested by the step advisor (untrusted:llm): …'", label, "Suggested by the step advisor (untrusted:llm): goodwill" in str(label[1]))

# D62: the live provider's address, with the environment naming another.
os.environ["ANTHROPIC_BASE_URL"] = "https://elsewhere.example"
kind, shown = attempt(lambda: str(__import__("ventoux.authoring.anthropic", fromlist=["client_for"]).client_for("not-a-key").base_url))
row("D62", "'ANTHROPIC_BASE_URL can't send the key and the prompts elsewhere' (the SDK's client, as the provider builds it, with the variable set)", f"{kind}: {shown}", kind == "ok" and str(shown).startswith("https://api.anthropic.com"))
del os.environ["ANTHROPIC_BASE_URL"]

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    (work / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\ndrafts = "drafts"\n')
    package = work / "packages" / "refund"
    (package / "plans").mkdir(parents=True)
    (package / "case.json").write_text(written(refund_case()))
    (package / "plans" / "refund-order.json").write_text(written(refund_plan()))

    def recorded(name: str, *answers: str) -> str:
        recording = Recording(Recorded.answering(*answers))
        asyncio.run(author(GOAL, the_package(), PLAN, CATALOG, SCHEMA, recording, 3))
        recording.save(work / name)
        return name

    clean = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    base = ["draft", "packages/refund", "--plan", PLAN, "--goal", GOAL, "--by", "omar"]
    code, said = run(work, "advise", "claim-7", "--by", "ana", env=clean)
    row("D62", "'ventoux advise exits ... 2 when it couldn't be asked: a setting ...' (no model named)", f"exit {code}: {said[:150]}", code == 2 and "Traceback" not in said)
    code, said = run(work, *base, env=clean)
    row("D63", "'2 when it couldn't ask or read' (no model named, no recording)", f"exit {code}: {said[:150]}", code == 2 and not (work / "drafts").exists())
    code, said = run(work, *base, "--model", "some-model", env=clean)
    row("D62", "'No key ... is a failure, said by the setting's name, never its value' (a model named, no key)", f"exit {code}: {said[:170]}", code == 2 and "ANTHROPIC_API_KEY" in said)
    code, said = run(work, *base, "--recording", recorded("abandoned.json", TO_THE_NOTE, TO_THE_NOTE, TO_THE_NOTE), env=clean)
    files = sorted(p.name for p in (work / "drafts").iterdir()) if (work / "drafts").is_dir() else []
    row("D63", "'1 abandoned'; 'never written as a plan file'; 'always, once the model was asked, <plan>.record.json'", f"exit {code}; drafts/ holds {files}; {said[:110]}", code == 1 and files == [f"{PLAN}.record.json"])
    code, said = run(work, *base, "--recording", recorded("drafted.json", TO_THE_NOTE, TO_THE_EMAIL), env=clean)
    row("D63", "'A draft already there is refused, never overwritten' (the abandoned draft's record is there)", f"exit {code}: {said[:170]}", code != 0)
    for path in (work / "drafts").iterdir():
        path.unlink()
    code, said = run(work, *base, "--recording", "drafted.json", env=clean)
    files = sorted(p.name for p in (work / "drafts").iterdir())
    row("D63", "'It exits 0 drafted'; '<plan>.json if drafted'", f"exit {code}; drafts/ holds {files}", code == 0 and files == [f"{PLAN}.json", f"{PLAN}.record.json"])
    record = json.loads((work / "drafts" / f"{PLAN}.record.json").read_text())
    wanted = ["goal", "asked_by", "provider", "rounds", "verdict", "reason"]
    row("D63", "'the goal, who asked, the provider, each round's answer and problems, the verdict and why'", f"the record's keys: {sorted(record)}; a round's keys: {sorted(record['rounds'][0])}", all(key in record for key in wanted) and sorted(record["rounds"][0]) == ["answer", "problems"])
    before = (work / "drafts" / f"{PLAN}.json").read_bytes()
    code, said = run(work, *base, "--recording", "drafted.json", env=clean)
    row("D63", "'A draft already there is refused, never overwritten'", f"exit {code}: {said[:150]}", code != 0 and (work / "drafts" / f"{PLAN}.json").read_bytes() == before)

    # D64: the sheet.
    code, sheet = run(work, "draft-sheet", f"drafts/{PLAN}.json", "--package", "packages/refund", env=clean)
    PARTS = ["Drafted by `recorded` for omar, in 2 rounds, from the goal:", "what changes", "as drafted", "never", "## Warnings", "## How it becomes real"]
    places = [sheet.find(part) for part in PARTS]
    row("D64", "'What it shows, in order' (the six parts)", f"exit {code}; where each part starts: {dict(zip(PARTS, places))}", code == 0 and all(place >= 0 for place in places) and places == sorted(places))
    row("D64", "'Never the model's own text' (no round's answer on the page)", f"the first answer's text on the page: {TO_THE_NOTE[:40] in sheet}", TO_THE_NOTE not in sheet)
    (work / "drafts" / f"{PLAN}.json").write_bytes(before.replace(b"\n", b"\n ", 1))
    code, said = run(work, "draft-sheet", f"drafts/{PLAN}.json", "--package", "packages/refund", env=clean)
    row("D64", "'The sheet hashes the file again and refuses on any difference' (one space added); 'exits ... 2'", f"exit {code}: {said[:170]}", code == 2 and "Approve this plan" not in said)
    (work / "drafts" / f"{PLAN}.json").write_bytes(before)
    kept = (work / "drafts" / f"{PLAN}.record.json").read_text()
    without = json.loads(kept)
    del without["draft_sha256"]
    (work / "drafts" / f"{PLAN}.record.json").write_text(json.dumps(without))
    code, said = run(work, "draft-sheet", f"drafts/{PLAN}.json", "--package", "packages/refund", env=clean)
    row("D64", "'... or on a record without the field'", f"exit {code}: {said[:150]}", code == 2 and "Approve this plan" not in said)
    abandoned = json.loads(kept) | {"verdict": "abandoned"}
    (work / "drafts" / f"{PLAN}.record.json").write_text(json.dumps(abandoned))
    code, said = run(work, "draft-sheet", f"drafts/{PLAN}.json", "--package", "packages/refund", env=clean)
    row("D64", "'its verdict is drafted'", f"exit {code}: {said[:150]}", code == 2 and "Approve this plan" not in said)
    (work / "drafts" / f"{PLAN}.record.json").write_text(kept)
    code, said = run(work, "draft-sheet", f"drafts/{PLAN}.json", "--package", "drafts", env=clean)
    row("D64", "'A drafts folder is never a package ... the sheet's --package refuse[s] it'", f"exit {code}: {said[:150]}", code == 2)
    code, said = run(work, "release", "drafts", "--releases", "releases", "--commit", "abc", env=clean)
    row("D64", "'... so ventoux release ... refuse[s] it'", f"exit {code}: {said[:150]}", code != 0)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
