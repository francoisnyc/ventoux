# Shows whether the names, bounds, refusals and history wordings of D52, D66, D68 and D69 to D74 are what a case run gives.
import json
import runpy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ventoux import Case, Field, Outcome, written
from ventoux.core.expressions import check, evaluate, parse_expression  # no public door evaluates one expression
from ventoux.core.expressions import DateType, NumberType
from ventoux.testing import assign, claim, close, edit, propose, run_case

ROWS: list[tuple[str, str, str, bool]] = []
BUILT = Path("examples/builder")


def row(decision: str, claim_text: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim_text, " ".join(str(shown).split())[:300], agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:170]


def built(file: str, name: str) -> dict:
    """The JSON the builder example `file` writes for its case `name`."""
    cases = [value for value in runpy.run_path(str(BUILT / file)).values() if isinstance(value, Case)]
    for case in cases:
        data = json.loads(written(case), parse_float=Decimal)
        if data["case"] == name:
            return data
    raise LookupError(name)


PEOPLE = {"ana": ["support"], "bo": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"], "ada": ["adjuster"]}
REASONS = {"duplicate": {"display": {"title": "A duplicate"}, "roles": ["support"]}}

# D52: a change request's entry, and an edit to the value already held.
required = built("required.py", "refund")
FILE = {"order_id": "ord-1", "amount": Decimal(50)}
REVIEWED = ("review", "approve", "ana", {"approved_amount": Decimal(50)})
run = run_case(required, FILE, [REVIEWED, edit("approved_amount", Decimal(60), "bo")], PEOPLE)
proposed = [line for line in run.history if "case.change#1" in line]
row("D52", "'A request is an entry of the case, case.change#1'", proposed[:1], bool(proposed))
kind, shown = attempt(lambda: run_case(required, FILE, [REVIEWED, edit("approved_amount", Decimal(50), "bo")], PEOPLE))
row("D52", "'An edit is refused ... to the value the field already holds'", f"{kind}: {shown}", kind == "ChangeRefused")
kind, shown = attempt(lambda: run_case(required, FILE, [REVIEWED, edit("approved_amount", Decimal(60), "bo"), ("case.change#1", "approve", "bo")], PEOPLE))
row("D52", "'Never approved by its proposer'", f"{kind}: {shown}", kind != "ok")

# D72: what an owing case says, and its close line.
run = run_case(required | {"close_reasons": REASONS}, FILE, [("review", "reject", "ana")], PEOPLE)
row("D72", "'waiting_for ...: confirm, required, proposed by support'", run.waiting_for, run.waiting_for == ["confirm, required, proposed by support"])
run = run_case(required | {"close_reasons": REASONS}, FILE, [("review", "reject", "ana"), close("duplicate", "ana")], PEOPLE)
row("D72", "'its last line names what was owed (closed: duplicate, by ana; confirm not done)'", run.history[-1], run.history[-1] == "closed: duplicate, by ana; confirm not done")
conditional = json.loads(json.dumps(required, default=str), parse_float=Decimal)
conditional["steps"]["confirm"]["when"] = {"==": [{"var": "review.outcome"}, "approve"]}
kind, shown = attempt(lambda: run_case(conditional, FILE, [], PEOPLE))
row("D72", "'a required step with a condition is refused when read'", f"{kind}: {shown}", kind == "CaseInvalid")

# D69 to D71: holders.
assigned = built("assigned.py", "refund")
OPEN = {"order_id": "ord-1"}
run = run_case(assigned, OPEN, [("confirm", "confirmed", "ana"), claim("review#1", "ana"), assign("review#1", "sam", "lee")], PEOPLE, opened_by="ana")
row("D70", "'lee assigned review#1 to sam as support-lead, adding , from ana when someone held it'", run.history[-1], run.history[-1] == "lee assigned review#1 to sam as support-lead, from ana")
run = run_case(assigned, OPEN, [("confirm", "confirmed", "ana"), assign("review#1", "sam", "lee")], PEOPLE, opened_by="ana")
row("D70", "'lee assigned review#1 to sam as support-lead'", run.history[-1], run.history[-1] == "lee assigned review#1 to sam as support-lead")
row("D71", "'confirm#1 assigned to ana by its rule' (the opener)", [l for l in run.history if "by its rule" in l], "confirm#1 assigned to ana by its rule" in run.history)
kind, shown = attempt(lambda: run_case(assigned, OPEN, [("confirm", "confirmed", "ana"), assign("review#1", "sam", "lee"), ("review", "reject", "bo")], PEOPLE, opened_by="ana"))
row("D69", "'while someone holds an entry, only they may answer it ... saying who holds it and how to free it'", f"{kind}: {shown}", kind == "AnswerRefused" and "sam" in str(shown))
kind, shown = attempt(lambda: run_case(assigned, OPEN, [("confirm", "confirmed", "ana"), assign("review#1", "sam", "ana")], PEOPLE, opened_by="ana"))
row("D70", "'A role the catalog doesn't mark as assigning may not assign'", f"{kind}: {shown}", kind != "ok")
four = json.loads(Path("examples/refund/refund-four-eyes.json").read_text(), parse_float=Decimal)
BIG = [("review", "approve", "ana", {"approved_amount": Decimal(12000)})]
kind, shown = attempt(lambda: run_case(four, {"order_id": "ord-1", "amount": Decimal(12000)}, [*BIG, claim("pay.approval#1", "lee")], PEOPLE))
row("D69", "'an approval whose count is above 1 ...; a claim of one is refused, saying so'", f"{kind}: {shown}", kind == "ClaimRefused")

# D73: lists and repeated steps.
repeated = built("repeated.py", "order-return")


def lines(count: int) -> dict:
    return {"order_id": "ord-1", "email": "c@example.com", "lines": [{"sku": f"sku-{n}", "amount": Decimal(1)} for n in range(count)]}


at_100 = attempt(lambda: run_case(repeated, lines(100), [], PEOPLE))
at_101 = attempt(lambda: run_case(repeated, lines(101), [], PEOPLE))
row("D73", "'a JSON array of at most 100 records'", f"100: {at_100[0]}; 101: {at_101[0]}: {at_101[1]}", at_100[0] == "ok" and at_101[0] != "ok")
run = run_case(repeated, lines(2), [], PEOPLE)
names = [line for line in run.history if "draft_line." in line][:2]
row("D73", "'named by a number the engine gives each key (draft_line.1#1)'", names, any("draft_line.1#1" in l for l in run.history) and any("draft_line.2#1" in l for l in run.history))
kind, shown = attempt(lambda: run_case(repeated, lines(2) | {"lines": [{"sku": "a", "amount": Decimal(1), "more": "x"}]}, [], PEOPLE))
row("D73", "'each with exactly the list's declared fields'", f"{kind}: {shown}", kind != "ok")
reserved = Case("r", title="R")
kind, shown = attempt(lambda: (reserved.field("each", Field.string(), title="Each"), reserved.task("t", title="T", roles=["support"], outcomes={"done": Outcome("Done")}), run_case(reserved, {}, [], PEOPLE)))
row("D73", "'each is a reserved name'", f"{kind}: {shown}", kind != "ok")

# D74: a child case.
parent, child = built("child.py", "claim"), built("child.py", "repair")
CLAIM_FILE = {"order_id": "ord-1", "vehicle": "veh-9"}
ACCEPT = ("assess", "accept", "ana", {"payout": Decimal(900)})
run = run_case(parent, CLAIM_FILE, [ACCEPT], PEOPLE, cases={"repair@3": child})
row("D74", "'repair#1: case repair, open'", run.waiting_for, run.waiting_for == ["repair#1: case repair, open"])
run = run_case(parent | {"close_reasons": REASONS}, CLAIM_FILE, [ACCEPT, close("duplicate", "ana")], PEOPLE, cases={"repair@3": child})
last = run.children["repair#1"].history[-1]
row("D74", "'closed by its parent: duplicate, by ana'", last, "by its parent: duplicate, by ana" in last)

# D68: an attachment's ID.
attached = built("attachments.py", "claim")
at_200 = attempt(lambda: run_case(attached, {}, [("assess", "accept", "ada", {"receipt": "d" * 200})], PEOPLE))
at_201 = attempt(lambda: run_case(attached, {}, [("assess", "accept", "ada", {"receipt": "d" * 201})], PEOPLE))
row("D68", "'an ID longer than 200 characters is refused before it is checked, never quoted'",
    f"200: {at_200[0]} {'' if at_200[0] == 'ok' else at_200[1]}; 201: {at_201[0]}: {at_201[1]}", at_201[0] == "AnswerRefused" and "ddd" not in at_201[1] and (at_200[0] == "ok" or "200" not in at_200[1]))

# D66: dates.
dated = built("dates.py", "claim")
REFUSED = ["2026-02-30", "2026-1-5", "20261031", "2026-W44-6", "2026-10-31T23:30:00Z", "0000-01-01", "２０２６-10-31", " 2026-10-31", "2026-10-31\n", "+2026-10-31"]
wrongly = [text for text in REFUSED if attempt(lambda t=text: run_case(dated, {"policy_start": t}, [], PEOPLE))[0] == "ok"]
good = [text for text in ("2026-10-31", "0001-01-01", "9999-12-31") if attempt(lambda t=text: run_case(dated, {"policy_start": t}, [], PEOPLE))[0] != "ok"]
row("D66", "'exactly YYYY-MM-DD, a real day, years 0001 to 9999; 2026-02-30, 2026-1-5, 20261031, a week date and a moment are refused'", f"accepted though listed as refused: {wrongly}; refused though a day: {good}", not wrongly and not good)
kind, shown = attempt(lambda: evaluate(parse_expression({"string": [{"var": "d"}]}), {"d": date(2026, 10, 31)}))
row("D66", "'string of a date, giving YYYY-MM-DD'", f"{kind}: {shown}", shown == "2026-10-31")
kind, shown = attempt(lambda: check(parse_expression({"+": [{"var": "d"}, 1]}), {"d": DateType()}))
row("D66", "'No date arithmetic'", f"{kind}: {shown}", kind == "ExpressionInvalid")
kind, shown = attempt(lambda: check(parse_expression({"-": [{"var": "d"}, {"date": "2026-01-01"}]}), {"d": DateType()}))
row("D66", "'No date arithmetic' (a day count)", f"{kind}: {shown}", kind == "ExpressionInvalid")
kind, shown = attempt(lambda: evaluate(parse_expression({"<": [{"var": "d"}, {"date": "2026-01-01"}]}), {"d": datetime(2025, 1, 1, 12, 0)}))
row("D66", "'never a datetime (a subclass in Python, so refused explicitly wherever a date is taken)'", f"{kind}: {shown}", kind == "ExpressionError")
kind, shown = attempt(lambda: parse_expression({"today": []}))
row("D66", "'today has no shape, so it can't be written'", f"{kind}: {shown[:60]}", kind == "ExpressionInvalid")
moment = Case("m", title="M")
day = moment.field("day", Field.date(), title="Day")
kind, shown = attempt(lambda: moment.task("t", title="T", roles=["support"], when=day < datetime(2027, 1, 1), outcomes={"done": Outcome("Done")}))
row("D66", "'The builder ... refuses a datetime'", f"{kind}: {shown}", kind != "ok")

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
