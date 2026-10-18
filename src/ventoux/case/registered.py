"""Every role, source label and system a case definition names is one the platform team
registered (layer 10b): a typo is caught before any case opens. See
docs/layers/10-case-validation.md (10b).
"""

from collections.abc import Collection

from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.reach import can_start
from ventoux.core.catalog import Catalog
from ventoux.core.references import unregistered
from ventoux.core.validate import Issue, role_issues


def role_issues_of(
    case: CaseDefinition, catalog: Catalog, can: Collection[str], closing: bool = True
) -> list[Issue]:
    """Each role nobody registered, where the case names it: it counts for nothing when the case
    runs, so it answers, approves, proposes, closes and sees nothing (brief, D22). A role a
    structural issue already names isn't said again: proposed_by roles of a step nobody can start
    (`NEVER_RUNS`), given `can`, what the case can ever reach, and close reasons' when `closing`
    is False (`NEVER_CLOSES`). A step a rule may start is started by someone, so its misspelt
    `proposed_by` is said (brief, D39)."""
    issues: list[Issue] = []
    for name, step in case.steps.items():
        path = f"steps.{name}"
        if isinstance(step, TaskStep):
            issues += role_issues(f"{path}.roles", step.roles, catalog)
        if isinstance(step, CallStep) and step.approval is not None:
            issues += role_issues(f"{path}.approval.roles", step.approval.roles, catalog)
        if can_start(case, catalog, name, can):
            issues += role_issues(f"{path}.proposed_by", step.proposed_by, catalog)
    if closing:
        for name, reason in case.close_reasons.items():
            issues += role_issues(f"close_reasons.{name}.roles", reason.roles, catalog)
    for name, field in case.fields.items():
        issues += role_issues(f"fields.{name}.visible_to", field.visible_to or (), catalog)
    return issues


def source_issues_of(case: CaseDefinition, catalog: Catalog) -> list[Issue]:
    """Each field declared untrusted with a label nobody registered (brief, D12)."""
    issues: list[Issue] = []
    for name, field in case.fields.items():
        if field.source is None:
            continue
        label = field.source.removeprefix("untrusted:")  # parse_case let only `untrusted:` through
        if label not in catalog.labels:
            issues.append(
                Issue(
                    f"fields.{name}.source",
                    "UNKNOWN_SOURCE",
                    f"{field.source} has a label nobody registered: the labels are "
                    f"{', '.join(catalog.labels)}; use one of them, or ask the platform team to "
                    "register it",
                )
            )
    return issues


def system_issues_of(case: CaseDefinition, catalog: Catalog) -> list[Issue]:
    """Each reference, in a field or in a list's records, naming a system nobody registered
    (brief, D30): the runtime's own check, which refuses such a case when it opens."""
    return [
        Issue(
            f"fields.{name}",
            "UNKNOWN_SYSTEM",
            f"{problem}: the systems are {', '.join(catalog.systems)}; use one of them, or ask the "
            "platform team to register it",
        )
        for name, field in case.fields.items()
        for problem in unregistered({name: field.declared}, catalog.systems)
    ]
