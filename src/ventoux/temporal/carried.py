"""A case's state, written as data and read back, to cross into its next run (brief, D27).

When a case continues as new, Temporal starts a fresh run with only what the old one hands it.
The whole state crosses, and nothing else: the new run decides from it alone. Every value is
written as the exact-number converter can carry it: sources, sets in the state, become sorted
lists, and are read back as sets.
"""

from decimal import Decimal
from typing import Any

from ventoux.case.state import (
    CaseState,
    GivenApproval,
    Moment,
    Obtained,
    OpenApproval,
    RuleFiring,
    RuleStart,
    StepRun,
    Timer,
)
from ventoux.core.before_activity import Steering


def state_as_data(state: CaseState) -> dict[str, Any]:
    """`state` as JSON-shaped data: dicts, lists, texts, numbers (exact), booleans."""
    return {
        "case": state.case,
        "values": dict(state.values),
        "sources": {name: sorted(sources) for name, sources in state.sources.items()},
        "obtained": {
            name: {"at": obtained.at, "run": obtained.run}
            for name, obtained in state.obtained.items()
        },
        "milestones": list(state.milestones),
        "refreshing": dict(state.refreshing),
        "runs": [
            {
                "entry": run.entry,
                "step": run.step,
                "status": run.status,
                "reason": run.reason,
                "approved": None if run.approved is None else given_as_data(run.approved),
                "refresh": run.refresh,
                "excluded": dict(run.excluded),
                "steered": [steering_as_data(steering) for steering in run.steered],
                "started": run.started,
                "stop_requested": run.stop_requested,
            }
            for run in state.runs
        ],
        "approvals": {
            step: {
                "entry": open.entry,
                "step": open.step,
                "seen": dict(open.seen),
                "count": open.count,
                "approved": dict(open.approved),  # in the order they approved: JSON keeps it
            }
            for step, open in state.approvals.items()
        },
        "given": {step: given_as_data(given) for step, given in state.given.items()},
        "asked": dict(state.asked),
        "withdrawn": dict(state.withdrawn),
        "proposers": dict(state.proposers),
        "waiting_to_start": list(state.waiting_to_start),
        "proposed_by_rules": {
            step: rule_start_as_data(asked) for step, asked in state.proposed_by_rules.items()
        },
        "arrived": dict(state.arrived),
        "waiting": dict(state.waiting),  # in the order they opened: JSON keeps it
        "opened_by": state.opened_by,
        "phase": state.phase,
        "closed_because": state.closed_because,
        "flags": list(state.flags),
        "history": list(state.history),
        "firings": [
            {
                "entry": f.entry,
                "rule": f.rule,
                "moment": f.moment,
                "status": f.status,
                "reason": f.reason,
                # What steered the start it fired on, for its retry (brief, D43).
                "steered": [steering_as_data(steering) for steering in f.steered],
            }
            for f in state.firings
        ],
        # Always empty between events (brief, D38).
        "moments": [
            {"said": m.said, "run": m.run, "entry": m.entry, "rule": m.rule} for m in state.moments
        ],
        "rule_starts": [rule_start_as_data(asked) for asked in state.rule_starts],  # the same
        "started_by_rules": list(state.started_by_rules),  # the same
        # Each timer set, with its due time: state, not running work, so it crosses as it is and
        # the new run fires it, once (brief, D27) (brief, D44).
        "timers": [
            {
                "rule": t.rule,
                "after": t.after,
                "since": t.since,
                "due": t.due,
                "run": t.run,
            }
            for t in state.timers
        ],
    }


def rule_start_as_data(asked: RuleStart) -> dict[str, Any]:
    return {
        "entry": asked.entry,
        "moment": asked.moment,
        "step": asked.step,
        "read_from": dict(asked.read_from),
        "untrusted": {name: sorted(sources) for name, sources in asked.untrusted.items()},
        "steered": [steering_as_data(steering) for steering in asked.steered],
    }


def rule_start_from_data(data: dict[str, Any]) -> RuleStart:
    return RuleStart(
        data["entry"],
        data["moment"],
        data["step"],
        dict(data["read_from"]),
        {name: frozenset(sources) for name, sources in data["untrusted"].items()},
        # None in a state from before the fix of the untrusted moment: nothing steered a moment.
        tuple(steering_from_data(steering) for steering in data.get("steered", [])),
    )


def steering_as_data(steering: Steering) -> dict[str, Any]:
    return {"said": steering.said, "sources": sorted(steering.sources)}


def steering_from_data(data: dict[str, Any]) -> Steering:
    return Steering(data["said"], frozenset(data["sources"]))


