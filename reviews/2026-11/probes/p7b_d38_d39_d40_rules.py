# Shows, claim by claim, whether D38 (moments, order, untrusted data never decides), D39 (rules that start steps) and D40 (rules that stop steps) are what the code does, on the in-memory runtime.
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.definition import parse_case  # no public door reads a stored definition alone
from ventoux.case.validate import validate_case  # the check `ventoux check` runs; not in public.json
from ventoux.core.contract_hash import contract_hash  # not public: the hash a release records
from ventoux.testing import CATALOG, close, finish, kyc_check, later, propose, retry, run_case

ROWS: list[tuple[str, str, str, bool]] = []
PEOPLE = {"ana": ["support"], "sam": ["support"], "lee": ["support-lead"], "olga": ["operations"]}
REFUND = json.loads(Path("examples/refund/refund.json").read_text(), parse_float=Decimal)


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
            "order_id": titled("Order", type="reference", system="orders"),
        },
        "milestones": {"big": titled("Big"), "seen": titled("Seen")},
        "steps": {
            "review": titled("Review", kind="task", roles=["support"], outcomes={"approve": titled("A"), "reject": titled("R")}),
            "two": titled("Two", kind="task", roles=["support"], outcomes={"done": titled("Done", sets=["second"])}),
            "follow": titled("Follow", kind="task", roles=["support"], automatic=False, repeatable=True, proposed_by=["support"], outcomes={"done": titled("Done")}),
        },
        "rules": {name: {"display": {"title": name}, **rule} for name, rule in rules.items()},
    }
    if edit:
        edit(case)
    return case


FILE = {"note": "ZZNOTE", "amount": Decimal(5), "order_id": "o-1"}
APPROVED = ("review", "approve", "ana")


def issues(definition: dict) -> list[tuple[str, str]] | str:
    try:
        found = validate_case(parse_case(copy.deepcopy(definition)), CATALOG)
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
    return [line for line in found if any(word in line for word in words)]


def boom(inputs: dict) -> dict:
    raise RuntimeError("ZZBOOM")


# D38
shapes = {"opened": "opened", "started": {"started": "review"}, "reached": {"reached": "big"}, "answered": {"answered": "review"},
          "event": {"event": "cancelled"}, "after": {"after": "1d", "since": "opened"}}
def with_event(case: dict) -> None:
    case["events"] = {"cancelled": titled("Cancelled", sent_by={"system": "portal"}, payload={"why": titled("Why", type="string")})}
    case["steps"]["review"]["outcomes"]["approve"]["reaches"] = ["big"]
read = {name: not str(issues(probe_case(with_event, x={"on": on, "then": {"start": ["follow"]}}))).startswith("refused") for name, on in shapes.items()}
unknown = issues(probe_case(x={"on": {"finished": "review"}, "then": {"reach": ["big"]}}))
row("D38", "'Three moments, a closed list' + D39's 'a task answered' + D41's event + D44's timer: six, and any other refused", f"read: {read}; {{'finished': ...}}: {unknown}",
    all(read.values()) and str(unknown).startswith("refused") and str(unknown).count("{") == 5)

order = probe_case(b_rule={"on": "opened", "then": {"reach": ["big"]}}, a_rule={"on": "opened", "then": {"reach": ["seen"]}}, c_rule={"on": {"reached": "seen"}, "then": {"start": ["follow"]}})
fired = [line.split(":")[0] for line in lines(history(order, []), "_rule#")]
row("D38", "'the rules on one moment in the definition's order; a milestone a rule reaches is a moment too'; 'Each firing is an entry (flag_high_risk#1)'", fired,
    fired == ["b_rule#1 on opened", "a_rule#1 on opened", "c_rule#1 on reached seen"])
for kind, name in (("step", "review"), ("milestone", "big")):
    shown = issues(probe_case(**{name: {"on": "opened", "then": {"reach": ["seen"]}}}))
    row("D38", f"'a rule's name is unlike any step's or milestone's' (a rule named as a {kind})", shown, str(shown).startswith("refused") and "not named like" in str(shown))

