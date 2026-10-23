"""The activation check: whether an environment's workers can run a release (layer 12e).

Temporal knows which workers poll a task queue, but not what they serve. So each worker publishes
a manifest, the contracts it serves with their hashes, and activating a release checks, for each
contract its record needs, that every worker polling where it runs serves it with the record's
hash (brief, D5). Pure: the manifests and the pollers come in as data, read by the caller.
See docs/layers/12-releases.md (12e).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from ventoux.case.releases import Hash


@dataclass(frozen=True)
class Bound:
    """Where a case worker runs a workflow contract: its workflow type and task queue
    (brief, D29)."""

    workflow: str  # the workflow type its team's worker registers
    task_queue: str  # the task queue that worker polls

    def __str__(self) -> str:
        return f"{self.workflow} on {self.task_queue}"


@dataclass(frozen=True)
class Manifest:
    """What one worker says it serves, published when it starts (brief, D5)."""

    environment: str  # the environment it serves: `production`
    task_queue: str  # the queue it polls
    build: str  # the deployment's name for its build, an image tag or a commit, as it was given
    identity: str  # its Temporal worker identity, as Temporal names it among a queue's pollers
    serves: dict[str, Hash]  # each contract it registers code for, with its hash
    workflows: list[str]  # the workflow types it registers
    case: str | None = None  # the case workflow type among them; None: not a case worker
    # Its case workflow's bindings: each workflow contract, and where it runs (brief, D29).
    binds: dict[str, Bound] = field(default_factory=dict[str, Bound])


@dataclass(frozen=True)
class Seen:
    """What a check sees in one environment: each worker's manifest by its identity, and each
    queue's pollers by identity, as Temporal lists them now."""

    environment: str
    manifests: Mapping[str, Manifest]
    pollers: Mapping[str, list[str]]


def activation_problems(
    label: str,
    contracts: Mapping[str, Hash],
    queue: str,
    environment: str,
    manifests: Mapping[str, Manifest],
    pollers: Mapping[str, list[str]],
) -> list[str]:
    """Why the release `label` (`refund 2`), whose record needs `contracts`, can't run on `queue`
    in `environment`, given each worker's manifest by identity and each queue's pollers by
    identity; every problem at once, empty if none. Contracts, queues, workers and builds are
    named, never a value."""
    seen = Seen(environment, manifests, pollers)
    if not pollers.get(queue):
        # A manifest says what a worker served when it started; only Temporal says who polls now.
        return [f"no worker polls {queue} now: start one, then activate"]
    found, workers = live(seen, queue, cases=True)
    for reference in sorted(contracts):
        bindings = {manifest.identity: manifest.binds.get(reference) for manifest in workers}
        if any(bindings.values()):
            # A workflow contract: its team's workers, where the case workers bind it, run it.
            found += bound_problems(label, reference, contracts[reference], queue, bindings, seen)
            continue
        if not any(reference in manifest.serves for manifest in workers):
            found.append(f"{reference}: no worker on {queue} serves it: deploy a build that does")
            continue
        for manifest in workers:
            found += served_problems(label, reference, contracts[reference], manifest)
    return list(dict.fromkeys(found))  # each said once, in the order found


def live(seen: Seen, queue: str, cases: bool) -> tuple[list[str], list[Manifest]]:
    """The manifests of the workers polling `queue` now, and why any other poller there refuses:
    a worker that said nothing in this environment might serve anything, and Temporal would give
    it tasks all the same (fail closed). On a case queue, each must be a case worker."""
    found: list[str] = []
    workers: list[Manifest] = []
    for identity in sorted(seen.pollers.get(queue, [])):
        manifest = seen.manifests.get(identity)
        here = (seen.environment, queue)
        if manifest is None or (manifest.environment, manifest.task_queue) != here:
            found.append(
                f"{identity} polls {queue} and published no manifest in {seen.environment}: it "
                "may serve anything"
            )
        elif cases and manifest.case is None:
            found.append(
                f"{identity} polls {queue} and serves no case workflow: it would be given cases "
                "to run"
            )
        else:
            workers.append(manifest)
    return found, workers


def bound_problems(
    label: str,
    reference: str,
    needed: Hash,
    queue: str,
    bindings: Mapping[str, Bound | None],
    seen: Seen,
) -> list[str]:
    """Why the workflow contract `reference` can't run where the case workers on `queue` bind
    it: they bind it differently, nobody polls there, or a worker there doesn't serve it as
    released or doesn't register its type (brief, D29)."""
    if len(set(bindings.values())) > 1:
        each = "; ".join(
            f"{identity}: {bound or 'not bound'}" for identity, bound in sorted(bindings.items())
        )
        return [
            f"{reference}: the workers on {queue} bind it differently ({each}): deploy one binding"
        ]
    bound = next(iter(bindings.values()))
    assert bound is not None  # the caller found one bound, and they are all the same
    there = bound.task_queue
    if not seen.pollers.get(there):
        return [
            (
                f"{reference}: no worker polls {there}, where {queue} binds it, now: start one, then "
                "activate"
            )
        ]
    found, workers = live(seen, there, cases=False)
    for manifest in workers:
        found += served_problems(label, reference, needed, manifest)
        if bound.workflow not in manifest.workflows and reference in manifest.serves:
            found.append(
                f"{reference}: worker {manifest.identity} (build {manifest.build}) doesn't register "
                f"{bound.workflow}, where {queue} binds it: deploy a build that does"
            )
    return found


def served_problems(label: str, reference: str, needed: Hash, manifest: Manifest) -> list[str]:
    """Why `manifest`'s worker can't be given `reference`'s tasks: it doesn't serve it, or serves
    it with another hash than the record's. Temporal gives a task to any worker polling its queue,
    so every one of them must serve it, as released (brief, D5)."""
    worker = f"worker {manifest.identity} (build {manifest.build})"
    served = manifest.serves.get(reference)
    if served is None:
        return [f"{reference}: {worker} doesn't serve it: deploy a build that does"]
    if served != needed:
        return [
            (
                f"{reference}: {worker} serves it with hash {short(served)}, and {label} needs "
                f"{short(needed)}: deploy the build that serves the released contract"
            )
        ]
    return []


def short(hash: Hash) -> str:
    """A hash as people read it: its first 12 hex characters, as `ventoux release` prints."""
    return hash.sha256[:12]
