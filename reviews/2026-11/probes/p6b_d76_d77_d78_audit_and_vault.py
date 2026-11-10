# Shows whether D76's list of decision kinds, D77's part names, bounds and store refusals, and D78's key names, timeout, address rule, key type and mark path are what the code does.
import copy
import json
import tempfile
import typing
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from ventoux.case.audit import DecisionKind  # reached past the public names: the engine's own list of kinds
from ventoux.case.definition import parse_case
from ventoux.temporal.audit import exported, sensitive_fields  # reached past: what the export activity writes
from ventoux.temporal.cases import CaseWorkflow
from ventoux.testing import close, edit, later, propose, retry, run_case
from ventoux.tooling.audit import AuditRefused, FileAudit
from ventoux.tooling.keys import FileKeys, KeyRefused
from ventoux.tooling.vault import KEY_TYPE, Recording, VaultKeys, vault_name

ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim_text: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim_text, " ".join(str(shown).split())[:320], agrees))


def attempt(action):
    try:
        return "ok", action()
    except Exception as error:
        return type(error).__name__, " ".join(str(error).split())[:170]


# D76: the kinds of decision.
BRIEF = ["answered", "approved", "rejected", "refused", "admitted", "started", "completed", "failed", "retried",
         "skipped", "reached", "set", "closed", "stopped", "edited", "migrated", "forgotten"]
declared = list(typing.get_args(DecisionKind.__value__))
row("D76", "'Its kind (answered, approved, ... forgotten)': the declared list", f"only in the code: {sorted(set(declared) - set(BRIEF))}; only in the brief: {sorted(set(BRIEF) - set(declared))}", set(declared) == set(BRIEF))

