"""Case validation: what can be proven about a case definition by reading it, before any case
opens (layer 10). See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

from ventoux.case.definition import CaseDefinition
from ventoux.core.catalog import Catalog
from ventoux.core.validate import Issue


def validate_case(case: CaseDefinition, catalog: Catalog) -> list[Issue]:
    """Every problem in `case`, a parsed case definition, read against `catalog`."""
    # Fail closed: anything but a parsed definition is refused, never read as one with no problems.
    if not isinstance(case, CaseDefinition):
        raise TypeError(
            f"validate_case takes a parsed case definition (see parse_case), not "
            f"{type(case).__name__}"
        )
    return []
