"""Ventoux's workflow runner: Temporal's sandbox, with Ventoux's own code passed through."""

from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run; a module passed
# through is imported once and shared. `core` and `case` are deterministic (the boundary test holds
# them to that), and passing them through keeps one copy of each class: a `Sensitive` the
# converter reads back is the class `case` checks for, whichever module first imported it. A
# replay uses the same runner (brief, D31). Every worker uses it: Temporal's default runner would
# import Ventoux afresh and hang the copy on the shared package (brief, D65).
SANDBOX = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules(
        "ventoux.core", "ventoux.case", "ventoux.tooling", "cryptography"
    )
)
