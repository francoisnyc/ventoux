"""The step advisor: a model names the step it thinks should run next; admission decides.

It is asked on behalf of one person, and suggests to them; they propose it, or don't (brief, D61).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from ventoux.authoring.provider import Message, Provider, ProviderFailed, Request
from ventoux.case.advising import AdvisorView, advisor_view
from ventoux.case.definition import CaseDefinition, Name
from ventoux.case.state import CaseState
from ventoux.core.catalog import Catalog

# Why admission would refuse the person's proposal of a step, or None: `proposal_refused`, in
# memory or asked of a running case.
Refused = Callable[[str], Awaitable[str | None]]


@dataclass(frozen=True)
class Shown(AdvisorView):
    """What the advisor is shown of a case, and the request that says it to the model."""

    @classmethod
    def of(cls, view: AdvisorView) -> "Shown":
        """`view`, with the request built from it alone."""
        return cls(**vars(view))

    @property
    def request(self) -> Request:
        """What the model is sent: the instructions, then what is shown, as JSON."""
        return Request(INSTRUCTIONS, (Message("user", json.dumps(self.said(), indent=2)),))

    def said(self) -> dict[str, Any]:
        """What is shown, as the JSON the model reads."""
        return {
            "case": self.case,
            "title": self.title,
            "fields": [vars(each) for each in self.fields],
            "milestones_reached": list(self.milestones),
            "latest_runs": [vars(each) for each in self.runs],
            "waiting_for": list(self.waiting_for),
            "steps_that_may_start_now": [vars(each) for each in self.steps],
        }


INSTRUCTIONS = """You advise on a case: work a team does step by step. Pick the one step, among \
those listed under steps_that_may_start_now, that should start next, or none.

You are shown the case's fields by name and kind, whether each is set, and where its value came \
from; never a value. A person decides whether to propose what you pick, and the engine checks it \
again.

Answer with one JSON object and nothing else: {"step": "<a step's name>"}, or {"step": null} if \
no step should start now."""


@dataclass(frozen=True)
class Advice:
    """What the advisor suggests: a step, or nothing and why."""

    step: str | None  # the step to suggest; None: nothing to suggest
    refused: str | None  # why nothing is suggested, or None
    by: str  # the provider that answered
    # Where a suggestion comes from: a model's answer, untrusted data, always (brief, D12).
    source: Literal["untrusted:llm"] = "untrusted:llm"

    def said(self) -> str:
        """The advice as every caller shows it, labelled with its source, so the label is never
        left off (brief, D61) (brief, D62)."""
        if self.step is not None:
            return f"Suggested by the step advisor ({self.source}): {self.step}"
        return f"The step advisor ({self.source}) suggests nothing: {self.refused}"


def shown_to_advisor(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    by: str,
    roles: frozenset[str],
    at: int,
) -> Shown:
    """What the advisor is shown of `state`, asked at `at` on behalf of `by`, who holds
    `roles`: no more than they may see, and no value at all (brief, D61)."""
    return Shown.of(advisor_view(case, catalog, state, by, roles, at))


async def advise(shown: Shown, provider: Provider, refused: Refused) -> Advice:
    """The step `provider`'s model suggests, once admission has checked it by `refused`."""
    try:
        answer = await provider.complete(shown.request)
    except ProviderFailed as failed:  # no answer is never read as one (brief, D62)
        return Advice(None, f"the step advisor gave no answer: {failed}", provider.name)
    try:
        step = step_named(answer)
    except NotOneName:
        # Nothing is guessed from it, and nothing of it is quoted: it is the model's text
        # (brief, D61).
        return Advice(None, NOT_ONE_NAME, provider.name)
    if step is None:
        return Advice(None, "the advisor has no step to suggest", provider.name)
    # Checked as the person's own proposal would be: the model picks among steps, never whether
    # one admission refuses runs (brief, D61).
    if (why := await refused(step)) is not None:
        return Advice(None, why, provider.name)
    return Advice(step, None, provider.name)


NOT_ONE_NAME = "the advisor's answer is not one step name, so it suggests nothing"


class NotOneName(Exception):
    """The model's answer is not `{"step": <a name>}` or `{"step": null}`."""


# Pydantic: checks a value against a type outside any model, here the case's own way of writing
# a name, so an answer is read by the rule the definition is.
NAME = TypeAdapter(Name)


def step_named(answer: str) -> str | None:
    """The step `answer` names, or None for `{"step": null}`; `NotOneName` for anything else:
    prose, a second key, a value that isn't a name written as the case writes names."""
    try:
        read = json.loads(unfenced(answer), object_pairs_hook=no_key_twice)
    except (ValueError, NotOneName):  # not JSON, or a key given twice
        raise NotOneName() from None
    if not isinstance(read, dict) or list(read) != ["step"]:
        raise NotOneName()
    step = read["step"]
    if step is None:
        return None
    try:
        return NAME.validate_python(step, strict=True)
    except ValidationError:
        raise NotOneName() from None


def unfenced(answer: str) -> str:
    """`answer` without the one fenced block around it, if it is one: a model often writes
    ```json on the line before and ``` on the line after."""
    text = answer.strip()
    if not (text.startswith("```") and text.endswith("```") and "\n" in text):
        return text
    inside = text[: -len("```")]
    return inside[inside.index("\n") + 1 :]


def no_key_twice(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """An object read from JSON, refusing a key given twice: Python's reader would keep the
    last one, silently."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise NotOneName()
    return dict(pairs)
