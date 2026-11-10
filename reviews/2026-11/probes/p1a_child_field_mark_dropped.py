# Shows whether a child case's field declared untrusted keeps its mark when its parent gives the value (D12, D74).
"""The child `intake` declares `summary` as `untrusted:llm`, sends it to a trusted-only input,
and has a rule that reaches a milestone on it. Opened on its own (the control), the engine adds
the mark and refuses both. Opened by a parent that gives `summary` from a trusted field, the same
child is run again. Only `ventoux.testing`, plus `parse_case` and `validate_case` for the check.
"""

from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


CHILD: dict[str, Any] = {
    "case": "intake",
    **titled("Intake"),
    "fields": {
        # The child's developer says: whatever is put here was written by a model.
        "summary": {"type": "string", **titled("Summary"), "source": "untrusted:llm"},
    },
    "milestones": {"urgent": titled("Urgent")},
    "steps": {
        "letter": {
            "kind": "activity",
            **titled("Letter"),
            "activity": "letters.draft@2",  # to_customer is trusted_only()
            "inputs": {"to_customer": {"var": "summary"}, "template": "t"},
        }
    },
    "rules": {
        "flag": {
            **titled("Flag"),
            "on": "opened",
            "when": {"==": [{"var": "summary"}, "urgent"]},
            "then": {"reach": ["urgent"]},
        }
    },
    "reports": ["summary"],
}
PARENT: dict[str, Any] = {
    "case": "claim",
    **titled("Claim"),
    "fields": {"text": {"type": "string", **titled("Text")}},
    "steps": {
        "intake": {
            "kind": "case",
            **titled("Intake"),
            "case": "intake@1",
            "inputs": {"summary": {"var": "text"}},
        },
        "reply": {
            "kind": "activity",
            **titled("Reply"),
            "activity": "letters.draft@2",
            "requires": ["intake"],
            "inputs": {"to_customer": {"var": "intake.summary"}, "template": "t"},
        },
    },
}


def show(title: str, run: Any) -> None:
    print(f"--- {title}")
    for line in run.history:
        print("   ", line)
    print("    summary's sources:", sorted(run.state.sources["summary"]))
    print(
        "    milestones:",
        sorted(run.state.milestones),
        "| needs attention:",
        len(run.needs_attention),
    )


print("=== the child opened on its own (control)")
alone = run_case(CHILD, file={"summary": "urgent"}, answers=[], people={})
show("intake", alone)

print("\n=== the same child opened by a parent, from a trusted field")
issues = validate_case(parse_case(PARENT), CATALOG, cases={"intake@1": CHILD})
print("check of the parent:")
for issue in issues:
    print(f"    {issue.severity} {issue.code} {issue.path}: {issue.message}")
run = run_case(PARENT, file={"text": "urgent"}, answers=[], people={}, cases={"intake@1": CHILD})
child = run.children["intake#1"]
show("intake, as the parent's child", child)
print("--- parent")
for line in run.history:
    print("   ", line)
print("    intake.summary's sources:", sorted(run.state.sources.get("intake.summary", ())))

marked_alone = "untrusted:llm" in alone.state.sources["summary"]
marked_child = "untrusted:llm" in child.state.sources["summary"]
sent = any(line.startswith("scheduled letter#1") for line in child.history)
replied = any(line.startswith("scheduled reply#1") for line in run.history)
check_refuses_reply = any(
    i.severity == "error" and i.path == "steps.reply.inputs.to_customer" for i in issues
)
print()
if marked_alone and not marked_child:
    print(
        "RESULT: BROKEN - a child's field declared untrusted:llm loses its mark when its parent "
        f"gives the value: the child reached {sorted(child.state.milestones)} on it, sent it to a "
        f"trusted-only input ({sent}), and the parent sent the reported value on ({replied}) "
        f"though the check claims that input is always refused ({check_refuses_reply})"
    )
else:
    print("RESULT: HELD - the child's declared mark is added to what its parent gives")
