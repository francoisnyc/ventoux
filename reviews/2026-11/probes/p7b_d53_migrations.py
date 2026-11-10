# Shows, claim by claim, whether D53's migrations (refused never terminated, nothing loosens, timers, the engine forward only, the preview, a close naming what it didn't reach) are what the in-memory runtime does.
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.case.engine import ENGINE  # not public: this code's engine version
from ventoux.case.migrations import migration_of  # not public: what the client sends
from ventoux.case.runtime import preview_migration  # not public: the query's pure function
from ventoux.testing import CATALOG, START, close, later, migrate, release_of, run_case, send

ROWS: list[tuple[str, str, str, bool]] = []
REFUND = json.loads(Path("examples/refund/refund.json").read_text(), parse_float=Decimal)
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead", "platform"], "pia": ["platform"], "pat": ["platform"], "olga": ["operations"]}
FILE = {"order_id": "o-1", "amount": Decimal(250)}
REVIEWED = ("review", "approve", "ana", {"approved_amount": Decimal(250)})
APPROVE = ("case.change#1", "approve", "lee")


def row(claim: str, shown: object, agrees: bool) -> None:
    ROWS.append(("D53", claim, " ".join(str(shown).split())[:430], agrees))


def titled(title: str, **more: Any) -> dict:
    return {"display": {"title": title}, **more}


def changed(edit: Any, base: dict = REFUND) -> dict:
    definition = copy.deepcopy(base)
    edit(definition)
    return definition


def kept_open(base: dict = REFUND) -> dict:
    return changed(lambda d: d.update(stays_open=True, close_reasons={"done": titled("Done", roles=["support"])}), base)


def moved(source: dict, target: dict, before: list, after: list | None = None, mapping: dict | None = None, engine: int = ENGINE, by: str = "pia", **given: Any) -> list[str]:
    """The history of a case of `source`, `before` played, then a migration to `target` proposed by `by` (and `after` played)."""
    try:
        proposal = migrate(release_of(target, 2), mapping or {}, by, engine)
        run = run_case(copy.deepcopy(source), given.pop("file", FILE), [*before, proposal, *(after if after is not None else [APPROVE])], PEOPLE, release=release_of(source, 1), **given)
    except Exception as error:
        kind = "THE PROBE'S TARGET CAN'T BE RELEASED" if type(error).__name__ == "PackageRefused" else "refused"
        return [f"{kind}, {type(error).__name__}: {' '.join(str(error).split())}"]
    return [*run.history, f"[{run.status}; release {run.state.release}; needs attention: {run.needs_attention}; timers {run.timers}]"]


SECOND = changed(lambda d: d["display"].update(title="Customer refund, second release"))
found = moved(REFUND, SECOND, [REVIEWED])
row("'A migration moves an open case to another release, as a change request ... proposed and approved by roles registered to migrate'", found[-3:], "release refund 2" in found[-1] and any("applied case.change#1: migrated from refund 1" in line for line in found))
found = moved(REFUND, SECOND, [REVIEWED], after=[("case.change#1", "approve", "pia")])
row("'never [approved] by its proposer'", found[-1], found[-1].startswith("refused, AnswerRefused"))
found = moved(REFUND, SECOND, [REVIEWED], after=[("case.change#1", "approve", "pia")], by="lee", opened_by="pia")
row("'nor the case's opener' (pia opened the case, lee proposes, pia approves)", found[-1], found[-1].startswith("refused, AnswerRefused"))
found = moved(REFUND, SECOND, [REVIEWED], by="ana", after=[])
row("(a person whose roles don't migrate proposes)", found[-1], found[-1].startswith("refused"))
found = moved(kept_open(), kept_open(SECOND), [REVIEWED, ("pay.approval#1", "approve", "sam")], after=[close("done", "ana")])
row("'cancelled if the case closes first'", [line for line in found if "case.change#1" in line][-1:], any("case.change#1" in line and "cancel" in line for line in found) and "release refund 1" in found[-1])

