"""An environment's registry, in memory: what it holds, and how it answers each request
(layer 12e).

One registry per environment keeps the workers' manifests, which release of each package is
active, which are retired, and which cases are open on each (brief, D5). Each request is a pure
function of the registry and the request, giving the registry after it and an answer, so the
registry workflow is a driver around them, as the case workflow is around `decide`.
See docs/layers/12-releases.md (12e).
"""

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field

from ventoux.case.activation import Manifest, activation_problems
from ventoux.case.releases import Hash


@dataclass(frozen=True)
class Answer:
    """What a request did, or why not: one line each, naming releases, cases and workers."""

    done: bool  # False: refused: what the request asked for didn't happen
    said: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Released:
    """A release, as a request names it: its package, number and digest."""

    name: str  # the package: `refund`
    release: int
    digest: Hash

    def __str__(self) -> str:
        return f"{self.name} {self.release}"


@dataclass
class Activation:
    """A release as it was activated here: what its record needs, and where its cases run."""

    released: Released
    contracts: dict[str, Hash]  # every contract its record needs, with its hash
    task_queue: str  # the queue its cases run on, whose workers activation checked


@dataclass
class Registry:
    """What one environment's registry holds; all of it crosses its continue-as-new."""

    environment: str  # `production`
    development: bool = False  # True: drafts run here; never set back once False (brief, D51)
    manifests: dict[str, Manifest] = field(default_factory=dict[str, Manifest])  # by identity
    active: dict[str, int] = field(default_factory=dict[str, int])  # each package's active release
    # Each release ever activated here, by its label (`refund 2`).
    activated: dict[str, Activation] = field(default_factory=dict[str, Activation])
    retired: list[str] = field(default_factory=list[str])  # labels, retired for good
    open: dict[str, str] = field(default_factory=dict[str, str])  # each open case's release
    # Each workflow contract the case workers bind, and the workflow type they bind it to.
    bindings: dict[str, str] = field(default_factory=dict[str, str])
    log: list[str] = field(default_factory=list[str])  # activations and retirements, in order


def publish(registry: Registry, manifest: Manifest) -> tuple[Registry, Answer]:
    """Keep `manifest`, a worker's as it starts, in place of any earlier one of its identity;
    refused if it moves a workflow type that open cases call (brief, D29)."""
    here = registry.environment
    if manifest.environment != here:
        return registry, Answer(
            False, [f"{manifest.identity} serves {manifest.environment}, not {here}"]
        )
    for reference, bound in sorted(manifest.binds.items()):
        before = registry.bindings.get(reference)
        calling = callers(registry, reference)
        if before is not None and before != bound.workflow and calling:
            # A case's history records the type of each child it started: replayed under another
            # type, it fails, so the type never moves while a case could call it (brief, D29).
            return registry, Answer(
                False,
                [
                    (
                        f"{reference} is bound to {before}, and {counted(calling)} of "
                        f"{', '.join(sorted(set(calling.values())))} "
                        f"{'calls' if len(calling) == 1 else 'call'} it: a workflow type never moves "
                        "under open cases; move its task queue, or bind a new contract version"
                    )
                ],
            )
    registry = copy.deepcopy(registry)  # the registry passed in is never changed
    registry.manifests[manifest.identity] = manifest
    for reference, bound in manifest.binds.items():
        registry.bindings[reference] = bound.workflow
    return registry, Answer(True, [f"{manifest.identity} serves {manifest.task_queue} in {here}"])


def callers(registry: Registry, reference: str) -> dict[str, str]:
    """Each open case whose release needs `reference`, with that release's label."""
    return {
        case: label
        for case, label in registry.open.items()
        if label in registry.activated and reference in registry.activated[label].contracts
    }


def counted(cases: Mapping[str, str]) -> str:
    """`1 open case`, `3 open cases`."""
    return f"{len(cases)} open case{'' if len(cases) == 1 else 's'}"


