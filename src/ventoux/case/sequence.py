"""The `sequence` shorthand: each step requires the one before it (brief, D2).

A structured workflow is a case with tight rules; `sequence` writes them for you. The definition
keeps the shorthand as written, so the diff shows it; the runtime reads the expanded `requires`.
"""

from ventoux.case.definition import CaseDefinition


def requirements(case: CaseDefinition) -> dict[str, tuple[str, ...]]:
    """What each step requires: its own `requires`, and the step before it in `sequence`."""
    required = {name: step.requires for name, step in case.steps.items()}
    for before, after in zip(case.sequence, case.sequence[1:], strict=False):
        if before not in required[after]:
            required[after] = (*required[after], before)
    return required
