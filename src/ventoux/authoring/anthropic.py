"""The live provider: Anthropic's Messages API, behind the optional `anthropic` extra (brief, D62).

Only this module imports the SDK, so nothing else needs the extra. Its key comes from the
environment alone, and is never said; anything it can't answer is a failure, never an answer.
"""

import os
from collections.abc import Mapping

from anthropic import APIError, AsyncAnthropic

from ventoux.authoring.provider import ProviderFailed, Request

KEY = "ANTHROPIC_API_KEY"  # the one place the key is read from


class Anthropic:
    """A provider asking one of Anthropic's models, named in configuration."""

    def __init__(
        self,
        model: str | None,
        env: Mapping[str, str] = os.environ,
        client: AsyncAnthropic | None = None,
    ) -> None:
        # Fail closed: the SDK would look for other credentials (a saved profile) if the key
        # weren't given, and the model would default to nobody's choice (brief, D62).
        if not model:
            raise ProviderFailed(
                'no model is named: name it in pyproject.toml, [tool.ventoux] model = "…", '
                "or with --model"
            )
        key = env.get(KEY)
        if not key:
            raise ProviderFailed(
                f"{KEY} is not set: the live provider reads its key from the environment, "
                "never from a file"
            )
        self._model = model
        self._client = client or AsyncAnthropic(api_key=key)

    @property
    def name(self) -> str:
        return f"anthropic:{self._model}"

    async def complete(self, request: Request) -> str:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=request.system,
                messages=[
                    {"role": each.role, "content": each.content} for each in request.messages
                ],
            )
        except APIError as error:
            # Its kind only: the SDK's message may quote what was sent (brief, D62).
            raise ProviderFailed(f"the model's API failed: {type(error).__name__}") from None
        # A stop reason says whether the text is a whole answer; anything else is no answer.
        if response.stop_reason == "refusal":
            raise ProviderFailed("the model refused to answer")
        if response.stop_reason not in WHOLE:
            raise ProviderFailed(f"the model's answer was cut short ({response.stop_reason})")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise ProviderFailed("the model gave no text")
        return text


# The stop reasons after which the model's text is its whole answer: it finished, or reached a
# stop sequence. Any other (cut short, paused, asking for a tool) is no answer (fail closed).
WHOLE = ("end_turn", "stop_sequence")

# Room for a whole plan in one answer, without streaming (the SDK's guidance for a request that
# isn't streamed); an answer cut short fails, never a part of one read as the whole.
MAX_TOKENS = 16000
