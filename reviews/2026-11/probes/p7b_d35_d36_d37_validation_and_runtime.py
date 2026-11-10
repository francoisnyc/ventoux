# Shows, claim by claim, whether D35 (each validation error is one the runtime meets too), D36 (strict input types, where a value goes) and D37 (the four warnings, each with its run) are what the code does.
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel

from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.case.validate import validate_case  # the check `ventoux check` runs; not in public.json
from ventoux.core.catalog import Catalog  # not in public.json: a deployment's catalog is built here
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Outcome  # how a fake gives a named outcome; not public
from ventoux.core.provenance import sourced
from ventoux.testing import CATALOG, later, retry, run_case, run_plan

ROWS: list[tuple[str, str, str, bool]] = []
REFUND = json.loads(Path("examples/refund/refund.json").read_text(), parse_float=Decimal)
PLAN = json.loads(Path("docs/guides/plans.md").read_text().split("```json\n")[1].split("```")[0], parse_float=Decimal)
PLANS = {"refund-order@1": PLAN}
PEOPLE = {"ana": ["support"], "sam": ["support"], "lee": ["support-lead"], "olga": ["operations"]}
FILE = {"order_id": "o-1", "amount": Decimal(40)}
SMALL = [("review", "approve", "ana", {"approved_amount": Decimal(40)})]
BIG = [("review", "approve", "ana", {"approved_amount": Decimal(500)})]


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:330], agrees))


def changed(edit: Any, base: dict = REFUND) -> dict:
    definition = copy.deepcopy(base)
    edit(definition)
    return definition


def issues(definition: dict, **given: Any) -> list[tuple[str, str, str]]:
    found = validate_case(parse_case(copy.deepcopy(definition)), CATALOG, **given)
    return [(issue.code, issue.severity, issue.message) for issue in found]


def ran(definition: dict, file: dict, answers: list, **given: Any) -> str:
    """What the runtime does with the definition, validation never called: `run_case` only parses."""
    try:
        run = run_case(copy.deepcopy(definition), file, answers, given.pop("people", PEOPLE), **given)
    except Exception as error:
        return f"refused, {type(error).__name__}: {error}"
    if run.needs_attention:
        return f"needs attention: {run.needs_attention[0]}"
    return f"{run.status}; waiting for {run.waiting_for}; last: {run.history[-1]}"


def settled(inputs: dict, **fields: Any) -> dict:
    case = copy.deepcopy(REFUND)
    del case["steps"]["pay"], case["sequence"]
    case["fields"].update(fields)
    case["steps"]["settle"] = {
        "kind": "plan", "display": {"title": "Settle"}, "plan": "refund-order@1", "inputs": inputs,
        "requires": ["review"], "when": {"==": [{"var": "review.outcome"}, "approve"]},
    }
    case["steps"]["call_customer"].update(requires=["settle"], when={"==": [{"var": "settle.outcome"}, "failed"]})
    return case


