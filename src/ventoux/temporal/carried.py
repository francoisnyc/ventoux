"""A case's state, written as data and read back, to cross into its next run (brief, D27).

When a case continues as new, Temporal starts a fresh run with only what the old one hands it.
The whole state crosses, and nothing else: the new run decides from it alone. Every value is
written as the exact-number converter can carry it: sources, sets in the state, become sorted
lists, and are read back as sets.
"""

from typing import Any

from ventoux.case.state import CaseState, GivenApproval, OpenApproval, StepRun


def state_as_data(state: CaseState) -> dict[str, Any]:
    """`state` as JSON-shaped data: dicts, lists, texts, numbers (exact), booleans."""
    return {
        "case": state.case,
        "values": dict(state.values),
        "sources": {name: sorted(sources) for name, sources in state.sources.items()},
        "milestones": list(state.milestones),
        "runs": [
            {
                "entry": run.entry,
                "step": run.step,
                "status": run.status,
                "reason": run.reason,
                "approved": None if run.approved is None else given_as_data(run.approved),
            }
            for run in state.runs
        ],
        "approvals": {
            step: {"entry": open.entry, "step": open.step, "seen": dict(open.seen)}
            for step, open in state.approvals.items()
        },
        "given": {step: given_as_data(given) for step, given in state.given.items()},
        "asked": dict(state.asked),
        "withdrawn": dict(state.withdrawn),
        "proposers": dict(state.proposers),
        "waiting": dict(state.waiting),  # in the order they opened: JSON keeps it
        "opened_by": state.opened_by,
        "phase": state.phase,
        "closed_because": state.closed_because,
        "flags": list(state.flags),
        "history": list(state.history),
    }


def given_as_data(given: GivenApproval) -> dict[str, Any]:
    return {"entry": given.entry, "by": given.by, "digest": given.digest}


def state_from_data(data: dict[str, Any]) -> CaseState:
    """The state `state_as_data` wrote, read back as it was."""
    return CaseState(
        case=data["case"],
        values=dict(data["values"]),
        sources={name: frozenset(sources) for name, sources in data["sources"].items()},
        milestones=list(data["milestones"]),
        runs=[
            StepRun(
                run["entry"],
                run["step"],
                run["status"],
                run["reason"],
                None if run["approved"] is None else GivenApproval(**run["approved"]),
            )
            for run in data["runs"]
        ],
        approvals={
            step: OpenApproval(open["entry"], open["step"], dict(open["seen"]))
            for step, open in data["approvals"].items()
        },
        given={step: GivenApproval(**given) for step, given in data["given"].items()},
        asked=dict(data["asked"]),
        withdrawn=dict(data["withdrawn"]),
        proposers=dict(data["proposers"]),
        waiting=dict(data["waiting"]),
        opened_by=data["opened_by"],
        phase=data["phase"],
        closed_because=data["closed_because"],
        flags=list(data["flags"]),
        history=list(data["history"]),
    )
