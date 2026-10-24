"""The environment commands' I/O: connecting to Temporal, reading records and manifests, and
saying what the registry answered (layer 12e).

What is decided is decided in the registry (`case/registry.py`, run by its workflow); here the
command reads what it is pointed at, asks, and prints. Exit 0 when done, 1 when refused, 2 when
something can't be read, as `ventoux release` (brief, D50). See docs/guides/releases.md.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from temporalio.client import Client
from temporalio.service import RPCError

from ventoux.case.activation import Manifest
from ventoux.case.registry import Answer
from ventoux.case.releases import RecordRefused
from ventoux.temporal import registry
from ventoux.temporal.converter import registry_converter
from ventoux.tooling.releases import FolderStore

DONE = 0  # it did what it was asked, or had nothing to do
REFUSED = 1  # the registry, or the store, refused: each problem is printed
CANT_READ = 2  # a file, or Temporal, can't be read

# Pydantic: checks a manifest's JSON against the dataclass, as a model would.
MANIFEST = TypeAdapter(Manifest)


class Unreadable(Exception):
    """A file that can't be read as what it should be."""


def environment_command(arguments: argparse.Namespace) -> int:
    """Run one environment command, print what it did, and say how it ended."""
    try:
        return asyncio.run(run(arguments))
    except (RecordRefused, registry.RegistryMissing, registry.ManifestRefused) as refused:
        print(refused, file=sys.stderr)
        return REFUSED
    except (Unreadable, OSError, RPCError, RuntimeError) as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ


async def run(arguments: argparse.Namespace) -> int:
    """The command, against Temporal at `--address`."""
    client = await Client.connect(
        arguments.address, namespace=arguments.namespace, data_converter=registry_converter()
    )
    if arguments.command == "environment":
        if arguments.action == "create":
            await registry.create_environment(client, arguments.name, arguments.development)
            kind = "development" if arguments.development else "production"
            where = "drafts open" if arguments.development else "drafts never open"
            print(f"{arguments.name} created: a {kind} environment, where {where}")
            return DONE
        if arguments.action == "harden":
            return said(await registry.harden(client, arguments.name, arguments.by))
        problems = await registry.environment_check(client, arguments.name)
        for line in problems:
            print(line)
        if problems:
            return REFUSED
        print(f"{arguments.name}: every release that is active or has open cases can run")
        return DONE
    if arguments.command == "manifest":
        return said(await registry.publish_manifest(client, read_manifest(arguments.file)))
    record = FolderStore(arguments.releases).get(arguments.package, arguments.release)
    if arguments.command == "activate":
        return said(
            await registry.activate(
                client, arguments.environment, record, arguments.task_queue, arguments.by
            )
        )
    return said(await registry.retire(client, arguments.environment, record, arguments.by))


def said(answer: Answer) -> int:
    """Print the registry's answer, one line each, and exit as it says."""
    for line in answer.said:
        print(line)
    return DONE if answer.done else REFUSED


def read_manifest(path: Path) -> Manifest:
    """A worker's manifest, from its JSON file: for a worker in another SDK language, which can't
    build one from Ventoux's library (brief, D6)."""
    try:
        return MANIFEST.validate_python(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as error:
        raise Unreadable(f"{path} can't be read as a worker's manifest: {error}") from None
