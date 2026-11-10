# Shows, claim by claim, whether D42 (rules that set fields), D43 (a steered run, on a plain activity step), D48 (the shapes refused for now, KEPT_FROM_STARTING) and D49 (a plan's path) are what the code does.
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.case.validate import validate_case  # the check `ventoux check` runs; not in public.json
from ventoux.core.plan import parse_plan  # not public
from ventoux.core.validate import validate as validate_plan  # the plan's own check; not public
from ventoux.testing import CATALOG, later, retry, run_case

ROWS: list[tuple[str, str, str, bool]] = []
PEOPLE = {"ana": ["support"], "sam": ["support"], "lee": ["support-lead"], "olga": ["operations"]}
REFUND = json.loads(Path("examples/refund/refund.json").read_text(), parse_float=Decimal)
PLAN = json.loads(Path("docs/guides/plans.md").read_text().split("```json\n")[1].split("```")[0], parse_float=Decimal)


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:420], agrees))


def titled(title: str, **more: Any) -> dict:
    return {"display": {"title": title}, **more}


def probe_case(edit: Any = None, **rules: dict) -> dict:
    case: dict = {
        "case": "probe", "display": {"title": "Probe"},
        "fields": {
            "note": titled("Note", type="string", source="untrusted:customer"),
            "amount": titled("Amount", type="number"),
            "second": titled("Second", type="number"),
            "owed": titled("Owed", type="number"),
            "seen": titled("Seen", type="string"),
            "national_id": titled("National ID", type="string", sensitive=True, visible_to=["claims-sensitive"]),
            "score": titled("Score", type="number", visible_to=["fraud"]),
            "tags": titled("Tags", type="list", fields={"tag": {"type": "string"}}),
            "order_id": titled("Order", type="reference", system="orders"),
        },
        "milestones": {"big": titled("Big"), "looked": titled("Looked"), "confirmed": titled("Confirmed")},
        "steps": {
            "review": titled("Review", kind="task", roles=["support"], outcomes={"approve": titled("A"), "reject": titled("R")}),
            "two": titled("Two", kind="task", roles=["support"], outcomes={"done": titled("Done", sets=["second"])}),
        },
        "rules": {name: {"display": {"title": name}, **rule} for name, rule in rules.items()},
    }
    if edit:
        edit(case)
    return case


FILE = {"note": "ZZNOTE", "amount": Decimal(5), "order_id": "o-1"}
APPROVED = ("review", "approve", "ana")


def issues(definition: dict, **given: Any) -> list[tuple[str, str]] | str:
    try:
        found = validate_case(parse_case(copy.deepcopy(definition)), CATALOG, **given)
    except Exception as error:
        return f"refused when read: {' '.join(str(error).split())}"
    return [(issue.code, issue.severity) for issue in found if issue.code != "UNREACHABLE_MILESTONE"]


def history(definition: dict, answers: list, file: dict = FILE, **given: Any) -> list[str]:
    try:
        run = run_case(copy.deepcopy(definition), file, answers, PEOPLE, **given)
    except Exception as error:
        return [f"refused, {type(error).__name__}: {error}"]
    return [*run.history, f"[{run.status}; needs attention: {run.needs_attention}; waiting for {run.waiting_for}]"]


def lines(found: list[str], *words: str) -> list[str]:
    """The history's lines holding one of `words`; never the probe's own last line, in brackets."""
    return [line for line in found if any(word in line for word in words) and not line.startswith("[")]


def refused_when_read(decision: str, claim: str, definition: dict, word: str) -> None:
    shown = issues(definition)
    row(decision, claim, shown, str(shown).startswith("refused when read") and word in str(shown))


# D42
sets_owed = {"on": "opened", "then": {"set": {"owed": {"+": [{"var": "amount"}, 1]}}}}
refused_when_read("D42", "'One kind of writer per field ... set by people's forms, or set by rules: never two of these'",
                  probe_case(x={"on": "opened", "then": {"set": {"second": {"var": "amount"}}}}), "set by a person")
