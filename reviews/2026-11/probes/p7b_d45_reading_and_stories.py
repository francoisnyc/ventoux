# Shows whether a sample of D45's claims (a reading in the engine's order, names not titles, an unknown shape refused; a story that states its whole timeline, `ventoux simulate`) is what the code does.
import copy
import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from ventoux.case import reading  # not public: what `ventoux simulate` and the case map read rules with
from ventoux.case.definition import parse_case  # no public door reads a stored definition alone

ROWS: list[tuple[str, str, str, bool]] = []
# The `ventoux` command, as its entry point runs it (`ventoux.tooling.cli:main`), on this interpreter.
VENTOUX = [sys.executable, "-c", "import sys; from ventoux.tooling.cli import main; sys.exit(main())"]


def row(claim: str, shown: object, agrees: bool) -> None:
    ROWS.append(("D45", claim, " ".join(str(shown).split())[:520], agrees))


def titled(title: str, **more: object) -> dict:
    return {"display": {"title": title}, **more}


CASE = {
    "case": "probe", "display": {"title": "Probe"},
    "fields": {"amount": titled("ZZ Amount Title", type="number"), "owed": titled("Owed", type="number")},
    "milestones": {"big": titled("ZZ Milestone Title")},
    "steps": {
        "review": titled("ZZ Review Title", kind="task", roles=["support"], outcomes={"approve": titled("A")}),
        "pay": titled("ZZ Pay Title", kind="activity", activity="orders.lookup@1", inputs={"order_id": "o-1"}),
        "follow": titled("ZZ Follow Title", kind="task", roles=["support"], automatic=False, outcomes={"done": titled("D")}),
    },
    "rules": {"all": titled("ZZ Rule Title", on={"answered": "review"}, when={">": [{"var": "amount"}, 70]},
                            then={"start": ["follow"], "reach": ["big"], "set": {"owed": {"+": [{"var": "amount"}, 1]}}, "stop": ["pay"]})},
}
[read] = reading.read_rules(parse_case(copy.deepcopy(CASE)))
sentence = read.sentence if hasattr(read, "sentence") else str(read)
row("'Every rule reads as one sentence, its moment, its condition and its actions, in the order the engine takes them (stop, set, reach, start)'", sentence,
    -1 < sentence.find("pay") < sentence.find("owed") < sentence.find("big") < sentence.find("follow"))
row("'Names, not titles'", f"titles in the sentence: {[word for word in ('ZZ Review', 'ZZ Pay', 'ZZ Milestone', 'ZZ Follow', 'ZZ Amount') if word in sentence]}", "ZZ " not in sentence.replace("ZZ Rule Title", ""))
row("'A condition reads as the one-line expression renderer writes it (kyc.risk_score > 70)'", sentence, "amount > 70" in sentence)
fine = " | ".join(str(getattr(clause, "text", clause)) for clause in getattr(read, "fine_print", []))
row("'An action reads as what the engine does, never as its name alone: \"stop pay\" would read as if the payment stops' (and the fine print: a running call only asked to stop, a failed run never stopped)", fine or "(no fine print attribute found)",
    "a running call is only asked to stop" in fine and "a failed run isn't stopped" in fine)
row("MINOR, shown not counted: the sentence itself writes the action as the words D45 gives as the reading to avoid ('\"stop pay\" would read as if the payment stops'); only the fine print says what the engine does", f"'stop pay' in the sentence: {'stop pay' in sentence}", True)
unknown_shapes = {}
for name, call in (("a moment", lambda: reading.when("x", 42)), ("a timer's anchor", lambda: reading.after("x", 42))):
    try:
        unknown_shapes[name] = f"read as: {call()}"
    except Exception as error:
        unknown_shapes[name] = f"{type(error).__name__}: {error}"
row("'A moment, an action or an expression the reader doesn't know is refused, never left out of the sentence'", unknown_shapes, all(shown.startswith("ReadingRefused") for shown in unknown_shapes.values()))

story = Path("examples/claim/stories/assess-restarts.json")
done = subprocess.run([*VENTOUX, "simulate", str(story)], capture_output=True, text=True)
out = done.stdout + done.stderr
row("'One command, ventoux simulate STORY.json' (examples/claim/stories/assess-restarts.json); its output 'quotes no value from the case file' (the story opens with claimed 1200)", f"exit {done.returncode}; {len(out.splitlines())} lines; '1200' printed: {'1200' in out}; last: {out.strip().splitlines()[-1:]}",
    done.returncode == 0 and "1200" not in out)
with tempfile.TemporaryDirectory() as folder:
    data = json.loads(story.read_text(), parse_float=Decimal)
    data["definition"] = str(Path("examples/claim/claim.json").resolve())
    moment = next(iter(data["expect"]["timeline"]))
    dropped = data["expect"]["timeline"][moment].pop()
    changed = Path(folder) / "story.json"
    changed.write_text(json.dumps(data, default=str))
    done = subprocess.run([*VENTOUX, "simulate", str(changed)], capture_output=True, text=True)
    out = (done.stdout + done.stderr).strip().splitlines()
    row("'A story states what it expects, the whole timeline exactly, so a firing nobody expected fails it' (one expected line removed: the line the engine still writes is now unexpected)", f"removed: {dropped!r}; exit {done.returncode}; {out[-2:]}", done.returncode != 0)
    data = json.loads(story.read_text(), parse_float=Decimal)
    data["definition"] = str(Path("examples/claim/claim.json").resolve())
    data["expect"]["timeline"][moment].append("a line the engine never writes")
    changed.write_text(json.dumps(data, default=str))
    done = subprocess.run([*VENTOUX, "simulate", str(changed)], capture_output=True, text=True)
    row("(the other way: an expected line that never happens)", f"exit {done.returncode}", done.returncode != 0)
tests = subprocess.run(["grep", "-rln", "examples", "tests/test_simulate.py"], capture_output=True, text=True).stdout.strip()
stories = sorted(str(path) for path in Path("examples").rglob("stories/*.json"))
row("'stories under examples/ run as tests' (tests/test_simulate.py names examples/; run alone, see the notes)", f"{len(stories)} stories; {tests}", bool(tests) and len(stories) > 0)

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
