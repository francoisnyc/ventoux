"""`ventoux advise`: what the step advisor suggests to a person on a running case (layer 15b).

It prints the suggestion, labelled, and proposes nothing: proposing is the person's act, from the
inbox (brief, D61). The provider is settled first, so a missing setting is refused before
Temporal is asked anything (brief, D62).
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from temporalio.client import Client, WorkflowQueryFailedError
from temporalio.service import RPCError

from ventoux.authoring.advisor import Advice
from ventoux.authoring.beside import advise_case
from ventoux.authoring.provider import Provider, ProviderFailed, Recorded
from ventoux.temporal.converter import registry_converter
from ventoux.tooling.deployment import Configuration

DONE = 0  # the advisor answered: a suggestion, or nothing and why
CANT_READ = 2  # a setting, a recording, the model, or Temporal can't be read


def advise_command(arguments: argparse.Namespace, found: Configuration) -> int:
    """Ask the step advisor for `--by`, holding each `--role`, and print what it suggests."""
    try:
        provider = provider_for(arguments, found)
    except (ProviderFailed, OSError, ValueError, KeyError) as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ
    try:
        advice = asyncio.run(advised(arguments, provider))
    except WorkflowQueryFailedError:
        # Its own failure is sealed by the codec ("Encoded failure"), so the command says what
        # to check: a plan's or a child's run, or a worker that predates the queries.
        print(
            f"{arguments.case} didn't answer the advisor's queries: is it a case, served by a "
            "worker that has them?",
            file=sys.stderr,
        )
        return CANT_READ
    except (OSError, RPCError, RuntimeError) as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ
    print(advice.said())
    # A provider that gave no answer (a setting, the model, a recording) couldn't be read.
    return CANT_READ if advice.gave_no_answer else DONE


def provider_for(arguments: argparse.Namespace, found: Configuration) -> Provider:
    """The provider to ask: a recording, if `--recording` names one; else the live provider, for
    the model `--model` or the configuration names (brief, D62)."""
    if arguments.recording is not None:
        return Recorded.read(Path(arguments.recording))
    try:
        # Imported here: only the live provider needs the `anthropic` extra.
        from ventoux.authoring.anthropic import Anthropic
    except ImportError:
        raise ProviderFailed(
            "the live provider needs the anthropic extra: pip install 'ventoux[anthropic]'"
        ) from None
    return Anthropic(arguments.model if arguments.model is not None else found.model)


async def advised(arguments: argparse.Namespace, provider: Provider) -> Advice:
    """The advice for the case, from the advisor beside it (brief, D61)."""
    # No key: the advisor's queries carry no case-file value, sealed or not (brief, D61).
    client = await Client.connect(
        arguments.address, namespace=arguments.namespace, data_converter=registry_converter()
    )
    case = client.get_workflow_handle(arguments.case)
    # The asker's time, against which facts' ages are told, as an approval sheet's (brief, D33).
    at = arguments.at if arguments.at is not None else int(time.time())
    return await advise_case(case, arguments.by, arguments.role, provider, at)