found = history(probe_case(x=sets_owed), [], file={**FILE, "owed": Decimal(1)})
row("D42", "'A field is given at the opening ... or set by rules: never two' (a rule-set field given at the opening)", found[-1], found[-1].startswith("refused, CaseRefused"))
refused_when_read("D42", "'A rule that reads nothing sets nothing: refused when the definition is read'", probe_case(x={"on": "opened", "then": {"set": {"owed": 5}}}), "reads no field")
refused_when_read("D42", "'A value computed from a sensitive field is set only on a sensitive field' (in the value)",
                  probe_case(x={"on": "opened", "then": {"set": {"owed": {"if": [{"==": [{"var": "national_id"}, "x"]}, 1, 2]}}}}), "sensitive")
refused_when_read("D42", "'... the condition included' (the sensitive field read only by the rule's when)",
                  probe_case(x={"on": "opened", "when": {"==": [{"var": "national_id"}, "x"]}, "then": {"set": {"owed": {"var": "amount"}}}}), "sensitive")
refused_when_read("D42", "'A set field is seen by no role that can't see every field it was computed from'", probe_case(x={"on": "opened", "then": {"set": {"owed": {"var": "score"}}}}), "only fraud sees")
refused_when_read("D42/D48", "'A list field is never set yet' / 'a list field set by a rule'", probe_case(x={"on": "opened", "then": {"set": {"tags": {"var": "tags"}}}}), "list")
refused_when_read("D42", "'set writes fields of the case file, never a step's outputs or outcome'", probe_case(x={"on": "opened", "then": {"set": {"review.outcome": {"cat": [{"var": "seen"}, "x"]}}}}), "")

constant = probe_case(x={"on": {"answered": "review"}, "when": {"==": [{"var": "note"}, "go"]}, "then": {"set": {"owed": {"var": "amount"}}}})
said = lines(history(constant, [APPROVED], file={**FILE, "note": "go"}), "x#1")
row("D42", "'a constant set under an untrusted condition is untrusted'; 'every write is a line of history naming the field and its sources, never the value'; 'A rule that only sets acts on untrusted data'", said,
    len(said) == 1 and "setting owed, from system:opener, untrusted:customer" in said[0] and " 5" not in said[0])

two_rules = probe_case(a={"on": {"answered": "review"}, "then": {"set": {"owed": {"var": "amount"}}}},
                       b={"on": {"answered": "review"}, "then": {"set": {"owed": {"+": [{"var": "amount"}, {"var": "second"}]}}}})
run = run_case(copy.deepcopy(two_rules), FILE, [later("2d"), ("two", "done", "sam", {"second": Decimal(3)}), later("1d"), APPROVED], PEOPLE)
said = lines(run.history, "setting owed")
row("D42", "'Two rules setting one field in one decision set it in order ...; the latest stands and both are recorded'", f"{said}; owed is {run.state.values['owed']}",
    [line.split("#")[0] for line in said] == ["a", "b"] and run.state.values["owed"] == Decimal(8))
obtained = {name: run.state.obtained[name].at for name in ("amount", "second", "owed")}  # reaches into the state: no public door gives a value's age but the approval sheet
row("D42", "'A computed value was obtained when the oldest fact it read was, by the rule's firing, never \"now\"' (amount from the opening, second two days later, the rule firing on day 3)",
    f"seconds since the opening: {({name: at - obtained['amount'] for name, at in obtained.items()})}; by {run.state.obtained['owed'].run}", obtained["owed"] == obtained["amount"] and run.state.obtained["owed"].run == "b#1")

whole = probe_case(a={"on": {"answered": "review"}, "then": {"set": {"owed": {"var": "second"}}, "reach": ["big"], "stop": ["two"]}})
found = history(whole, [APPROVED])
row("D42", "'A rule acts whole or not at all: if a value it sets can't be read ... it fails and needs attention, and nothing in its then acts'", found[-2:],
    "a#1 failed" in found[-2] and "reached big" not in found and "two by support" in found[-1])

def paying(case: dict) -> None:
    case["steps"]["pay"] = titled("Pay", kind="activity", activity="payments.refund@2", requires=["review"], inputs={"order_id": {"var": "order_id"}, "amount": {"var": "owed"}},
                                  approval={"roles": ["support-lead"], "display": {"reason": "r"}})
    case["steps"]["tell"] = titled("Tell", kind="task", roles=["support"], requires=["pay"], when={"==": [{"var": "pay.outcome"}, "declined"]}, outcomes={"done": titled("d")})
writers = probe_case(paying, a={"on": "opened", "then": {"set": {"owed": {"var": "amount"}}}},
                     b={"on": {"answered": "two"}, "when": {"==": [{"var": "note"}, "go"]}, "then": {"set": {"owed": {"var": "amount"}}}})
