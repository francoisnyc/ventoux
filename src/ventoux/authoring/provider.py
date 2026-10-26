"""Providers: what asks a model, as one small protocol (brief, D61).

A provider is given a request (the system text and the messages, in order) and gives the model's
answer as text. What it answers is untrusted data, `untrusted:llm`: read, checked, and never run
(brief, D12). `Recorded` answers from a recording, so tests need no network and no key.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Message:
    """One turn of the conversation with the model."""

    role: Literal["user", "assistant"]  # who said it: the asker, or the model
    content: str  # what was said


@dataclass(frozen=True)
class Request:
    """What a model is asked: its instructions, then the conversation so far."""

    system: str  # the instructions, the same for every turn
    messages: tuple[Message, ...]  # the conversation, in order, the last one the asker's


class Provider(Protocol):
    """Something that asks a model. Asynchronous, so asking never blocks an event loop."""

    @property
    def name(self) -> str:
        """Which provider this is, as a record says it: `recorded`, `anthropic:<model>`."""
        ...

    async def complete(self, request: Request) -> str:
        """The model's answer to `request`, as text."""
        ...


class ProviderFailed(Exception):
    """A provider gave no answer: a setting is missing, or the model or its API failed. Its
    message names the setting or the failure, never a key or what was asked (brief, D62)."""


class ReplayRefused(Exception):
    """A recording was asked something it didn't record: a request that differs, or one more
    than it holds. Never answered with the nearest answer it has (fail closed)."""


@dataclass(frozen=True)
class Exchange:
    """One request a provider was sent, and its answer."""

    request: Request | None  # None: answer whatever is asked (for tests about the answer)
    answer: str


class Recorded:
    """A provider that replays a recording: each answer only to the request it was recorded
    with, in order, and nothing past the last. No network and no key."""

    def __init__(self, exchanges: tuple[Exchange, ...]) -> None:
        self._exchanges = exchanges
        self._next = 0  # the exchange the next request is compared with

    @classmethod
    def answering(cls, *answers: str) -> "Recorded":
        """Gives `answers` in order, whatever it is asked: for tests about reading an answer,
        never about what was asked."""
        return cls(tuple(Exchange(None, answer) for answer in answers))

    @classmethod
    def read(cls, path: Path) -> "Recorded":
        """The recording `Recording.save` wrote at `path`."""
        session = json.loads(path.read_text(encoding="utf-8"))
        return cls(tuple(exchange_of(each) for each in session["exchanges"]))

    @property
    def name(self) -> str:
        return "recorded"

    async def complete(self, request: Request) -> str:
        number = self._next + 1  # requests are counted from 1, as people count them
        if self._next >= len(self._exchanges):
            held = len(self._exchanges)
            raise ReplayRefused(f"request {number} was never recorded: the recording holds {held}")
        recorded = self._exchanges[self._next]
        if recorded.request is not None and (where := difference(recorded.request, request)):
            raise ReplayRefused(f"request {number} differs from the one recorded, {where}")
        self._next += 1
        return recorded.answer


def difference(recorded: Request, asked: Request) -> str | None:
    """Where `asked` first differs from `recorded`, in words, or None if it doesn't."""
    if asked.system != recorded.system:
        return "in its system text"
    for number, (was, now) in enumerate(zip(recorded.messages, asked.messages), start=1):
        if was != now:
            return f"at message {number}"
    if len(asked.messages) != len(recorded.messages):
        return f"in its number of messages: {len(asked.messages)}, not {len(recorded.messages)}"
    return None


class Recording:
    """A provider that asks another one and keeps each exchange, to save as a recording. A
    person runs it by hand, with a live provider, to make a test's recording."""

    def __init__(self, inner: Provider) -> None:
        self._inner = inner
        self._exchanges: list[Exchange] = []

    @property
    def name(self) -> str:
        return self._inner.name

    async def complete(self, request: Request) -> str:
        answer = await self._inner.complete(request)
        self._exchanges.append(Exchange(request, answer))
        return answer

    def save(self, path: Path) -> None:
        """Write every exchange so far to `path`, as `Recorded.read` reads it. It holds what was
        asked and answered, never a key."""
        session = {"provider": self.name, "exchanges": [asdict(each) for each in self._exchanges]}
        path.write_text(json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def exchange_of(saved: dict[str, Any]) -> Exchange:
    """An exchange as `Recording.save` wrote it."""
    request = saved["request"]
    messages = tuple(Message(each["role"], each["content"]) for each in request["messages"])
    return Exchange(Request(request["system"], messages), saved["answer"])