@dataclass(frozen=True)
class Activating:
    """A request to activate a release here: from its record, and what the command saw."""

    released: Released
    contracts: dict[str, Hash]  # every contract its record needs, with its hash
    task_queue: str  # where its new cases will run
    pollers: dict[str, list[str]]  # each queue's pollers, by identity, as the command saw them
    by: str  # who activates it, as the trusted caller states (brief, D19)


def activate(registry: Registry, asked: Activating) -> tuple[Registry, Answer]:
    """Make `asked.released` the release its package's new cases open on, once the workers here
    serve what its record needs: checked again against the manifests this registry holds, never
    trusting the command's own check (brief, D5). Rolling back is activating an earlier release."""
    released, label, here = asked.released, str(asked.released), registry.environment
    refused = f"{label} not activated in {here}:"
    if label in registry.retired:
        return registry, Answer(False, [refused, f"{label} is retired in {here}: it opens no case"])
    known = registry.activated.get(label)
    if known is not None and known.released.digest != released.digest:
        # Fail closed: one label, one behaviour; a record that changed is never taken.
        return registry, Answer(False, [refused, f"{here}'s {label} has another digest"])
    problems = activation_problems(
        label, asked.contracts, asked.task_queue, here, registry.manifests, asked.pollers
    )
    if problems:
        return registry, Answer(False, [refused, *problems])
    before = registry.active.get(released.name)
    if before == released.release and registry.activated[label].task_queue == asked.task_queue:
        return registry, Answer(True, [f"{label} is already active in {here}"])
    registry = copy.deepcopy(registry)
    registry.active[released.name] = released.release
    registry.activated[label] = Activation(released, dict(asked.contracts), asked.task_queue)
    line = f"{asked.by} activated {label} in {here}"
    if before is not None and before > released.release:
        line += f", rolling back from {released.name} {before}"
    elif before is not None and before != released.release:
        line += f", after {released.name} {before}"
    registry.log.append(line)
    return registry, Answer(True, [line])


@dataclass(frozen=True)
class Opening:
    """A case asking, as it opens, whether it may: on which release, from which queue."""

    case: str  # its ID: `refund-7`
    task_queue: str  # the queue it runs on, as its workflow knows it
    released: Released | None  # its release; None: a draft


def opened(registry: Registry, asked: Opening) -> tuple[Registry, Answer]:
    """Let the case open, and list it as open on its release, if that release is its package's
    active one here, with the same digest, on the queue it was activated on; a draft only in a
    development environment (brief, D51). One request, so nothing comes between the check and
    the listing."""
    here, case, released = registry.environment, asked.case, asked.released
    if released is None:
        if registry.development:
            return registry, Answer(True, [f"{case} opened as a draft in {here}"])
        return registry, Answer(
            False, [f"{case} can't open as a draft in {here}: open it on a release"]
        )
    label = str(released)
    refused = f"{case} can't open on {label}"
    if registry.open.get(case) == label:
        return registry, Answer(True, [f"{case} is open on {label} in {here}"])  # asked again
    why = target_problem(registry, released)
    active = registry.active.get(released.name)
    if why is None and active != released.release:
        why = f"{released.name} {active} is active in {here}"
    if why is not None:
        return registry, Answer(False, [f"{refused}: {why}"])
    queue = registry.activated[label].task_queue
    if asked.task_queue != queue:
        # Activation checked the workers on that queue only (choice 68, as answered).
        return registry, Answer(
            False, [f"{refused} on {asked.task_queue}: {here} activated it on {queue}"]
        )
    registry = copy.deepcopy(registry)
    registry.open[case] = label
    return registry, Answer(True, [f"{case} is open on {label} in {here}"])


def target_problem(registry: Registry, released: Released) -> str | None:
    """Why no case may run on `released` here: retired, never activated, or with another digest
    than the one activated; None if one may."""
    label, here = str(released), registry.environment
    if label in registry.retired:
        return f"{label} is retired in {here}"
    known = registry.activated.get(label)
    if known is None:
        if released.name not in registry.active:
            return f"{here} has no {released.name} activated"
        return f"{here} never activated {label}: activate it first"
    if known.released.digest != released.digest:
        return f"{here}'s {label} has another digest"
    return None