trusted = history(writers, [APPROVED, ("pay.approval#1", "approve", "lee")])
steered = history(writers, [("two", "done", "sam", {"second": Decimal(1)}), APPROVED, ("pay.approval#1", "approve", "lee")], file={**FILE, "note": "go"})
row("D42", "'what is refused for some writers and not others is a warning, WRITER_DECIDES' (and its run: paid when rule a wrote owed, refused when rule b did)",
    f"validation: {issues(writers)}; a wrote: {lines(trusted, 'pay#1')[-1]}; b wrote: {lines(steered, 'pay#1')[-1]}",
    issues(writers) == [("WRITER_DECIDES", "warning")] and "pay#1 done" in lines(trusted, "pay#1")[-1] and "pay#1 failed" in lines(steered, "pay#1")[-1] and "untrusted:customer" in lines(steered, "pay#1")[-1])

# D43, on a plain activity step (`lookup`, whose `when` reads the customer's note).
LOOKS = {"orders.lookup@2": lambda inputs: {"status": "shipped"}}
def steered_case(edit: Any = None, **rules: dict) -> dict:
    def add(case: dict) -> None:
        case["steps"]["lookup"] = titled("Look", kind="activity", activity="orders.lookup@2", inputs={"order_id": {"var": "order_id"}}, when={"==": [{"var": "note"}, "go"]}, reaches=["looked"])
        if edit:
            edit(case)
    return probe_case(add, **rules)
GO = {**FILE, "note": "go"}
found = history(steered_case(), [], file=GO, activities=LOOKS)
row("D43", "'A steered run reaches nothing. An activity ... run that untrusted data steered is done, and its reaches aren't applied, saying why'", f"validation: {issues(steered_case())}; {lines(found, 'lookup#1')[-2:]}",
    "reached looked" not in found and "lookup#1 reaches nothing" in found[-2] and "note (untrusted:customer)" in found[-2] and ("UNTRUSTED_TRIGGER", "error") in issues(steered_case()))
row("D43", "'A steered activity's ... outcome and outputs carry what steered the run, beside their contract's ... source'", lines(found, "lookup#1 done"), "giving status from system:orders, untrusted:customer" in lines(found, "lookup#1 done")[0])
on_start = steered_case(a={"on": {"started": "lookup"}, "then": {"reach": ["big"]}}, b={"on": {"started": "lookup"}, "then": {"stop": ["two"]}},
                        c={"on": {"started": "lookup"}, "when": {"exists": "order_id"}, "then": {"set": {"seen": "yes"}}})
found = history(on_start, [], file=GO, activities=LOOKS)
row("D43", "'A rule on its started moment ...: a rule that reaches or stops doesn't act, saying what steered the start, never a value; a value it sets carries it'", [line[:90] for line in lines(found, "a#1", "b#1", "c#1")],
    "reaches nothing" in lines(found, "a#1")[0] and "stops nothing" in lines(found, "b#1")[0] and "setting seen, from system:opener, untrusted:customer" in lines(found, "c#1")[0] and "reached big" not in found)
def started_step(case: dict) -> None:
    case["steps"]["draft"] = titled("Draft", kind="activity", activity="letters.draft@2", inputs={"to_customer": "a@b", "template": "t"}, automatic=False)
found = history(steered_case(started_step, s={"on": {"started": "lookup"}, "then": {"start": ["draft"]}}), [], file=GO, activities=LOOKS)
row("D43", "'a step it starts has it checked against each input's policy'", lines(found, "draft#1")[-1:], "draft#1 failed" in lines(found, "draft#1")[-1] and "untrusted:customer" in lines(found, "draft#1")[-1])
def requiring(case: dict) -> None:
    case["steps"]["next"] = titled("Next", kind="activity", activity="orders.lookup@2", inputs={"order_id": {"var": "order_id"}}, requires=["lookup"], reaches=["big"])
found = history(steered_case(requiring), [], file=GO, activities=LOOKS)
row("D43", "'A run keeps what steered its start: ... what steered the latest done run of each step it requires'", lines(found, "next#1")[-1:], "next#1 reaches nothing: next requires lookup" in found[-2] and "reached big" not in found)
def through_a_task(case: dict) -> None:
    case["steps"]["confirm"] = titled("Confirm", kind="task", roles=["support"], requires=["lookup"], outcomes={"ok": titled("ok", reaches=["confirmed"])})
    case["steps"]["after"] = titled("After", kind="activity", activity="orders.lookup@2", inputs={"order_id": {"var": "order_id"}}, requires=["confirm"], reaches=["big"])
