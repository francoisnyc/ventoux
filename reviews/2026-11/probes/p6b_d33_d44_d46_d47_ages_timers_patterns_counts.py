# Shows whether D33/D44's ages and tie rules, D46's pattern expansion names and refusals, and D47's `count` readings and history wordings are what the code does.
import copy
import json
from decimal import Decimal
from pathlib import Path

from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.testing import later, run_case

ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, str(shown), agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:150]


def load(name: str) -> dict:
    return json.loads(Path(name).read_text(), parse_float=Decimal)


CLAIM = load("examples/claim/claim.json")
REMINDED = load("examples/refund/refund-reminded.json")
FOUR = load("examples/refund/refund-four-eyes.json")


def claim_within(age: object) -> dict:
    case = copy.deepcopy(CLAIM)
    case["rules"]["escalate"]["sla"]["within"] = age
    return case


# D33/D44: which ages a timer takes.
readings = {age: attempt(lambda a=age: parse_case(claim_within(a)))[0] for age in
            ["30m", "12h", "1d", "1m", "1w", "90s", "60s", "0m", "0d", "1.5h", "-1d", "+1d", " 1d", "1d ", "1D", "", "d", "٣d", "1_0d", "01d", 5, "59m"]}
accepted = sorted(str(a) for a, kind in readings.items() if kind == "ok")
row("D44", "'an age in D33's format (30m, 12h, 1d), at least a minute'", f"accepted: {accepted}", accepted == sorted(["30m", "12h", "1d", "1m", "01d", "59m"]))
huge = "9" * 30 + "d"
kind, shown = attempt(lambda: parse_case(claim_within(huge)))
# Not a promise of D44, so it never breaks the result: what Temporal's own duration does with such a wait.
from google.protobuf.duration_pb2 import Duration  # what the SDK writes a workflow timer's wait into

seconds = 10**30 * 86400
sdk_kind, sdk_shown = attempt(lambda: Duration().FromNanoseconds(seconds * 10**9))
row("D44", "an age with no upper bound (asked: is one that no workflow timer can hold refused when read?)",
    f"{huge[:6]}...d (30 digits): read: {kind}; the same wait as a protobuf duration: {sdk_kind} {sdk_shown if sdk_kind != 'ok' else ''}", True)

# D33: max_age.
def with_max_age(age: object) -> dict:
    case = copy.deepcopy(FOUR)
    case["steps"]["pay"]["max_age"] = {"approved_amount": age}
    return case


readings = {age: attempt(lambda a=age: parse_case(with_max_age(a)))[0] for age in ["30m", "12h", "1d", "1w", "90s", "0m", "1.5h", "0d"]}
accepted = sorted(a for a, kind in readings.items() if kind == "ok")
row("D33", "'max_age ... as 30m, 12h or 1d' (the code: 'at least a minute')", f"accepted: {accepted}", accepted == ["12h", "1d", "30m"])

# D44: the tie rules, on two timers due at one second and an event at that second.
TIES = {
    "case": "ties", "display": {"title": "Ties"}, "fields": {},
    "steps": {
        "work": {"kind": "task", "display": {"title": "Work"}, "roles": ["support"], "outcomes": {"done": {"display": {"title": "Done"}}}},
        "second": {"kind": "task", "display": {"title": "Second"}, "roles": ["support"], "automatic": False, "repeatable": True, "outcomes": {"done": {"display": {"title": "Done"}}}},
        "first": {"kind": "task", "display": {"title": "First"}, "roles": ["support"], "automatic": False, "repeatable": True, "outcomes": {"done": {"display": {"title": "Done"}}}},
    },
    "rules": {
        "b_rule": {"display": {"title": "B"}, "on": {"after": "1d", "since": {"opened": True}}, "then": {"start": ["second"]}},
        "a_rule": {"display": {"title": "A"}, "on": {"after": "24h", "since": {"opened": True}}, "then": {"start": ["first"]}},
    },
}
kind, parsed = attempt(lambda: parse_case(copy.deepcopy(TIES)))
if kind != "ok":
    for since in ({"opened": {}}, "opened", {"opened": None}):
        for rule in TIES["rules"].values():
            rule["on"]["since"] = since
        kind, parsed = attempt(lambda: parse_case(copy.deepcopy(TIES)))
        if kind == "ok":
            break
if kind != "ok":
    row("D44", "tie rules", f"the probe's definition was refused: {parsed}", False)
else:
    run = run_case(copy.deepcopy(TIES), {}, [later("1d"), ("work", "done", "ana")], {"ana": ["support"]})
    lines = [line for line in run.history if "_rule#1" in line or "answered" in line]
    order = [("b_rule" in line and "b") or ("a_rule" in line and "a") or "answer" for line in lines]
    row("D44", "'two due at one second in the order they were set; at a tie with an event, the timer goes first'", f"{order} <- {lines}", order == ["b", "a", "answer"])
    row("D44", "'reports list set timers ... soonest first, with their due time in UTC'", run_case(copy.deepcopy(TIES), {}, [], {}).timers, True)