unreadable = probe_case(flag={"on": {"answered": "review"}, "when": {">": [{"var": "second"}, 1]}, "then": {"reach": ["big"]}})
found = history(unreadable, [APPROVED])
row("D38", "'A rule that can't be read needs attention: it acts on nothing, keeps the case open ... Never read as false'", found[-2:],
    "flag#1 failed" in found[-2] and "open; needs attention: [\"flag#1" in found[-1] and "reached big" not in found)
found = history(unreadable, [APPROVED, ("two", "done", "sam", {"second": Decimal(3)}), retry("flag#1", "olga")])
row("D38", "'an operator retries it, reading its condition again'", found[-5:], "olga retried flag#1 as operations" in found and "reached big" in found)

untrusted = probe_case(flag={"on": {"answered": "review"}, "when": {"==": [{"var": "note"}, "go"]}, "then": {"reach": ["big"]}})
found = history(untrusted, [APPROVED], file={**FILE, "note": "go"})
said = lines(found, "flag#1")
row("D38", "'if its condition reads a value from an untrusted: source it doesn't act, and says which value and source, never the value' + UNTRUSTED_TRIGGER", f"validation: {issues(untrusted)}; run: {said}",
    ("UNTRUSTED_TRIGGER", "error") in issues(untrusted) and "reached big" not in found and "note, from untrusted:customer" in said[0] and '"go"' not in said[0])

never = probe_case(flag={"on": {"reached": "seen"}, "then": {"reach": ["big"]}})
row("D38", "'a rule whose moment can never come ... is an error (NEVER_FIRES)'", issues(never), ("NEVER_FIRES", "error") in issues(never))
closing = probe_case(lambda case: case.update(closes_when=["big"]), fin={"on": "opened", "then": {"reach": ["big"]}}, late={"on": {"reached": "big"}, "then": {"reach": ["seen"]}})
found = history(closing, [])
said = lines(found, "late#1")
row("D38", "'Rules stop with the close ... no rule acts, including one on the moment that completed it; each such firing is recorded with why' (and NEVER_FIRES for 'comes only once every closes_when milestone is reached')",
    f"validation: {issues(closing)}; run: {said}; {found[-1]}", ("NEVER_FIRES", "error") in issues(closing) and "not applied" in said[0] and "reached seen" not in found and "[closed" in found[-1])
by_person = probe_case(lambda case: case.update(close_reasons={"withdrawn": titled("W", roles=["support"])}), late={"on": {"answered": "review"}, "then": {"start": ["follow"]}})
found = history(by_person, [close("withdrawn", "ana"), APPROVED])
row("D38", "'a person's close does the same' (an answer sent after a person closed the case)", found[-3:], not lines(found, "started follow"))

# D39
def start_rule(edit: Any = None, start: tuple[str, ...] = ("follow",)) -> dict:
    return probe_case(edit, s={"on": {"answered": "review"}, "then": {"start": list(start)}})
recorded = {
    "its requirements aren't met": (start_rule(lambda case: case["steps"]["follow"].update(requires=["two"])), [APPROVED], "follow requires two", {}),
    "its `when` is false": (start_rule(lambda case: case["steps"]["follow"].update(when={">": [{"var": "amount"}, 100]})), [APPROVED], "is false", {}),
    "it is running": (start_rule(start=("two",)), [APPROVED], "already running", {}),
    "it has run and isn't repeatable": (start_rule(start=("review",)), [APPROVED], "not repeatable", {}),
    "it is waiting for its approval": (start_rule(lambda case: case["steps"].update(look=titled("Look", kind="activity", activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}}, repeatable=True, proposed_by=["support"], approval={"roles": ["support-lead"], "display": {"reason": "r"}})), start=("look",)), [APPROVED], "approval", {}),
    "its latest run needs attention": (start_rule(lambda case: case["steps"].update(look=titled("Look", kind="activity", activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}}, repeatable=True, proposed_by=["support"])), start=("look",)), [APPROVED], "needs attention", {"activities": {"orders.lookup@1": boom}}),
}
for reason, (definition, answers, word, given) in recorded.items():
    found = history(definition, answers, **given)
    said = lines(found, "s#1")
    row("D39", f"'A start the engine can't make is never silent. It is recorded, and nothing runs, when ... {reason}'", said, len(said) == 1 and "not started" in said[0] and word in said[0])