# Refused, never terminated: what the case holds under a name the target lacks, unmapped.
def with_rule(d: dict) -> None:
    d["milestones"] = {"flagged": titled("Flagged")}
    d["rules"] = {"flag": titled("flag", on={"answered": "review"}, when={">": [{"var": "approved_amount"}, 100]}, then={"reach": ["flagged"]})}
def with_event(d: dict) -> None:
    d["events"] = {"cancelled": titled("Cancelled", sent_by={"system": "portal"}, payload={"why": titled("Why", type="string")})}
    d["steps"]["hello"] = titled("Hello", kind="task", roles=["support"], automatic=False, proposed_by=["support"], outcomes={"done": titled("Done")})
    d["rules"] = {"hear": titled("hear", on={"event": "cancelled"}, then={"start": ["hello"]})}
flagged = kept_open(changed(with_rule))
heard = kept_open(changed(with_event))
HELD = {
    "a run of a step in any status (an open task)": (kept_open(), changed(lambda d: (d["steps"].update(check=d["steps"].pop("review")), d.update(sequence=["check", "pay"]), d["steps"]["pay"].update(when={"==": [{"var": "check.outcome"}, "approve"]})), kept_open()), [], "review"),
    "an approval ... waiting on a step": (kept_open(), changed(lambda d: (d["steps"].pop("pay"), d["steps"].pop("call_customer"), d.pop("sequence")), kept_open()), [REVIEWED], "pay.approval#1"),
    "a reached milestone": (flagged, changed(lambda d: (d.pop("milestones"), d.pop("rules")), flagged), [REVIEWED], "flagged"),
    "a value in the case file": (kept_open(), changed(lambda d: d["fields"].pop("amount"), kept_open()), [], "amount"),
    "a rule's failed firing": (flagged, changed(lambda d: (d.pop("milestones"), d.pop("rules")), flagged), [("review", "reject", "ana")], "flag#1"),
    "an event's ... carried values": (heard, changed(lambda d: (d.pop("events"), d.pop("rules")), heard), [send("cancelled", {"why": "ZZWHY"}, "system:portal")], "cancelled"),
}
for held, (source, target, before, name) in HELD.items():
    found = moved(source, target, before, after=[])
    row(f"'Refused, never terminated. Anything the case holds under a name the target lacks, unmapped, refuses the migration': {held}", found[-1],
        found[-1].startswith("refused, ChangeRefused") and name in found[-1] and "ZZWHY" not in found[-1])
both = moved(kept_open(), changed(lambda d: (d["fields"].pop("amount"), d["fields"].pop("order_id"), d["steps"].pop("pay"), d["steps"].pop("call_customer"), d.pop("sequence")), kept_open()), [REVIEWED], after=[])
row("'each problem said at once with what to map or wait for'", both[-1], both[-1].count("map it") >= 3)
outcome_gone = moved(kept_open(), changed(lambda d: (d["steps"]["review"]["outcomes"].update(accept=d["steps"]["review"]["outcomes"].pop("approve")), d["steps"]["pay"].update(when={"==": [{"var": "review.outcome"}, "accept"]})), kept_open()), [REVIEWED], after=[])
row("'What a finished run ... recorded must be what the target can hold: a done run's outcome one its step declares'", outcome_gone[-1], outcome_gone[-1].startswith("refused, ChangeRefused") and "approve" in outcome_gone[-1])

# Nothing loosens.
def hidden(d: dict) -> None:
    d["fields"]["secret"] = titled("Secret", type="string", sensitive=True, visible_to=["support-lead"])
    d["fields"]["narrow"] = titled("Narrow", type="number", visible_to=["support-lead"])
strict = kept_open(changed(hidden))
SECRET = {**FILE, "secret": "ZZSECRET", "narrow": Decimal(7)}
LOOSER = {
    "a field never loses sensitive": lambda d: d["fields"]["secret"].pop("sensitive"),
    "widens the visible_to it declares": lambda d: d["fields"]["narrow"].update(visible_to=["support-lead", "support"]),
    "(drops the visible_to it declares)": lambda d: d["fields"]["narrow"].pop("visible_to"),
    "or changes type": lambda d: d["fields"]["narrow"].update(type="string"),
}
for claim, edit in LOOSER.items():
    found = moved(strict, changed(edit, strict), [], after=[], file=SECRET)
    row(f"'nothing loosens': {claim}", found[-1], found[-1].startswith("refused, ChangeRefused") and "ZZSECRET" not in found[-1])