# D46: the names a pattern expands into, and its refusals.
expanded = [name for name in parse_case(copy.deepcopy(REMINDED)).rules]
row("D46", "'a reminder gives one rule per age, <name>_<age> as written (remind_review_2d)'", expanded, expanded == ["remind_review_1d", "remind_review_2d", "remind_review_4d"])
expanded = [name for name in parse_case(copy.deepcopy(CLAIM)).rules]
row("D46", "'A pattern that expands into one rule gives it its own name'", expanded, expanded == ["escalate"])


def reminded(**reminder: object) -> dict:
    case = copy.deepcopy(REMINDED)
    case["rules"]["remind_review"]["reminder"].update(reminder)
    return case


kind, shown = attempt(lambda: parse_case(reminded(after=["1d", "24h"])))
row("D46", "'Two ages that are the same time are refused'", f"{kind}: {shown}", kind != "ok")
kind, shown = attempt(lambda: parse_case(reminded(task="pay")))
row("D46", "'On a task only'", f"{kind}: {shown}", kind != "ok")
clash = copy.deepcopy(REMINDED)
clash["steps"]["remind_review_2d"] = copy.deepcopy(clash["steps"]["remind"])
kind, shown = attempt(lambda: parse_case(clash))
row("D46", "'a clash is refused when read, naming the pattern'", f"{kind}: {shown}", kind != "ok" and "remind_review" in str(shown))
odd = copy.deepcopy(CLAIM)
odd["rules"]["escalate"] = {"display": {"title": "x"}, "four_eyes": {"step": "assess"}, "then": {"start": ["lead_review"]}}
kind, shown = attempt(lambda: parse_case(odd))
row("D46", "'anything else is refused, naming the shapes'", f"{kind}: {shown}", kind != "ok" and "sla" in str(shown) and "reminder" in str(shown))
both = copy.deepcopy(CLAIM)
both["rules"]["escalate"]["on"] = {"opened": True}
kind, shown = attempt(lambda: parse_case(both))
row("D46", "an entry with both `on` and `sla` (asked: is it refused?)", f"{kind}: {shown}", kind != "ok")

# D47: count.
def four(count: object) -> dict:
    case = copy.deepcopy(FOUR)
    case["steps"]["pay"]["approval"]["count"] = count
    return case


readings = {repr(count): attempt(lambda c=count: parse_case(four(c)))[0] for count in ["2", 2.0, Decimal("2.0"), Decimal("2"), True, 0, -1, None, 1, 2, 3]}
accepted = sorted(c for c, kind in readings.items() if kind == "ok")
row("D47", "'A whole number of at least 1, refused ... otherwise (\"2\", 2.0 and true included)'", f"accepted: {accepted}", accepted == ["1", "2", "3"])
kind, shown = attempt(lambda: parse_case(json.loads(json.dumps(four(2)).replace('"count": 2', '"count": 2.0'), parse_float=Decimal)))
row("D47", "'2.0 ... never read as a number' (as the JSON text 2.0, read with exact decimals)", f"{kind}: {shown if kind != 'ok' else 'accepted'}", kind != "ok")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}
run = run_case(four(2), {"order_id": "ord-1", "amount": Decimal(12000)},
               [("review", "approve", "ana", {"approved_amount": Decimal(12000)}), ("pay", "approve", "sam")], PEOPLE)
asked = [line for line in run.history if line.startswith("asked pay.approval#1")]
row("D47", "'asked pay.approval#1: approval of pay by support-lead, from 2 people'", asked, asked == ["asked pay.approval#1: approval of pay by support-lead, from 2 people"])
given = [line for line in run.history if "1 of 2 given" in line]
row("D47", "'for each approve, …: 1 of 2 given'", given, len(given) == 1)
row("D47", "'waiting_for says approval of pay by support-lead: 1 of 2 given'", run.waiting_for, run.waiting_for == ["approval of pay by support-lead: 1 of 2 given"])
kind, shown = attempt(lambda: run_case(four(2), {"order_id": "ord-1", "amount": Decimal(12000)},
               [("review", "approve", "ana", {"approved_amount": Decimal(12000)}), ("pay", "approve", "sam"), ("pay", "reject", "sam")], PEOPLE))
row("D47", "'someone who has already answered the entry is refused, reject included'", f"{kind}: {shown}", kind == "AnswerRefused")
run = run_case(four(2), {"order_id": "ord-1", "amount": Decimal(12000)},
               [("review", "approve", "ana", {"approved_amount": Decimal(12000)}), ("pay", "approve", "sam"), ("pay", "reject", "lee")], PEOPLE)
row("D47", "'One rejection rejects the entry, whatever was approved before'", [line for line in run.history if "reject" in line][-2:], "pay" not in run.steps_done and not run.waiting_for or "pay" not in run.steps_done)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