contract_missing = start_rule(lambda case: case["steps"].update(look=titled("Look", kind="activity", activity="orders.nope@1", inputs={}, automatic=False)), start=("look",))
found = history(contract_missing, [APPROVED])
row("D39", "'it fails, needing attention, as admission does, when ... its contract is missing'", found[-2:], "needs attention: [\"look#1" in found[-1] or "needs attention: ['look#1" in found[-1])

def fresh(case: dict) -> None:
    case["steps"]["lookup"] = titled("Look", kind="activity", activity="orders.lookup@2", inputs={"order_id": {"var": "order_id"}})
    case["steps"]["chase"] = titled("Chase", kind="activity", activity="letters.draft@2", inputs={"to_customer": {"var": "lookup.status"}, "template": "t"},
                                    automatic=False, repeatable=True, proposed_by=["support"], requires=["lookup"], max_age={"lookup.status": "1d"})
LOOKS = {"orders.lookup@2": lambda inputs: {"status": "shipped"}}
waits = probe_case(fresh)
found = history(waits, [later("3d"), propose("chase", "ana")], activities=LOOKS)
tail = found[found.index("ana proposed chase as support"):]
row("D39", "'A step a person proposes whose stale fact can be fetched again is accepted and waits: the fact is fetched, then admission reads everything again on the fresh value, and starts the step'", tail[:5],
    len(tail) > 4 and "refreshing lookup.status" in tail[1] and "scheduled lookup#2" in tail[2] and "scheduled chase#1" in tail[4])
found = history(waits, [finish("lookup#1"), later("3d"), propose("chase", "ana"), propose("chase", "sam")], activities=LOOKS, held=["lookup"])
row("D39", "'A proposal of a step whose start already waits is refused' (the refresh held running, a second person proposes)", found[-1], found[-1].startswith("refused, ProposalRefused"))
found = history(waits, [finish("lookup#1"), later("3d"), propose("chase", "ana"), finish("lookup#2")], activities=LOOKS, held=["lookup"])
row("D39", "(the same, the held refresh then landing: the waiting start runs)", found[-4:], bool(lines(found, "scheduled chase#1")))
def stale_opening(case: dict) -> None:
    fresh(case)
    case["steps"]["chase"]["max_age"] = {"amount": "1d"}
    case["steps"]["chase"]["when"] = {">": [{"var": "amount"}, 1]}
found = history(probe_case(stale_opening), [later("3d"), propose("chase", "ana")], activities=LOOKS)
row("D39", "'one whose stale fact can't be fetched again is refused, saying why'", found[-1], found[-1].startswith("refused, ProposalRefused") and "can't be fetched again" in found[-1])
def stale_for_rule(case: dict) -> None:
    fresh(case)
    case["steps"]["chase"]["proposed_by"] = []
found = history(probe_case(stale_for_rule, s={"on": {"answered": "review"}, "then": {"start": ["chase"]}}), [later("3d"), APPROVED], activities=LOOKS)
row("D39", "'A rule's start doesn't wait': it fails on 'a fact it needs fresh [that] is stale, whether or not it could be fetched again'", found[-2:], "chase#1 failed" in found[-2] and not lines(found, "refreshing"))
found = history(probe_case(stale_for_rule, s={"on": {"answered": "review"}, "then": {"start": ["chase"]}}), [later("3d"), APPROVED, retry("chase#1", "olga")], activities=LOOKS)
row("D39", "'an operator's retry fetches it again'", found[-5:-1], bool(lines(found, "scheduled lookup#2")) and bool(lines(found, "scheduled chase#1")))

def failing(case: dict) -> None:
    case["steps"]["look"] = titled("Look", kind="activity", activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}}, repeatable=True, proposed_by=["support"])
found = history(probe_case(failing), [propose("look", "sam")], activities={"orders.lookup@1": boom})
row("D39", "'Nothing starts beside a failed run ... not started again, by a rule or a person's proposal' (a person's proposal)", found[-1], found[-1].startswith("refused, ProposalRefused") and "needs attention" in found[-1])