found = moved(strict, changed(lambda d: d["fields"]["narrow"].update(visible_to=[]) if False else d["fields"]["amount"].update(visible_to=["support-lead"]), strict), [], file=SECRET)
row("(control, the stricter side: a field gaining a visible_to migrates)", found[-1], "release probe 2" in found[-1] or "release refund 2" in found[-1])

# Timers.
def chasing(age: str = "2d", since: Any = None) -> dict:
    d = kept_open()
    d["milestones"] = {"chased": titled("Chased"), "other": titled("Other")}
    d["rules"] = {"chase": titled("chase", on={"after": age, "since": since or {"started": "review"}}, then={"reach": ["chased"]})}
    return d
same = changed(lambda d: d["display"].update(title="v2"), chasing())
found = moved(chasing(), same, [later("1d")])
row("'Timers: kept if their rule, moment and age are'", found[-1], "timers ['chase" in found[-1] and "2026-01-03" in found[-1])
found = moved(chasing(), chasing("3d"), [later("1d")])
row("'measured again from when they were set if the age changed'", f"{[line for line in found if 'chase' in line and 'case.change' not in line][-1:]} {found[-1]}", "2026-01-04" in found[-1])
found = moved(chasing("3d"), chasing("1d"), [later("50h")])  # due a day after the start, 26 hours ago
row("'firing right after the migration if that time has passed'; 'Nothing fires in the past' (its due time becomes the migration's own)", found[-2:], "already past, so it fires now" in found[-2] and "due 2026-01-03T02:00:00Z" in found[-1])
found = moved(chasing("3d"), chasing("1d"), [later("50h")], after=[APPROVE, later("1m")])
row("(the same, a minute later: in memory a timer fires when the script next moves time, so the firing shows only then)", found[-4:-1], "reached chased" in found and found.index("reached chased") > next(i for i, line in enumerate(found) if "applied case.change#1" in line))
found = moved(chasing(), changed(lambda d: d.pop("rules"), chasing()), [later("1d")])
said = [line for line in found if line.startswith("cancelled chase")]
row("'cancelled, said, if the rule is gone'", f"{said}; {found[-1]}", bool(said) and "timers []" in found[-1])
found = moved(chasing(), chasing(since="opened"), [later("1d")])
said = [line for line in found if line.startswith("cancelled chase")]
row("'cancelled, said, if the rule ... waits on another moment'", f"{said}; {found[-1]}", bool(said) and "timers []" in found[-1])

# The engine.
found = moved(REFUND, SECOND, [REVIEWED], engine=ENGINE + 1, after=[])
row(f"'a version the code doesn't know ... is refused' (engine {ENGINE + 1})", found[-1], found[-1].startswith("refused, ChangeRefused"))
found = moved(REFUND, SECOND, [REVIEWED], engine=ENGINE - 1, after=[])
row(f"'or one older than the case's, is refused' (engine {ENGINE - 1}, the case on {ENGINE})", found[-1], found[-1].startswith("refused, ChangeRefused"))
try:
    older = run_case(copy.deepcopy(REFUND), FILE, [REVIEWED, migrate(release_of(REFUND, 1), {}, "pia"), APPROVE], PEOPLE, release=release_of(REFUND, 1), engine=ENGINE - 1)
    shown, agrees = f"release {older.state.release}, engine {older.state.engine}; {older.history[-2]}", older.state.engine == ENGINE
except Exception as error:
    shown, agrees = f"refused, {type(error).__name__}: {error}", False
row(f"'A migration may move the engine alone' (a case on engine {ENGINE - 1}, the same release, to {ENGINE})", shown, agrees)
try:
    run_case(copy.deepcopy(REFUND), FILE, [REVIEWED, migrate(release_of(REFUND, 1), {}, "pia")], PEOPLE, release=release_of(REFUND, 1))
    shown, agrees = "accepted", False
except Exception as error:
    shown, agrees = f"refused, {type(error).__name__}: {error}", True
