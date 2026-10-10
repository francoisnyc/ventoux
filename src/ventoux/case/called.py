"""What a step calls: its contract, looked up as its kind (layer 8d)."""

from ventoux.case.definition import CallStep, WorkflowStep
from ventoux.core.catalog import Catalog
from ventoux.core.contract import Contract


def called(catalog: Catalog, step: CallStep) -> Contract:
    """The contract `step` calls. A workflow step names a workflow contract, an activity step an
    activity contract; the other kind is refused (`NotInCatalog`), and the step fails: nothing
    guesses how to run it (brief, D29)."""
    if isinstance(step, WorkflowStep):
        return catalog.workflow(step.workflow)
    return catalog.get(step.called)


def unbound(workflow: str) -> str:
    """Why a workflow step can't start: the deployment hasn't bound its contract. Each driver
    knows its deployment's bindings; neither guesses where to run it (brief, D29)."""
    return f"{workflow} has no binding here: bind it to a workflow"
