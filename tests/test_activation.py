"""The activation check and the environment registry, in memory (layer 12e).

Pure: manifests, pollers and requests are data, as the registry workflow and `ventoux activate`
give them. See docs/layers/12-releases.md (12e).
"""

from ventoux.case.activation import Bound, Manifest, activation_problems
from ventoux.case.releases import Hash

REFUND_3 = Hash(1, "c3e07d1a9b52" + "0" * 52)  # what the record says payments.refund@3 is
OTHER_3 = Hash(1, "51aa1c09e4f2" + "0" * 52)  # what an old build's catalog says it is
LOOKUP = Hash(1, "ab" * 32)
KYC = Hash(1, "cd" * 32)
NEEDS = {"payments.refund@3": REFUND_3, "orders.lookup@1": LOOKUP}


def worker(
    identity: str,
    serves: dict[str, Hash],
    build: str = "4f2a9c1",
    queue: str = "refunds",
    binds: dict[str, Bound] | None = None,
    case: str | None = "ventoux.case",
    environment: str = "production",
    workflows: list[str] | None = None,
) -> Manifest:
    """A worker's manifest, as it publishes it."""
    if workflows is None:
        workflows = [] if case is None else [case, "ventoux.plan"]
    return Manifest(environment, queue, build, identity, serves, workflows, case, binds or {})


def problems(
    manifests: list[Manifest], pollers: dict[str, list[str]], needs: dict[str, Hash] = NEEDS
) -> list[str]:
    by_identity = {manifest.identity: manifest for manifest in manifests}
    return activation_problems("refund 2", needs, "refunds", "production", by_identity, pollers)


# --- Slice 1: the check ---


def test_a_release_no_worker_serves_is_refused() -> None:
    # The curriculum's: the workers on refunds serve the lookup, and not the refund refund 2 calls.
    old = worker("refunds-a", {"orders.lookup@1": LOOKUP, "payments.refund@2": OTHER_3})
    assert problems([old], {"refunds": ["refunds-a"]}) == [
        "payments.refund@3: no worker on refunds serves it: deploy a build that does"
    ]


def test_a_served_hash_that_differs_is_refused() -> None:
    # The curriculum's: one worker serves refund@3 as the record says, another serves a refund@3
    # its own catalog hashes differently; Temporal would give a task to either.
    new = worker("refunds-a", {"orders.lookup@1": LOOKUP, "payments.refund@3": REFUND_3})
    old = worker("refunds-b", {"orders.lookup@1": LOOKUP, "payments.refund@3": OTHER_3}, "7b0e311")
    assert problems([new, old], {"refunds": ["refunds-a", "refunds-b"]}) == [
        (
            "payments.refund@3: worker refunds-b (build 7b0e311) serves it with hash 51aa1c09e4f2, "
            "and refund 2 needs c3e07d1a9b52: deploy the build that serves the released contract"
        )
    ]


SERVES = {"orders.lookup@1": LOOKUP, "payments.refund@3": REFUND_3}


def test_a_worker_without_a_manifest_refuses() -> None:
    # A poller with no manifest here, one of another environment, and one that isn't a case worker
    # might serve anything: Temporal would give it the release's tasks all the same.
    good = worker("refunds-a", SERVES)
    staging = worker("refunds-s", SERVES, environment="staging")
    contracts_only = worker("refunds-k", SERVES, case=None)
    pollers = {"refunds": ["refunds-a", "refunds-c", "refunds-k", "refunds-s"]}
    assert problems([good, staging, contracts_only], pollers) == [
        "refunds-c polls refunds and published no manifest in production: it may serve anything",
        "refunds-k polls refunds and serves no case workflow: it would be given cases to run",
        "refunds-s polls refunds and published no manifest in production: it may serve anything",
    ]