found = history(steered_case(through_a_task), [("confirm", "ok", "ana")], file=GO, activities=LOOKS)
row("D43", "'A person is where it ends. A task's answer, ... its reaches ... come from the person who answered' ('unless that step is a task')", lines(found, "reached", "after#1 done"),
    "reached confirmed" in found and "reached big" in found and "after#1 done, giving status from system:orders" in found)
def approved_first(case: dict) -> None:
    case["steps"]["lookup"]["approval"] = {"roles": ["support-lead"], "display": {"reason": "r"}}
found = history(steered_case(approved_first), [("lookup.approval#1", "approve", "lee")], file=GO, activities=LOOKS)
row("D43", "'An approval is not [where it ends]'", lines(found, "lookup")[-2:], "lee answered lookup.approval#1 approve as support-lead" in found and "reached looked" not in found and "untrusted:customer" in lines(found, "lookup#1 done")[0])
calls: list[int] = []
def flaky(inputs: dict) -> dict:
    calls.append(1)
    if len(calls) == 1:
        raise RuntimeError("once")
    return {"status": "shipped"}
found = history(steered_case(), [retry("lookup#1", "olga")], file=GO, activities={"orders.lookup@2": flaky})
row("D43", "'Every kind of step keeps it ... for its retry'", lines(found, "lookup#1")[-3:], "olga retried lookup#1 as operations" in found and "reached looked" not in found and "untrusted:customer" in lines(found, "lookup#1 done")[0])
def read_later(case: dict) -> None:
    case["steps"]["draft"] = titled("Draft", kind="activity", activity="letters.draft@2", requires=["lookup"], inputs={"to_customer": {"var": "lookup.status"}, "template": "t"})
found = history(steered_case(read_later), [], file=GO, activities=LOOKS)
row("D43", "(its consequence: a steered output read into an input that takes no untrusted data is refused, and case validation says INPUT_POLICY)", f"validation: {issues(steered_case(read_later))}; {lines(found, 'draft#1')[-1:]}",
    ("INPUT_POLICY", "error") in issues(steered_case(read_later)) and "draft#1 failed" in lines(found, "draft#1")[-1])

# D48
def with_event(payload: dict | None = None, sent_by: Any = None) -> dict:
    def add(case: dict) -> None:
        case["events"] = {"cancelled": titled("Cancelled", sent_by=sent_by or {"system": "portal"}, payload=payload or {"why": titled("Why", type="string")})}
    return probe_case(add, x={"on": {"event": "cancelled"}, "then": {"reach": ["big"]}})
row("D48", "(control: the event the next rows change is read)", issues(with_event()), issues(with_event()) == [])
for kind, payload in (("sensitive", titled("Why", type="string", sensitive=True)), ("list", titled("Why", type="list", fields={"tag": {"type": "string"}})), ("visible_to", titled("Why", type="string", visible_to=["fraud"]))):
    refused_when_read("D48", f"'Shapes refused for now ...: a {kind} payload field'", with_event({"why": payload}), "payload.why")
for sender in ({"system": "portal", "roles": ["support"]}, {"system": ["portal", "crm"]}, [{"system": "portal"}, {"system": "crm"}]):
    refused_when_read("D48", f"'more than one sender per event': sent_by {json.dumps(sender)}", with_event(sent_by=sender), "sent_by")
for since in ({"first_start": "review"}, "first_start"):
    refused_when_read("D48", f"'since=first_start': since {json.dumps(since)}", probe_case(x={"on": {"after": "2d", "since": since}, "then": {"reach": ["big"]}}), "since")
counted = copy.deepcopy(PLAN)
counted["states"]["approve_refund"]["approval"]["count"] = 2
try:
    shown, agrees = str(validate_plan(parse_plan(counted), CATALOG)), False
except Exception as error:
    shown, agrees = f"refused when read: {error}", "count" in str(error)