row("'that it moves the release or the engine' (to the release and the engine it is on)", shown, agrees)

# The preview.
reviewed = run_case(copy.deepcopy(REFUND), FILE, [REVIEWED], PEOPLE, release=release_of(REFUND, 1))
before = copy.deepcopy(reviewed.state)
seen = preview_migration(parse_case(copy.deepcopy(REFUND)), CATALOG, reviewed.state, migration_of(release_of(SECOND, 2), {}, ENGINE), START)
row("'The preview is the apply without effect ... on a copy of the case's state'", f"lines {seen.lines[:1]}; refused {seen.refused}; the state is unchanged: {reviewed.state == before}", bool(seen.lines) and reviewed.state == before)
closed = run_case(copy.deepcopy(REFUND), FILE, [("review", "reject", "ana")], PEOPLE, release=release_of(REFUND, 1))
try:
    seen = preview_migration(parse_case(copy.deepcopy(REFUND)), CATALOG, closed.state, migration_of(release_of(SECOND, 2), {}, ENGINE), START)
    shown, agrees = f"{closed.status}: lines {seen.lines}; refused {seen.refused}", bool(seen.refused) and not seen.lines
except Exception as error:
    shown, agrees = f"{closed.status}: {type(error).__name__}: {error}", True
row("'a closed case's [preview] is refused' (the pure function the query calls, on a closed case's state)", shown, agrees)
found = moved(REFUND, SECOND, [("review", "reject", "ana")], after=[])
row("(a migration proposed for a closed case)", found[-1], found[-1].startswith("refused"))

# After it.
def ruled(d: dict) -> None:
    d["milestones"] = {"seen": titled("Seen")}
    d["rules"] = {"hello": titled("hello", on="opened", then={"reach": ["seen"]})}
found = moved(kept_open(), changed(ruled, kept_open()), [REVIEWED])
row("'a migration isn't a moment for rules' (the target adds a rule on `opened`)", [line for line in found if "hello" in line or "reached seen" in line], not any("hello#" in line or "reached seen" in line for line in found) and "release refund 2" in found[-1])
moved_run = run_case(copy.deepcopy(REFUND), FILE, [REVIEWED, migrate(release_of(SECOND, 2), {}, "pia"), APPROVE], PEOPLE, release=release_of(REFUND, 1))
row("'Values keep their sources, never re-stamped'", {name: sorted(sources) for name, sources in moved_run.state.sources.items()},
    moved_run.state.sources["approved_amount"] == frozenset({"person:ana"}) and moved_run.state.sources["amount"] == frozenset({"system:opener"}))
said = [line for line in moved_run.history if "case.change#1" in line]
row("'The history says each step, naming people, roles, releases, engine versions, names and entries, never a value'", said, len(said) == 3 and not any("250" in line for line in moved_run.history))
third = changed(lambda d: d["display"].update(title="third"))
try:
    stale = run_case(copy.deepcopy(REFUND), FILE, [REVIEWED, migrate(release_of(SECOND, 2), {}, "pia"), migrate(release_of(third, 3), {}, "pat"), ("case.change#1", "approve", "lee"), ("case.change#2", "approve", "lee")], PEOPLE, release=release_of(REFUND, 1))
    shown = [line for line in stale.history if "case.change#2" in line][-1:] + [f"release {stale.state.release}"]
    agrees = stale.state.release == "refund 2"
except Exception as error:
    shown, agrees = f"refused, {type(error).__name__}: {error}", "refund 1" in str(error) or "refund 2" in str(error)
row("'a migration proposed against the old release isn't applied' (two proposed on refund 1; the first applied, then the second approved)", shown, agrees)

# A close that didn't reach its closes_when.
def paid(d: dict) -> None:
    d["closes_when"] = ["paid"]
    d["milestones"] = {"paid": titled("Paid")}
    d["steps"]["pay"]["reaches"] = ["paid"]
rejected = run_case(changed(paid), FILE, [("review", "reject", "ana")], PEOPLE)
row("'A case that closes without reaching its closes_when says which milestones it didn't reach'", rejected.history[-1], rejected.status == "closed" and "paid not reached" in rejected.history[-1])

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