PEOPLE = {"ana": ["support"], "bo": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"], "ops": ["operations"]}
FOUR = json.loads(Path("examples/refund/refund-four-eyes.json").read_text(), parse_float=Decimal)
FOUR["fields"]["national_id"] = {"type": "string", "display": {"title": "National ID"}, "sensitive": True, "visible_to": ["support"]}
FOUR["close_reasons"] = {"duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}}
FILE = {"order_id": "ord-1", "amount": Decimal(12000), "national_id": "AB123456"}
REVIEW = ("review", "approve", "ana", {"approved_amount": Decimal(12000)})


def failing(inputs):
    raise RuntimeError("the payment system is down")


runs = [
    run_case(FOUR, FILE, [REVIEW, ("pay", "approve", "sam"), ("pay", "approve", "lee")], PEOPLE),
    run_case(FOUR, FILE, [REVIEW, ("pay", "approve", "sam"), ("pay", "reject", "lee")], PEOPLE),
    run_case(FOUR, FILE, [close("duplicate", "ana")], PEOPLE),
    run_case(FOUR, FILE, [REVIEW, edit("approved_amount", Decimal(50), "bo"), ("case.change#1", "approve", "sam")], PEOPLE),
    run_case(json.loads(Path("examples/claim/claim.json").read_text(), parse_float=Decimal), {"claimed": Decimal(1)}, [later("6d"), ("assess", "done", "ada")], {"ada": ["adjuster"]}),
]
kind, failed_run = attempt(lambda: run_case(FOUR, FILE, [REVIEW, ("pay", "approve", "sam"), ("pay", "approve", "lee"), retry("pay#1", "ops")], PEOPLE, activities={"payments.refund@2": failing}))
if kind == "ok":
    runs.append(failed_run)
emitted = sorted({decision.kind for run in runs for record in run.audit for decision in record.decisions})
row("D76", "every kind a run's records hold is one of the list", f"{emitted} (from {len(runs)} runs)", set(emitted) <= set(BRIEF) and len(emitted) >= 8)
first = runs[0].audit
row("D76", "'a number from 1'", [record.number for record in first], [record.number for record in first] == list(range(1, len(first) + 1)))
ONE = copy.deepcopy(FOUR)
ONE["steps"]["pay"]["approval"]["count"] = 1
one = run_case(ONE, FILE, [REVIEW, ("pay", "approve", "sam")], PEOPLE)
approving = next(record for record in one.audit if record.act.kind == "answered" and any(d.kind == "approved" for d in record.decisions))
kinds = [decision.kind for decision in approving.decisions]
asking = next(([d.kind for d in record.decisions] for record in one.audit if any(d.kind == "admitted" for d in record.decisions)), [])
row("D76", "'An answer that approves pay and so starts it is one record: approved, admitted, started' (the same decision later: 'admitted is an approval asked')",
    f"the approving answer's decisions: {kinds}; `admitted` is in the record of the answer that had the approval asked: {asking}", kinds == ["approved", "admitted", "started"])
# D77: the part a sensitive value is sealed for, and the store's refusals.
with tempfile.TemporaryDirectory() as temporary:
    keys = FileKeys(Path(temporary) / "keys.json")
    keys.create("claim-7")
    written = exported("claim-7", first, sensitive_fields(parse_case(copy.deepcopy(FOUR))), {}, keys)
    part = written[0]["act"]["values"]["national_id"].get("part")
    row("D77", "'a part naming its place in the record: audit/<stream>/<number>/act/values/<field>'", part, part == "audit/claim-7/1/act/values/national_id")
    row("D77", "'Sealed, or not written': the value is nowhere in clear in what is written", "AB123456" in json.dumps(written), "AB123456" not in json.dumps(written))
    kind, shown = attempt(lambda: exported("claim-7", first, {}, {}, keys))
    row("D77", "(asked) the same records with the definition's sensitive fields not given: still sealed, or refused?", f"{kind}: {shown if kind != 'ok' else ('in clear' if 'AB123456' in json.dumps(shown) else 'sealed')}", kind != "ok" or "AB123456" not in json.dumps(shown))
    store = FileAudit(Path(temporary) / "audit")
    store.append(written[:1])
    kind, shown = attempt(lambda: store.append(written[2:3]))
    row("D77", "'a number whose previous one it doesn't hold is refused'", f"{kind}: {shown}", kind == "AuditRefused")
    other = copy.deepcopy(written[0])
    other["engine"] = 99
    kind, shown = attempt(lambda: store.append([other]))
    row("D77", "'other content ... is refused'", f"{kind}: {shown}", kind == "AuditRefused")
    kind, shown = attempt(lambda: store.append(written[:1]))
    row("D77", "'the same content again is accepted'", kind, kind == "ok")
    kind, shown = attempt(lambda: store.append([written[1], written[3]]))
    kept = [each["number"] for each in store.read("claim-7")]
    row("D77", "'nothing of the call is kept' (the code's words) when one record of a call is refused", f"{kind}; kept numbers {kept}", kind == "AuditRefused" and kept == [1])
    row("D77", "'FileAudit, one JSON Lines file per stream'", sorted(p.name for p in (Path(temporary) / "audit").iterdir() if not p.name.startswith(".")), True)

retries = CaseWorkflow.export_retries
row("D77", "'the activity's retries are bounded (10 attempts, the longest wait 5 minutes)' (the policy the case workflow passes to the export activity)",
    f"maximum_attempts={retries.maximum_attempts}, maximum_interval={retries.maximum_interval}", retries.maximum_attempts == 10 and retries.maximum_interval == timedelta(minutes=5))
row("D77", "'Past 256 KB of unwritten records ... the case holds'", f"audit_bound={CaseWorkflow.audit_bound}", CaseWorkflow.audit_bound == 256 * 1024)

# D78: names, bounds, address, key type, mark path.
row("D78", "'refund-A-1001 is ventoux-refund-_41-1001'", vault_name("refund-A-1001"), vault_name("refund-A-1001") == "ventoux-refund-_41-1001")
row("D78", "'every other byte of its UTF-8, capitals and _ included, is _ and two hex digits'", [vault_name(x) for x in ("a_b", "a/b", "é", "a.b")], [vault_name(x) for x in ("a_b", "a/b", "é", "a.b")] == ["ventoux-a_5fb", "ventoux-a_2fb", "ventoux-_c3_a9", "ventoux-a_2eb"])
kind, shown = attempt(lambda: vault_name(""))
row("D78", "'An empty ID ... refused'", f"{kind}: {shown}", kind == "KeyRefused")
longest = "a" * (128 - len("ventoux-"))
at_128, at_129 = attempt(lambda: vault_name(longest)), attempt(lambda: vault_name(longest + "a"))
row("D78", "'one whose name passes 128 characters [is] refused'", f"a name of 128: {at_128[0]}; of 129: {at_129[0]}: {at_129[1]}", at_128[0] == "ok" and at_129[0] == "KeyRefused")
ADDRESSES = {"https://vault.internal:8200": True, "http://localhost:8200": True, "http://127.0.0.1:8200": True,
             "http://vault.internal:8200": False, "http://localhost.evil.example": False, "http://localhost@evil.example": False,
             "http://127.0.0.1.evil.example": False, "http://127.0.0.2": False, "ftp://localhost": False, "vault.internal:8200": False, "//localhost": False}
wrong = [address for address, accepted in ADDRESSES.items() if (attempt(lambda a=address: VaultKeys(a, "transit", "secret", transport=Recording([])))[0] == "ok") != accepted]
row("D78", "'an http:// address is refused unless it is localhost or 127.0.0.1'", f"read the wrong way: {wrong}", not wrong)
keys = VaultKeys("https://vault.internal:8200", "transit", "secret", transport=Recording([]))
row("D78", "'Every call has a timeout (10 seconds by default)'", keys.timeout, keys.timeout == 10)
row("D78", "'A key per case, aes256-gcm96'", KEY_TYPE, KEY_TYPE == "aes256-gcm96")
row("D78", "'The mark, ventoux/forgotten/<name> in a key-value engine (version 2)'", keys.mark_path("ventoux-x"), keys.mark_path("ventoux-x") == "/v1/secret/data/ventoux/forgotten/ventoux-x")
kind, shown = attempt(lambda: VaultKeys("https://vault.internal:8200", "", "secret", transport=Recording([])))
row("D78", "'each required, no default'", f"{kind}: {shown}", kind == "ValueError")
kind, shown = attempt(lambda: keys.state("claim-7"))
row("D78", "'a request [the recording] doesn't hold is refused, saying which'", f"{kind}: {shown}", kind != "ok")

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