@dataclass(frozen=True)
class Moving:
    """A case asking, as a migration is about to apply, whether it may move to its target."""

    case: str
    released: Released  # the target


def moved(registry: Registry, asked: Moving) -> tuple[Registry, Answer]:
    """List the case as open on the migration's target, if that target was activated here and
    isn't retired, with its digest: a migration back to an earlier release stays possible
    (brief, D53), one to a release activation never checked here doesn't."""
    why = target_problem(registry, asked.released)
    if why is not None and why.startswith(f"{registry.environment} has no"):
        why = f"{registry.environment} never activated {asked.released}: activate it first"
    if why is not None:
        return registry, Answer(False, [f"{asked.case} can't move to {asked.released}: {why}"])
    registry = copy.deepcopy(registry)
    registry.open[asked.case] = str(asked.released)
    return registry, Answer(
        True, [f"{asked.case} is open on {asked.released} in {registry.environment}"]
    )


def closed(registry: Registry, case: str) -> tuple[Registry, Answer]:
    """The case has closed: no longer open on any release. Said again, it changes nothing."""
    registry = copy.deepcopy(registry)
    label = registry.open.pop(case, None)
    return registry, Answer(True, [] if label is None else [f"{case} closed on {label}"])


def open_on(registry: Registry, released: Released) -> list[str]:
    """The cases open on `released` here, by ID: a migration's cohort (brief, D53)."""
    return sorted(case for case, label in registry.open.items() if label == str(released))


@dataclass(frozen=True)
class Retiring:
    """A request to retire a release here."""

    released: Released
    by: str  # who retires it, as the trusted caller states (brief, D19)


def retire(
    registry: Registry, asked: Retiring, ended: Mapping[str, str]
) -> tuple[Registry, Answer]:
    """Retire the release for good: it then opens no case, is no migration's target and is never
    activated again; refused while it is active or a case is open on it (brief, D5). `ended`
    says, for cases listed on it, which Temporal says have ended (`terminated`) without saying
    they closed: those are dropped, saying so, and never block it (choice 67, as answered)."""
    label, here = str(asked.released), registry.environment
    refused = f"{label} not retired"
    if label in registry.retired:
        return registry, Answer(False, [f"{label} is retired in {here} already"])
    if label not in registry.activated:
        return registry, Answer(False, [f"{refused}: {here} never activated it"])
    if registry.active.get(asked.released.name) == asked.released.release:
        return registry, Answer(
            False, [f"{refused}: it is active in {here}: activate another first"]
        )
    registry = copy.deepcopy(registry)
    said: list[str] = []
    for case in open_on(registry, asked.released):
        if case in ended:
            del registry.open[case]
            said.append(
                f"{case} ended ({ended[case]}) without saying it closed: no longer open on {label}"
            )
    still = open_on(registry, asked.released)
    if still:
        said.append(
            f"{refused}: {len(still)} case{'' if len(still) == 1 else 's'} "
            f"{'is' if len(still) == 1 else 'are'} open on it in {here} ({', '.join(still)}): "
            "migrate them, or let them close"
        )
        return registry, Answer(False, said)
    registry.retired.append(label)
    line = f"{asked.by} retired {label} in {here}"
    registry.log.append(line)
    return registry, Answer(True, [*said, line])


def harden(registry: Registry, by: str) -> tuple[Registry, Answer]:
    """Make a development environment a production one, for good: drafts no longer open there.
    Nothing makes it a development one again: stricter downstream, never looser (brief, D51)."""
    here = registry.environment
    if not registry.development:
        return registry, Answer(True, [f"{here} is a production environment already"])
    registry = copy.deepcopy(registry)
    registry.development = False
    line = f"{by} made {here} a production environment: drafts no longer open"
    registry.log.append(line)
    return registry, Answer(True, [line])
