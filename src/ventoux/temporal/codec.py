"""The payload codec and the failure converter: sensitive values sealed with their case's key
(layer 9b).

The converter gives each sensitive value its own part of a payload (`sensitive/0`), inside the
workflow, deterministically. This codec runs outside workflow code, where reading a key is
allowed: it has the key provider seal each part with the case's key, as `encrypted/0`, and open it
again. The rest of the payload stays readable in the Temporal UI (brief, D15) (brief, D31).
See docs/layers/09-case-data.md (9b).
"""

from collections.abc import Sequence
from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.api.failure.v1 import Failure
from temporalio.converter import (
    ActivitySerializationContext,
    DefaultFailureConverter,
    PayloadCodec,
    PayloadConverter,
    SerializationContext,
    WithSerializationContext,
    WorkflowSerializationContext,
)

from ventoux.core.sensitive import Sensitive, plain
from ventoux.tooling.keys import KeyProvider, KeyRefused

# A part's name in a payload's metadata, before the codec seals it, and after.
SENSITIVE = "sensitive/"
ENCRYPTED = "encrypted/"
# What Temporal writes in place of a failure's message once it is moved into a payload.
ENCODED_FAILURE = "Encoded failure"


def case_of(workflow_id: str) -> str:
    """The case a workflow belongs to: a case is its own (`claim-7`), and a plan or workflow
    step's child `claim-7/collect#1` is its case's. So a case ID never holds a `/`."""
    return workflow_id.split("/")[0]


class SensitiveCodec(PayloadCodec, WithSerializationContext):
    """Seals each sensitive part of a payload with its case's key, and opens it again."""

    def __init__(self, keys: KeyProvider, case: str | None = None) -> None:
        self.keys = keys
        self.case = case  # the case of the workflow Temporal said the payloads belong to

    def with_context(self, context: SerializationContext) -> "SensitiveCodec":
        """This codec for the payloads of one workflow, from the ID Temporal gives: a workflow's
        own payloads and its children's, and those of the activities it calls."""
        # Temporal: before each use, the SDK hands the codec the workflow its payloads belong to.
        workflow_id = None
        if isinstance(context, WorkflowSerializationContext | ActivitySerializationContext):
            workflow_id = context.workflow_id
        return SensitiveCodec(self.keys, None if workflow_id is None else case_of(workflow_id))

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        return [self.sealed(payload, SENSITIVE, ENCRYPTED, self.keys.seal) for payload in payloads]

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        return [self.sealed(payload, ENCRYPTED, SENSITIVE, self.keys.open) for payload in payloads]

    def sealed(self, payload: Payload, before: str, after: str, change: Any) -> Payload:
        """`payload` with each part named `before<n>` changed by `change` (seal or open) and
        renamed `after<n>`. A payload without one is passed on as it is, with no key asked for:
        so a case with no sensitive value, or a history from before 9b, needs no key."""
        names = sorted(name for name in payload.metadata if name.startswith(before))
        if not names:
            return payload
        if self.case is None:
            # Fail closed: never written, or read, without knowing whose key it takes.
            raise KeyRefused(
                "a sensitive part has no case to be sealed or opened for: Temporal gave the codec "
                "no workflow ID"
            )
        changed = Payload()
        changed.CopyFrom(payload)  # Temporal: a payload given to a codec is never changed
        for name in names:
            part = SENSITIVE + name.removeprefix(before)  # its place, the same either way
            changed.metadata[after + name.removeprefix(before)] = change(
                self.case, payload.metadata[name], part
            )
            del changed.metadata[name]
        return changed


class SensitiveFailures(DefaultFailureConverter):
    """Temporal's failure converter, with a failure's message and stack trace moved into a
    payload as sensitive parts, at every level of its causes. Temporal keeps them outside
    payloads, and they may quote a sensitive value, whoever raised the failure (brief, D31)."""

    def to_failure(
        self, exception: BaseException, payload_converter: PayloadConverter, failure: Failure
    ) -> None:
        # The causes are converted first, each by this method: each level seals its own.
        super().to_failure(exception, payload_converter, failure)
        if failure.HasField("encoded_attributes"):
            return  # already sealed where it was raised, such as an activity's failure
        attributes = {
            "message": Sensitive(failure.message),
            "stack_trace": Sensitive(failure.stack_trace),
        }
        failure.encoded_attributes.CopyFrom(payload_converter.to_payloads([attributes])[0])
        failure.message, failure.stack_trace = ENCODED_FAILURE, ""

    def from_failure(self, failure: Failure, payload_converter: PayloadConverter) -> BaseException:
        if failure.HasField("encoded_attributes"):
            opened = Failure()
            opened.CopyFrom(failure)  # Temporal: a failure given to a converter is never changed
            attributes = payload_converter.from_payloads([failure.encoded_attributes])[0]
            opened.message = str(plain(attributes["message"]))
            opened.stack_trace = str(plain(attributes["stack_trace"]))
            opened.ClearField("encoded_attributes")
            failure = opened
        # The causes are read back by this method too, from Temporal's own.
        return super().from_failure(failure, payload_converter)
