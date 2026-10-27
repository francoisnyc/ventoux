"""`ventoux draft`: a model drafts a plan of a package, checked as a release checks it, into the
drafts folder named in configuration, never into a package (brief, D63).

Everything is settled before the model is asked (the person, the folder, the package, the
provider, a draft already there), so a refusal then writes nothing. Once the model was asked, a
record is written whatever the verdict. Exit 0 drafted, 1 abandoned, 2 when it couldn't read or
ask, never with a traceback.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from ventoux.authoring.loop import Authored, DraftRefused, author
from ventoux.authoring.provider import Provider, ProviderFailed
from ventoux.case.releases import PackageRefused, PackageUnreadable
from ventoux.core.catalog import Catalog
from ventoux.core.person import identifier_problem
from ventoux.tooling.advising import provider_for
from ventoux.tooling.deployment import Configuration
from ventoux.tooling.releases import read_package
from ventoux.tooling.schema import schema_files

DRAFTED = 0
ABANDONED = 1  # refused, as `ventoux release` uses 1
CANT = 2  # a setting, a file, the package or the model couldn't be read or asked


def draft_command(arguments: argparse.Namespace, found: Configuration, catalog: Catalog) -> int:
    """Draft `--plan` of the package at `arguments.package` for `--goal`, asked by `--by`."""
    try:
        drafts = drafts_folder(found)
        if (wrong := identifier_problem(arguments.by)) is not None:
            raise DraftRefused(wrong)
        released = read_package(arguments.package)
        plan_file, record_file = (
            drafts / f"{arguments.plan}.json",
            drafts / f"{arguments.plan}.record.json",
        )
        for there in (plan_file, record_file):
            if there.exists():
                # Someone may be reviewing it: never overwritten (brief, D63).
                raise DraftRefused(
                    f"{shown(there, found)} is there already: move it, or keep it in a pull request"
                )
        provider = provider_for(arguments, found)
        schema = json.loads(schema_files()["plan.schema.json"])  # what `ventoux schema` publishes
        authored = asyncio.run(
            author(
                arguments.goal,
                released,
                arguments.plan,
                catalog,
                schema,
                provider,
                arguments.rounds,
            )
        )
    except (DraftRefused, ProviderFailed, PackageRefused, PackageUnreadable, OSError) as refused:
        print(refused, file=sys.stderr)
        return CANT
    drafts.mkdir(parents=True, exist_ok=True)
    digest = None
    if authored.verdict == "drafted" and authored.plan is not None:
        plan_file.write_text(authored.plan)
        digest = hashlib.sha256(plan_file.read_bytes()).hexdigest()
    record_file.write_text(record_of(arguments, released.name, provider, authored, digest))
    kept = f"its record: {shown(record_file, found)}"
    if digest is not None:
        print(
            f"{arguments.plan} drafted in {counted(len(authored.rounds))}: {shown(plan_file, found)}"
        )
        print(kept)
        print(
            "keep it in a pull request: it runs nowhere until it is reviewed, released and activated"
        )
        return DRAFTED
    if authored.verdict == "abandoned":
        print(f"{arguments.plan} {authored.reason}")
        print(kept)
        return ABANDONED
    print(f"{arguments.plan}: {authored.reason}", file=sys.stderr)
    print(kept, file=sys.stderr)
    return CANT


def drafts_folder(found: Configuration) -> Path:
    """The drafts folder the configuration names, relative to the project's root; none named is
    refused, never a default folder (brief, D63)."""
    if found.drafts is None:
        raise DraftRefused(
            'no drafts folder is named: name it in pyproject.toml, [tool.ventoux] drafts = "drafts"'
        )
    root = found.root if found.root is not None else Path.cwd()
    return root / found.drafts


def record_of(
    arguments: argparse.Namespace,
    package: str,
    provider: Provider,
    authored: Authored,
    digest: str | None,
) -> str:
    """The draft's provenance, kept beside it, never in it: so a reviewed plan reads the same
    whoever drafted it (brief, D14) (brief, D63)."""
    kept = {
        "plan": arguments.plan,
        "package": package,
        "goal": arguments.goal,
        "asked_by": arguments.by,
        "provider": provider.name,
        "rounds": [
            {"answer": each.answer, "problems": list(each.problems)} for each in authored.rounds
        ],
        "verdict": authored.verdict,
        "reason": authored.reason,
        "warnings": list(authored.warnings),
        # The SHA-256 of the plan file's bytes, as written; None when none was: so a draft edited
        # without its record is told, and never shown for approval (brief, D64).
        "draft_sha256": digest,
    }
    return json.dumps(kept, indent=2, ensure_ascii=False) + "\n"


def shown(path: Path, found: Configuration) -> str:
    """`path` as the person reads it: relative to the project's root."""
    root = found.root if found.root is not None else Path.cwd()
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def counted(rounds: int) -> str:
    return "1 round" if rounds == 1 else f"{rounds} rounds"