def test_a_manifest_without_a_live_worker_refuses() -> None:
    # A manifest says what a worker served when it started; only Temporal's pollers say anyone
    # polls now. A queue nobody polls refuses, whatever the manifests say.
    gone = worker("refunds-a", SERVES)
    assert problems([gone], {}) == ["no worker polls refunds now: start one, then activate"]
    assert problems([gone], {"refunds": []}) == [
        "no worker polls refunds now: start one, then activate"
    ]


KYC_BOUND = {"kyc.check@1": Bound("KycCheck", "kyc")}
WITH_KYC = NEEDS | {"kyc.check@1": KYC}


def team(identity: str, serves: dict[str, Hash], workflows: list[str] | None = None) -> Manifest:
    """A manifest a team's workflow worker publishes, in any SDK language: no case workflow."""
    return worker(identity, serves, "k-12", "kyc", case=None, workflows=workflows or ["KycCheck"])


def test_a_workflow_contract_is_checked_where_it_is_bound() -> None:
    # The case workers bind kyc.check@1 to KycCheck on kyc: the team's workers there are checked,
    # each serving it with the record's hash and registering the type, never the case workers.
    cases = worker("refunds-a", SERVES, binds=KYC_BOUND)
    right = team("kyc-a", {"kyc.check@1": KYC})
    wrong = team("kyc-b", {"kyc.check@1": OTHER_3})
    untyped = team("kyc-c", {"kyc.check@1": KYC}, ["KycCheckV2"])
    everyone = [cases, right, wrong, untyped]
    polling = {"refunds": ["refunds-a"], "kyc": ["kyc-a", "kyc-b", "kyc-c", "kyc-d"]}
    assert problems([cases, right], {"refunds": ["refunds-a"], "kyc": ["kyc-a"]}, WITH_KYC) == []
    assert problems(everyone, polling, WITH_KYC) == [
        "kyc-d polls kyc and published no manifest in production: it may serve anything",
        (
            "kyc.check@1: worker kyc-b (build k-12) serves it with hash 51aa1c09e4f2, and refund 2 "
            "needs cdcdcdcdcdcd: deploy the build that serves the released contract"
        ),
        (
            "kyc.check@1: worker kyc-c (build k-12) doesn't register KycCheck, where refunds binds "
            "it: deploy a build that does"
        ),
    ]
    # Nobody on the bound queue; two case workers binding it two ways.
    assert problems([cases], {"refunds": ["refunds-a"]}, WITH_KYC) == [
        "kyc.check@1: no worker polls kyc, where refunds binds it, now: start one, then activate"
    ]
    moved = worker("refunds-b", SERVES, "7b0e311", binds={"kyc.check@1": Bound("Kyc", "kyc")})
    unbound = worker("refunds-c", SERVES, "7b0e311")
    two_ways = {"refunds": ["refunds-a", "refunds-b", "refunds-c"], "kyc": ["kyc-a"]}
    assert problems([cases, moved, unbound, right], two_ways, WITH_KYC) == [
        (
            "kyc.check@1: the workers on refunds bind it differently (refunds-a: KycCheck on kyc; "
            "refunds-b: Kyc on kyc; refunds-c: not bound): deploy one binding"
        )
    ]


def test_activation_says_every_problem_at_once() -> None:
    # Every worker and every contract is read, and each problem said once, naming contracts,
    # queues, workers, builds and short hashes: never a value of any case.
    new = worker("refunds-a", {"payments.refund@3": REFUND_3})
    old = worker("refunds-b", {"payments.refund@3": OTHER_3}, "7b0e311")
    found = problems([new, old], {"refunds": ["refunds-a", "refunds-b", "refunds-c"]})
    assert found == [
        "refunds-c polls refunds and published no manifest in production: it may serve anything",
        "orders.lookup@1: no worker on refunds serves it: deploy a build that does",
        (
            "payments.refund@3: worker refunds-b (build 7b0e311) serves it with hash 51aa1c09e4f2, "
            "and refund 2 needs c3e07d1a9b52: deploy the build that serves the released contract"
        ),
    ]