row("D48", "'count on a plan's approval'", shown, agrees)
for shape in ({"roles": [["support-lead"], ["fraud"]]}, {"approvers": [{"roles": ["support-lead"]}, {"roles": ["fraud"]}]}, {"count": 2, "roles": {"first": ["support-lead"], "second": ["fraud"]}}):
    per_approver = copy.deepcopy(REFUND)
    per_approver["steps"]["pay"]["approval"].update(shape)
    refused_when_read("D48", f"'different roles per approver': approval {json.dumps(shape)[:70]}", per_approver, "approval")
kept = probe_case(lambda case: case["steps"].update(extra=titled("Extra", kind="task", roles=["support"], when={"==": [{"var": "note"}, "go"]}, outcomes={"done": titled("d")})))
found = history(kept, [APPROVED, ("two", "done", "sam", {"second": Decimal(1)})])
said = lines(found, "extra not started")
row("D48", "'KEPT_FROM_STARTING' a warning; 'the case may close without it'; 'The history says when it happens, naming the step, the field and its source, never the value'", f"validation: {issues(kept)}; run: {said}; {found[-1]}",
    issues(kept) == [("KEPT_FROM_STARTING", "warning")] and len(said) == 1 and "note, from untrusted:customer" in said[0] and "ZZNOTE" not in said[0] and "[closed" in found[-1])

# D49
branching = copy.deepcopy(PLAN)
branching["fields"]["note"] = {"type": "string"}
branching["states"]["check_order"]["on"]["done"] = [{"when": {"==": [{"var": "note"}, "go"]}, "target": "approve_refund"}, {"target": "failed"}]
declared = copy.deepcopy(branching)
declared["fields"]["note"]["source"] = "untrusted:customer"
found_plan = [(issue.code, issue.severity) for issue in validate_plan(parse_plan(declared), CATALOG)]
row("D49", "'Plan validation refuses a transition reading a field the plan declares untrusted (UNTRUSTED_TRANSITION)'", found_plan, found_plan == [("UNTRUSTED_TRANSITION", "error")])
def settled() -> dict:
    case = copy.deepcopy(REFUND)
    del case["steps"]["pay"], case["sequence"]
    case["fields"]["note"] = titled("Note", type="string", source="untrusted:customer")
    case["steps"]["settle"] = titled("Settle", kind="plan", plan="refund-order@1", requires=["review"], when={"==": [{"var": "review.outcome"}, "approve"]},
                                     inputs={"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}, "note": {"var": "note"}})
    case["steps"]["call_customer"].update(requires=["settle"], when={"==": [{"var": "settle.outcome"}, "failed"]})
    return case
OPENING = {"order_id": "o-1", "amount": Decimal(40), "note": "go"}
REVIEWED = [("review", "approve", "ana", {"approved_amount": Decimal(40)})]
shown = issues(settled(), plans={"refund-order@1": branching})
row("D49", "'Case validation refuses a plan step's input that is untrusted whoever writes it and feeds a field a transition reads (UNTRUSTED_TRIGGER)'", shown, shown == [("UNTRUSTED_TRIGGER", "error")])
found = history(settled(), REVIEWED, file=OPENING, plans={"refund-order@1": branching})
sentence = "on done, the transition to approve_refund reads note (untrusted:customer), and untrusted data can't choose a plan's path"
row("D49", f"the refusal's sentence, with this plan's names: '{sentence}'; 'The plan step fails and needs attention'; 'The runtime refuses whether or not validation ran'", found[-2], found[-2] == f"settle#1 failed: refund-order@1 stopped: {sentence}")
later_one = copy.deepcopy(branching)
later_one["states"]["check_order"]["on"]["done"] = [{"when": {">": [{"var": "amount"}, 1]}, "target": "approve_refund"}, {"when": {"==": [{"var": "note"}, "go"]}, "target": "failed"}, {"target": "failed"}]
found = history(settled(), REVIEWED, file=OPENING, plans={"refund-order@1": later_one}, plan_answers={"settle": [("approve_refund", "approve", "lee")]})
row("D49", "'A transition that is never tried (an earlier one held) reads nothing, and refuses nothing'", found[-3:], "settle#1 done" in found and "[closed" in found[-1])
found = history(settled(), [("review", "approve", "ana", {"approved_amount": Decimal(1)})], file=OPENING, plans={"refund-order@1": later_one})
row("D49", "'it stops before reading the condition, whatever the value would give' (the earlier one false, so the untrusted one is tried)", found[-2], "the transition to failed reads note (untrusted:customer)" in found[-2])

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
