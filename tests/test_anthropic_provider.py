"""The live provider (layer 15b): Anthropic's, behind the `anthropic` extra, failing closed.

No test reaches the network: the SDK's client is replaced by a fake that records what it is
asked. The key is read from the environment alone, and never said (brief, D62).
"""

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import anthropic
import httpx2
import pytest

from ventoux.authoring.anthropic import Anthropic, ProviderFailed
from ventoux.authoring.provider import Message, Request

KEY = "sk-ant-test-0123456789"
ASKED = Request("Advise.", (Message("user", "Which step?"),))


def test_no_key_in_the_environment_is_refused_naming_the_setting() -> None:
    with pytest.raises(ProviderFailed) as failed:
        Anthropic("claude-opus-5-5", env={})
    assert str(failed.value) == (
        "ANTHROPIC_API_KEY is not set: the live provider reads its key from the environment, "
        "never from a file"
    )


def test_no_model_named_is_refused_naming_where_to_name_one() -> None:
    with pytest.raises(ProviderFailed) as failed:
        Anthropic(None, env={"ANTHROPIC_API_KEY": KEY})
    assert str(failed.value) == (
        'no model is named: name it in pyproject.toml, [tool.ventoux] model = "…", or with --model'
    )
    assert KEY not in str(failed.value)


class FakeMessages:
    """Stands in for the SDK's `client.messages`: records each call, answers as told."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.asked: list[dict[str, Any]] = []

    async def create(self, **asked: Any) -> Any:
        self.asked.append(asked)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def replied(stop_reason: str, *texts: str) -> Any:
    """A response as the SDK gives it: its stop reason and its content blocks."""
    blocks = [SimpleNamespace(type="thinking", thinking="")]
    blocks += [SimpleNamespace(type="text", text=text) for text in texts]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def unreachable() -> anthropic.APIConnectionError:
    """The error the SDK raises when the API can't be reached."""
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(message="Connection error.", request=request)


def provider(answer: Any) -> tuple[Anthropic, FakeMessages]:
    messages = FakeMessages(answer)
    client = cast(Any, SimpleNamespace(messages=messages))
    return Anthropic("claude-opus-5-5", env={"ANTHROPIC_API_KEY": KEY}, client=client), messages


def test_it_sends_the_requests_system_text_and_messages_and_joins_the_models_text() -> None:
    live, messages = provider(replied("end_turn", '{"step": ', '"goodwill"}'))
    assert asyncio.run(live.complete(ASKED)) == '{"step": "goodwill"}'
    assert live.name == "anthropic:claude-opus-5-5"
    [asked] = messages.asked
    assert asked["model"] == "claude-opus-5-5"
    assert asked["system"] == "Advise."
    assert asked["messages"] == [{"role": "user", "content": "Which step?"}]


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (replied("refusal"), "the model refused to answer"),
        (replied("max_tokens", '{"step": "goo'), "the model's answer was cut short (max_tokens)"),
        (replied("end_turn"), "the model gave no text"),
        (
            replied("model_context_window_exceeded", '{"step": '),
            "the model's answer was cut short (model_context_window_exceeded)",
        ),
        (unreachable(), "the model's API failed: APIConnectionError"),
    ],
)
def test_a_refusal_a_cut_answer_no_text_or_an_api_error_fails_closed(
    answer: Any, said: str
) -> None:
    live, _ = provider(answer)
    with pytest.raises(ProviderFailed) as failed:
        asyncio.run(live.complete(ASKED))
    assert str(failed.value) == said
    assert KEY not in str(failed.value)
