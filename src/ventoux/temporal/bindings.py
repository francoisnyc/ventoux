"""Bindings: where each workflow contract runs, in this deployment (brief, D5, layer 8d).

A contract says what a workflow promises; a binding says where it runs: its workflow type and task
queue. Moving where it runs is an operations change, never a contract change. See
docs/guides/cases.md, "Running a case on Temporal".
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    """Where one workflow contract runs: `Binding(workflow="KycCheck", task_queue="kyc")`."""

    workflow: str  # the workflow type its team's worker registers, in any SDK language
    task_queue: str  # the task queue that worker polls