again = probe_case(s1={"on": {"answered": "review"}, "then": {"start": ["follow"]}}, s2={"on": {"answered": "review"}, "then": {"stop": ["follow"]}}, s3={"on": {"answered": "review"}, "then": {"start": ["follow"]}})
found = history(again, [APPROVED])
said = lines(found, "s1#1", "s2#1", "s3#1")
row("D39", "'A step a rule has started in a decision isn't started again by a rule in it (recorded)'", said[-1], "a rule already started it in this decision" in said[-1])
row("D38/D40", "ASKED, not a promise in these words: with rules written start (s1), stop (s2), start (s3) on one moment, does s1's start act before s2's stop? ('the rules on one moment in the definition's order'; 'admission runs again after')",
    f"order in the history: {[line.split(':', 1)[0].split('#')[0] + ':' + line.split(': ', 1)[1][:28] for line in said]}; follow is left {'open' if 'follow by support' in found[-1] else 'not open'}", True)

never_starts = probe_case(s={"on": {"started": "review"}, "then": {"start": ["review"]}})
row("D39", "'a start refused every time it fires is an error at the rule (NEVER_STARTS)'", issues(never_starts), ("NEVER_STARTS", "error") in issues(never_starts))
def loop(**more: Any) -> dict:
    return {"case": "loop", "display": {"title": "Loop"}, "steps": {"a": titled("A", kind="task", roles=["support"], repeatable=True, outcomes={"done": titled("Done")})},
            "rules": {"again": titled("again", on={"answered": "a"}, then={"start": ["a"]})}, **more}
def message(definition: dict, code: str) -> str:
    return next((issue.message for issue in validate_case(parse_case(definition), CATALOG) if issue.code == code), "")
row("D39", "'NEVER_CLOSES' for a loop nothing can end; 'when its definition allows forgetting and a role that forgets is registered, that only a forget request would; otherwise, that nothing could'",
    f"{issues(loop())}: ...{message(loop(), 'NEVER_CLOSES')[60:190]} | forgetting never: ...{message(loop(forgetting='never'), 'NEVER_CLOSES')[100:180]}",
    issues(loop()) == [("NEVER_CLOSES", "error")] and "nothing but a forget request could close it" in message(loop(), "NEVER_CLOSES") and "nothing could ever close it" in message(loop(forgetting="never"), "NEVER_CLOSES"))
closable = loop(close_reasons={"withdrawn": titled("W", roles=["support"])})
found = history(closable, [("a", "done", "ana"), ("a", "done", "ana"), close("withdrawn", "ana")], file={})
row("D39", "'The same loop when a close reason ... can still close the case is a warning, LOOPS_UNTIL_CLOSED'", f"{issues(closable)}; run: {lines(found, 'again#', 'closed')[-3:]}",
    issues(closable) == [("LOOPS_UNTIL_CLOSED", "warning")] and bool(lines(found, "again#2")) and "[closed" in found[-1])

asks = copy.deepcopy(REFUND)
asks["fields"]["note"] = titled("Note", type="string", source="untrusted:customer")
asks["steps"]["pay"]["approval"]["when"] = {"and": [{"==": [{"var": "note"}, "big"]}, {">": [{"var": "approved_amount"}, 100]}]}
found = history(asks, [("review", "approve", "ana", {"approved_amount": Decimal(40)})], file={"order_id": "o-1", "amount": Decimal(40), "note": "small"})
said = lines(found, "asked pay.approval")
row("D39", "'An approval's when that read untrusted data asks anyway ... the approval is asked whatever it gave, saying why'", said, len(said) == 1 and "untrusted data can't remove an approval" in said[0] and "small" not in said[0])
unsent = probe_case(lambda case: case["steps"].update(draft=titled("Draft", kind="activity", activity="letters.draft@2", inputs={"to_customer": "a@b", "template": "t"}, automatic=False)),
                    s={"on": {"answered": "review"}, "when": {"==": [{"var": "note"}, "go"]}, "then": {"start": ["draft"]}})
found = history(unsent, [APPROVED], file={**FILE, "note": "go"})
row("D39", "'if ... the when of the rule that started it, read an untrusted ... source, each input whose policy refuses that source is refused, and the run fails naming the condition's field and source, never the value'",
    f"validation: {issues(unsent)}; run: {found[-2]}", ("INPUT_POLICY", "error") in issues(unsent) and "draft#1 failed" in found[-2] and "note" in found[-2] and "untrusted:customer" in found[-2] and '"go"' not in found[-2])