def given_as_data(given: GivenApproval) -> dict[str, Any]:
    return {
        "entry": given.entry,
        "by": given.by,
        "digest": given.digest,
        "seen": dict(given.seen),
        "also": list(given.also),
    }


def given_from_data(data: dict[str, Any]) -> GivenApproval:
    """A given approval `given_as_data` wrote; one from before 11h2 has no other approvers."""
    return GivenApproval(
        data["entry"], data["by"], data["digest"], dict(data["seen"]), tuple(data.get("also", ()))
    )


def state_from_data(data: dict[str, Any]) -> CaseState:
    """The state `state_as_data` wrote, read back as it was."""
    return CaseState(
        case=data["case"],
        values=dict(data["values"]),
        sources={name: frozenset(sources) for name, sources in data["sources"].items()},
        # A state carried by a run from before layer 9d has no times: its facts' ages are unknown,
        # so a step needing one fresh stops (docs/layers/09-case-data.md, 9d).
        obtained={
            name: Obtained(whole(obtained["at"]), obtained["run"])
            for name, obtained in data.get("obtained", {}).items()
        },
        milestones=list(data["milestones"]),
        refreshing=dict(data.get("refreshing", {})),  # none in a state from before layer 9d
        runs=[
            StepRun(
                run["entry"],
                run["step"],
                run["status"],
                run["reason"],
                None if run["approved"] is None else given_from_data(run["approved"]),
                run.get("refresh", False),  # none in a state from before layer 9d
                # None in a state from before layer 11b: no plan run kept what it started on.
                dict(run.get("excluded", {})),
                tuple(steering_from_data(steering) for steering in run.get("steered", [])),
                # None in a state from before 11b: read as started, so a retry of such a run fires
                # nothing, as it did when the state was written.
                started=run.get("started", True),
                # None in a state from before 11c: no rule could stop a run.
                stop_requested=run.get("stop_requested", ""),
            )
            for run in data["runs"]
        ],
        approvals={
            # Neither in a state from before 11h2: every approval was one person's.
            step: OpenApproval(
                open["entry"],
                open["step"],
                dict(open["seen"]),
                open.get("count", 1),
                dict(open.get("approved", {})),
            )
            for step, open in data["approvals"].items()
        },
        given={step: given_from_data(given) for step, given in data["given"].items()},
        asked=dict(data["asked"]),
        withdrawn=dict(data["withdrawn"]),
        proposers=dict(data["proposers"]),
        # None in a state from before layer 11b: no proposal waited for a fact.
        waiting_to_start=list(data.get("waiting_to_start", [])),
        # None in a state from before layer 11b: no rule started a step.
        proposed_by_rules={
            step: rule_start_from_data(asked)
            for step, asked in data.get("proposed_by_rules", {}).items()
        },
        # None in a state from before layer 11d: no event had arrived.
        arrived={name: whole(count) for name, count in data.get("arrived", {}).items()},
        waiting=dict(data["waiting"]),
        opened_by=data["opened_by"],
        phase=data["phase"],
        closed_because=data["closed_because"],
        flags=list(data["flags"]),
        history=list(data["history"]),
        # None in a state from before layer 11a: no rule had fired.
        firings=[firing_from_data(firing) for firing in data.get("firings", [])],
        moments=[
            Moment(m["said"], m["run"], m.get("entry", ""), m.get("rule", ""))
            for m in data.get("moments", [])
        ],
        rule_starts=[rule_start_from_data(asked) for asked in data.get("rule_starts", [])],
        started_by_rules=list(data.get("started_by_rules", [])),
        # None in a state from before layer 11f: no timer could be set.
        timers=[
            Timer(t["rule"], t["after"], t["since"], whole(t["due"]), t["run"])
            for t in data.get("timers", [])
        ],
    )


def firing_from_data(data: dict[str, Any]) -> RuleFiring:
    return RuleFiring(
        data["entry"],
        data["rule"],
        data["moment"],
        data["status"],
        data["reason"],
        # None in a state from before the fix of the untrusted moment: nothing steered a moment.
        tuple(steering_from_data(steering) for steering in data.get("steered", [])),
    )


def whole(number: object) -> int:
    """A time read back as the whole number it was written as: the exact-number converter reads
    every JSON number as a `Decimal` (brief, D20). Anything else is refused, never rounded."""
    if isinstance(number, bool) or not isinstance(number, int | Decimal) or number % 1 != 0:
        raise ValueError(
            f"a carried time is a whole number of seconds, not a {type(number).__name__}"
        )
    return int(number)