# D35: each error and the runtime's refusal of the same definition, validation skipped.
SAME = {
    "UNKNOWN_CONTRACT": (changed(lambda d: d["steps"]["pay"].update(activity="payments.nope@9")), SMALL, "not in the catalog"),
    "UNKNOWN_INPUT": (changed(lambda d: d["steps"]["pay"]["inputs"].update(extra="x")), SMALL, "extra"),
    "MISSING_INPUT": (changed(lambda d: d["steps"]["pay"]["inputs"].pop("amount")), SMALL, "amount"),
    "ENGINE_INPUT": (changed(lambda d: d["steps"]["pay"]["inputs"].update(idempotency_key="k")), SMALL, "filled by the engine"),
    "APPROVAL_REQUIRED": (changed(lambda d: d["steps"]["pay"].pop("approval")), SMALL, "has no approval"),
    "APPROVAL_ROLE": (changed(lambda d: d["steps"]["pay"]["approval"].update(roles=["support"])), BIG + [("pay.approval#1", "approve", "sam")], "may approve no risk"),
    "UNKNOWN_ROLE": (changed(lambda d: d["steps"]["review"].update(roles=["ghost"])), SMALL, "ghost"),
    "EXPRESSION_INVALID": (changed(lambda d: d["steps"]["pay"].update(when={"==": [{"var": "review.outcome"}, "aprove"]})), SMALL, 'no outcome "aprove"'),
    "WRONG_KIND": (changed(lambda d: d["steps"]["pay"].update(activity="kyc.check@1")), SMALL, "workflow contract"),
    "UNKNOWN_SOURCE": (changed(lambda d: d["fields"]["amount"].update(source="untrusted:nobody")), SMALL, "label nobody registered"),
    "INPUT_TYPE": (changed(lambda d: d["steps"]["pay"]["inputs"].update(amount="40")), SMALL, "Decimal"),
    "UNKNOWN_PLAN": (settled({"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}}), SMALL, "no plan refund-order@1"),
}
for code, (definition, answers, said) in SAME.items():
    found = issues(definition)
    outcome = ran(definition, FILE, answers)
    stopped = (outcome.startswith("refused") or outcome.startswith("needs attention")) and said in outcome
    row("D35", f"'Every error is one the runtime would meet too': {code}", f"validation: {[c for c, _, _ in found]}; the run, unvalidated: {outcome}",
        [c for c, s, _ in found if s == "error"] == [code] and stopped)

view = run_case(changed(lambda d: d["fields"]["amount"].update(visible_to=["ghost"])), FILE, [], PEOPLE).view(["ghost"])
row("D35", "'a role nobody registered gives sight of nothing'", f"a person holding only ghost sees values {dict(view.values)}; hidden: {sorted(view.hidden)}", not view.values)

quoted = changed(lambda d: (d["steps"]["pay"]["display"].update(title="ZZTITLE"), d["steps"]["pay"]["approval"]["display"].update(reason="ZZREASON"),
                            d["steps"]["pay"].update(when={"==": [{"var": "review.outcome"}, "acept"]})))
messages = " | ".join(message for _, _, message in issues(quoted))
row("D35", "'A message may quote a literal of the definition ... Titles, an approval's reason ... never quoted'", messages,
    '"acept"' in messages and "ZZTITLE" not in messages and "ZZREASON" not in messages)
case_value = changed(lambda d: d["steps"]["pay"]["inputs"].pop("amount"))
outcome = ran(case_value, {"order_id": "ZZORDER", "amount": Decimal(987654)}, [("review", "approve", "ana", {"approved_amount": Decimal(876543)}), ("pay.approval#1", "approve", "lee")])
row("D35", "'every value from a case file [is] never quoted' (the runtime's refusal of the same)", outcome, outcome.startswith("needs attention") and not any(v in outcome for v in ("ZZORDER", "987654", "876543")))

one = changed(lambda d: d["steps"]["pay"].update(activity="payments.nope@9"))  # call_customer reads pay.outcome
found = issues(one)
row("D35", "'One cause, one issue: a step whose contract ... is missing gets one issue, and nothing that reads what it would give is reported again'", found, len(found) == 1)
twice = changed(lambda d: d["steps"]["pay"]["approval"].update(roles=["suport-lead"]))
found = issues(twice)
row("D35", "'a role already named by a structural issue (D34) isn't repeated'", [(c, m[:60]) for c, _, m in found], len(found) == 1)

# D36: strict types.
text_field = {"type": "string", "display": {"title": "Asked, as text"}}
as_text = changed(lambda d: (d["fields"].update(asked=text_field), d["steps"]["pay"]["inputs"].update(amount={"var": "asked"})))
found = issues(as_text)
outcome = ran(as_text, {**FILE, "asked": "40"}, SMALL)
row("D36", "'the text \"40\" is refused where a decimal is taken, in cases' (a text field given to payments.refund's amount)", f"validation: {[c for c, _, _ in found]}; run: {outcome}",
    "INPUT_TYPE" in [c for c, _, _ in found] and outcome.startswith("needs attention") and "Decimal" in outcome)
to_plan = settled({"order_id": {"var": "order_id"}, "amount": {"var": "asked"}}, asked=text_field)
found = issues(to_plan, plans=PLANS)
outcome = ran(to_plan, {**FILE, "asked": "40"}, SMALL, plans=PLANS)
row("D36", "'A plan checks each field the case gives it against the field's type when it starts ... Case validation refuses both first'", f"validation: {[(c, m[:70]) for c, _, m in found]}; run: {outcome}",
    "INPUT_TYPE" in [c for c, _, _ in found] and outcome.startswith("needs attention"))
try:
    shown = str(run_plan(PLAN, {"order_id": sourced("o-1", "system:opener"), "amount": sourced("40", "system:opener")}, [], people=PEOPLE).status)
    agrees = False
except Exception as error:
    shown, agrees = f"{type(error).__name__}: {error}", True
row("D36", "'... and in plans' (the plan run alone, amount given as the text \"40\")", shown, agrees)
wrong_system = settled({"order_id": {"var": "customer"}, "amount": {"var": "approved_amount"}}, customer={"type": "reference", "system": "crm", "display": {"title": "Customer"}})
found = issues(wrong_system, plans=PLANS)
outcome = ran(wrong_system, {**FILE, "customer": "c-1"}, SMALL, plans=PLANS)
row("D36", "'a reference field takes only a reference to its system' (a crm reference given where orders is taken)", f"validation: {[c for c, _, _ in found]}; run: {outcome}",
    "REFERENCE" in [c for c, _, _ in found] and outcome.startswith("needs attention"))


class Nested(BaseModel):
    inner: str


def registered(input_type: Any) -> str:
    class Out(BaseModel):
        y: str

    taken = type("Taken", (BaseModel,), {"__annotations__": {"x": input_type}})
    try:
        Catalog().register(ActivityContract(
            name="probe.takes", version=1, input=taken, output=Out, risk="low", effect="read",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None, outcomes=[], display=Display(title="t", description="t")))
    except Exception as error:
        return "refused: " + str(error).split("Value error, ")[-1][:150]
    return "accepted"


kinds = {"float": float, "Any": Any, "int": int, "a nested model": Nested, "Literal[1, 2]": Literal[1, 2], "bytes": bytes,
         "Decimal": Decimal, "str": str, "bool": bool, "Literal of texts": Literal["a", "b"], "Decimal | None": Decimal | None}
results = {name: registered(kind) for name, kind in kinds.items()}
refused = sorted(name for name, result in results.items() if result.startswith("refused"))
row("D36", "'An input takes only what a case's value can be, checked when its contract is registered ... the catalog refuses them, saying what to use instead'",
    f"refused: {refused}; e.g. {results['float']}", refused == sorted(["float", "Any", "int", "a nested model", "Literal[1, 2]", "bytes"]) and "Decimal" in results["float"])

record = changed(lambda d: d["steps"].update(record={"kind": "activity", "display": {"title": "Record"}, "activity": "ledger.post@1", "requires": ["review"], "inputs": {"amount": {"var": "amount"}}}))
found = [(c, s) for c, s, _ in issues(record)]
posted = {"ledger.post@1": lambda inputs: {"entry": "e-1"}}
by_person = ran(record, FILE, SMALL, opened_by="sam", activities=posted)
try:
    system_run = run_case(copy.deepcopy(record), FILE, SMALL, PEOPLE, activities=posted)
    by_system = "scheduled" if any(line.startswith("scheduled record#1") for line in system_run.history) else str(system_run.needs_attention)
except Exception as error:
    by_system = f"{type(error).__name__}: {error}"
row("D36", "'a refusal that holds only when a person opens it is a warning' (OPENER_DECIDES)", f"validation: {found}; a system opens: record {by_system}; a person opens: {by_person}",
    found == [("OPENER_DECIDES", "warning")] and by_system == "scheduled" and "only from opener" in by_person)

workflow = changed(lambda d: (
    d["fields"].update(national_id={"type": "string", "sensitive": True, "visible_to": ["claims-sensitive"], "display": {"title": "National ID"}}),
    d["steps"].update(check={"kind": "workflow", "display": {"title": "Check"}, "workflow": "kyc.check@1", "inputs": {"customer_id": {"var": "national_id"}}})))
found = [(c, s) for c, s, _ in issues(workflow)]
outcome = ran(workflow, {**FILE, "national_id": "ZZ-SECRET"}, [])
row("D36", "'A workflow step is never given a sensitive value, and case validation refuses one first'", f"validation: {found}; run: {outcome}",
    found == [("SENSITIVE_TO_WORKFLOW", "error")] and outcome.startswith("needs attention") and "ZZ-SECRET" not in outcome)

literal = settled({"order_id": {"var": "order_id"}, "amount": Decimal(40)})
found = [(c, s) for c, s, _ in issues(literal, plans=PLANS)]
outcome = ran(literal, FILE, SMALL, plans=PLANS)
row("D36", "'A plan field given only values written in the definition comes from nobody, so the plan refuses to start, and case validation says so first'", f"validation: {found}; run: {outcome}",
    found == [("NO_SOURCES", "error")] and "can't start" in outcome)

hidden = changed(lambda d: (
    d["fields"].update(fraud_score={"type": "number", "visible_to": ["fraud"], "display": {"title": "Fraud score"}}),
    d["steps"]["pay"].update(when={"if": [{"==": [{"var": "review.outcome"}, "approve"]}, {"<": [{"var": "fraud_score"}, 50]}, False]})))
found = [(c, s) for c, s, _ in issues(hidden)]
scored = {**FILE, "fraud_score": Decimal(3)}
alone = ran(hidden, scored, BIG + [("pay.approval#1", "approve", "lee")])
both = ran(hidden, scored, BIG + [("pay.approval#1", "approve", "lee")], people={**PEOPLE, "lee": ["support-lead", "fraud"]})
row("D36", "'An approver who can't see what they approve is a warning, never an error ... The refusal at answer time stays'",
    f"validation: {found}; lee as support-lead only: {alone}; lee holding fraud as well: {both}",
    found == [("APPROVER_CANT_SEE", "warning")] and alone.startswith("refused, AnswerRefused") and both.startswith("closed"))


# D37: the four warnings, each with the run it describes.
def declines(inputs: dict) -> dict:
    raise Outcome("declined")


unread = changed(lambda d: d["steps"].pop("call_customer"))
found = [(c, s) for c, s, _ in issues(unread)]
run = run_case(copy.deepcopy(unread), FILE, SMALL, PEOPLE, activities={"payments.refund@2": declines})
row("D37", "OUTCOME_UNREAD: 'The case goes on, and with nothing left to do closes, with nobody told'", f"validation: {found}; declined: {run.status}, {run.history[-2:]}",
    found == [("OUTCOME_UNREAD", "warning")] and run.status == "closed" and not run.needs_attention)

unset = changed(lambda d: d["steps"]["pay"].pop("when"))
found = [(c, s) for c, s, _ in issues(unset)]
outcome = ran(unset, FILE, [("review", "reject", "ana")])
row("D37", "MAY_BE_UNSET: 'reading a value nobody set fails the step'", f"validation: {found}; rejected: {outcome}", found == [("MAY_BE_UNSET", "warning")] and "has no value" in outcome)

stale = changed(lambda d: d["steps"]["pay"].update(max_age={"approved_amount": "1d"}))
found = [(c, s) for c, s, _ in issues(stale)]
outcome = ran(stale, FILE, BIG + [later("3d"), ("pay.approval#1", "approve", "lee")])
row("D37", "NEVER_REFRESHED: 'Each time it is stale, the step needs attention'", f"validation: {found}; approved three days later: {outcome}",
    found == [("NEVER_REFRESHED", "warning")] and outcome.startswith("needs attention") and "can't be fetched again" in outcome)

elsewhere = changed(lambda d: d["steps"]["pay"]["approval"].update(when={">": [{"var": "amount"}, 100]}))
found = [(c, s) for c, s, _ in issues(elsewhere)]
run = run_case(copy.deepcopy(elsewhere), FILE, BIG, PEOPLE)
asked = any(line.startswith("asked pay.approval") for line in run.history)
row("D37", "APPROVAL_ELSEWHERE: 'it guards a neighbouring value, not the one that is sent'", f"validation: {found}; 40 asked, 500 approved: approval asked: {asked}; {run.history[-2]}",
    found == [("APPROVAL_ELSEWHERE", "warning")] and not asked and run.status == "closed")

guard = {"==": [{"var": "review.outcome"}, "approve"]}
reads = {">": [{"var": "approved_amount"}, 0]}
for operator, expression, warned in (("and", {"and": [guard, reads]}, True), ("or", {"or": [{"!": [guard]}, reads]}, True), ("if", {"if": [guard, reads, False]}, False)):
    guarded = changed(lambda d: d["steps"]["pay"].update(when=expression))
    found = [(c, path) for c, _, path in ((i.code, i.severity, i.path) for i in validate_case(parse_case(copy.deepcopy(guarded)), CATALOG)) if path == "steps.pay.when"]
    outcome = ran(guarded, FILE, [("review", "reject", "ana")])
    failed = "can't be evaluated" in outcome
    row("D37", f"'inside one expression only `if` guards a branch, since `and` and `or` read every part': {operator}", f"validation at pay.when: {found}; rejected: {outcome}",
        (bool(found) and failed) if warned else (not found and not failed))

after = changed(lambda d: (d.pop("sequence"), d["steps"]["review"].update(requires=["pay"]), d["steps"]["pay"].pop("when")))
found = [(c, s) for c, s, _ in issues(after)]
first = ran(after, FILE, [])
again = ran(after, FILE, [retry("pay#1", "olga")])
row("D37", "SET_AFTER: 'a step reading, every time it starts, a value that only steps waiting for it set fails every time ... no retry ... helps'",
    f"validation: {found}; run: {first}; after an operator's retry: {again}", ("SET_AFTER", "error") in found and "has no value" in first and "has no value" in again)

quickstart = json.loads(Path("examples/quickstart/packages/refund/case.json").read_text(), parse_float=Decimal)
found = issues(quickstart)
row("D37", "'The quickstart warns about nothing'", f"examples/quickstart/packages/refund/case.json: {found}", found == [])
run = run_case(copy.deepcopy(quickstart), FILE, SMALL, PEOPLE, activities={"payments.refund@2": declines})
row("D37", "'its refund calls the customer when the provider declines, so a declined refund no longer closes the case with nobody told'", f"{run.status}; waiting for {run.waiting_for}",
    run.status == "open" and any("call_customer" in waiting for waiting in run.waiting_for))

both_issues = changed(lambda d: (d["steps"].pop("call_customer"), d["steps"]["pay"].update(activity="payments.nope@9")))
found = [(c, s) for c, s, _ in issues(both_issues)]
row("D37", "'One cause, one issue ... a step or a value an error already names gets no warning'", found, found == [("UNKNOWN_CONTRACT", "error")])

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