# D40
def owed(case: dict) -> None:
    case["fields"]["owed"] = titled("Owed", type="number")
one_then = probe_case(owed, all={"on": {"answered": "review"}, "then": {"start": ["follow"], "reach": ["big"], "set": {"owed": {"+": [{"var": "amount"}, 1]}}, "stop": ["two"]}})
found = history(one_then, [APPROVED])
said = [line.split(": ", 1)[1].split(" ")[0] for line in lines(found, "all#1")]
row("D40/D42", "'Inside one then, the stop acts first, then [set, then] reach, then start'", said, [word for word in said if word in ("stopping", "setting", "reaching", "starting")] == ["stopping", "setting", "reaching", "starting"])
shown = issues(probe_case(x={"on": "opened", "then": {"stop": ["follow"], "start": ["follow"]}}))
row("D40", "'One name in both stop and start of a rule is refused'", shown, str(shown).startswith("refused") and "both stopped and started" in str(shown))
shown = issues(probe_case(x={"on": "opened", "then": {"stop": ["big"]}}))
row("D40", "'stop ... lists steps, and refuses any other name'", shown, str(shown).startswith("refused"))
stops_task = probe_case(x={"on": {"answered": "review"}, "then": {"stop": ["two"]}}, y={"on": {"answered": "review"}, "then": {"stop": ["two", "follow"]}})
found = history(stops_task, [APPROVED])
row("D40", "'An open task is cancelled, saying why' and 'a stop with nothing to stop, or already asked, is recorded and does nothing else'", lines(found, "two#1", "not stopped")[-3:],
    bool(lines(found, "cancelled two#1")) and len(lines(found, "not stopped")) == 2)
def halted(case: dict) -> None:
    case["steps"]["look"] = titled("Look", kind="activity", activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}})
halts = probe_case(halted, halt={"on": {"answered": "review"}, "then": {"stop": ["look"]}})
found = history(halts, [APPROVED], activities={"orders.lookup@1": boom})
row("D40", "'A failed run is never stopped'", found[-2:], "a failed run is never stopped" in found[-2] and "needs attention: [\"look#1" in found[-1].replace("'look", '"look'))
found = history(halts, [APPROVED, finish("look#1")], activities={"orders.lookup@1": boom}, held=["look"])
row("D40", "'a run that fails after its stop was requested is a failure like any other ... never cancelled'", found[-3:], "look#1 failed after its stop was requested" in found[-2] and "look#1" in found[-1] and "cancelled look#1" not in found)
found = history(halts, [APPROVED, finish("look#1")], held=["look"])
row("D40", "'A running activity ... finishes, marked \"stop requested\"; done, it is recorded as done and flagged'", found[-4:-1], bool(lines(found, "look#1: stop requested")) and bool(lines(found, "flagged: look#1 completed after its stop")))
cant_stop = probe_case(x={"on": {"answered": "review"}, "when": {"==": [{"var": "note"}, "go"]}, "then": {"stop": ["two"]}})
found = history(cant_stop, [APPROVED], file={**FILE, "note": "go"})
row("D40", "'A rule whose condition reads an untrusted source stops nothing, and says which value and source, never the value; ... UNTRUSTED_TRIGGER covers a rule that stops'", f"validation: {issues(cant_stop)}; run: {lines(found, 'x#1')}",
    ("UNTRUSTED_TRIGGER", "error") in issues(cant_stop) and "stops nothing" in lines(found, "x#1")[0] and "two by support" in found[-1])
plain, declared_false, declared_true = contract_hash(kyc_check), contract_hash(kyc_check.model_copy(update={"cancellable": False})), contract_hash(kyc_check.model_copy(update={"cancellable": True}))
row("D40", "'cancellable ... Left out of the hash when false, declared or not, so existing contracts keep their hashes'", f"not declared == declared false: {plain == declared_false}; declared true differs: {plain != declared_true}", plain == declared_false and plain != declared_true)

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
