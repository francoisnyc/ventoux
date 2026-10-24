"""The activation check and the environment registry, in memory (layer 12e).

Pure: manifests, pollers and requests are data, as the registry workflow and `ventoux activate`
give them. See docs/layers/12-releases.md (12e).
"""

from ventoux.case.activation import Bound, Manifest, activation_problems
from ventoux.case.registry import (
    Activating,
    Moving,
    Opening,
    Registry,
    Released,
    Retiring,
    activate,
    closed,
    harden,
    moved,
    open_on,
    opened,
    publish,
    retire,
)
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


# --- Slice 2: the registry ---

REFUND_1 = Released("refund", 1, Hash(1, "11" * 32))
REFUND_2 = Released("refund", 2, Hash(1, "22" * 32))
LIVE = {"refunds": ["refunds-a"]}


def production(*manifests: Manifest) -> Registry:
    """Production's registry, with each worker's manifest published."""
    registry = Registry("production")
    for manifest in manifests:
        registry, _ = publish(registry, manifest)
    return registry


def activating(released: Released, needs: dict[str, Hash] = NEEDS) -> Activating:
    """Pia's activation of `released` on refunds, with the pollers her command saw."""
    return Activating(released, dict(needs), "refunds", LIVE, "pia")


def test_the_registry_checks_again_what_it_holds() -> None:
    # The command checked; the registry checks again against the manifests it holds, depending on
    # nothing the client checked but the pollers, which a workflow can't see.
    registry = production(
        worker("refunds-a", {"orders.lookup@1": LOOKUP, "payments.refund@3": OTHER_3})
    )
    after, answer = activate(registry, activating(REFUND_2))
    assert not answer.done
    assert answer.said == [
        "refund 2 not activated in production:",
        (
            "payments.refund@3: worker refunds-a (build 4f2a9c1) serves it with hash 51aa1c09e4f2, "
            "and refund 2 needs c3e07d1a9b52: deploy the build that serves the released contract"
        ),
    ]
    assert after == registry


SERVED = worker("refunds-a", SERVES)


def test_rolling_back_is_activating_the_previous_release() -> None:
    # The same request, the same checks: the workers must still serve refund 1's contracts as
    # refund 1's record says, or the rollback is refused too.
    registry = production(SERVED)
    registry, first = activate(registry, activating(REFUND_1))
    registry, second = activate(registry, activating(REFUND_2))
    registry, again = activate(registry, activating(REFUND_2))
    registry, back = activate(registry, activating(REFUND_1))
    assert [first.said, second.said, again.said, back.said] == [
        ["pia activated refund 1 in production"],
        ["pia activated refund 2 in production, after refund 1"],
        ["refund 2 is already active in production"],
        ["pia activated refund 1 in production, rolling back from refund 2"],
    ]
    assert registry.active == {"refund": 1}
    assert registry.log == [first.said[0], second.said[0], back.said[0]]
    gone, refused = activate(registry, activating(REFUND_2, {"payments.refund@2": REFUND_3}))
    assert refused.said == [
        "refund 2 not activated in production:",
        "payments.refund@2: no worker on refunds serves it: deploy a build that does",
    ]
    assert gone.active == {"refund": 1}


def with_open_cases(*cases: str) -> Registry:
    """Production with refund 1 activated, then refund 2; `cases` opened on refund 1 before."""
    registry, _ = activate(production(SERVED), activating(REFUND_1))
    for case in cases:
        registry, answer = opened(registry, Opening(case, "refunds", REFUND_1))
        assert answer.done
    registry, _ = activate(registry, activating(REFUND_2))
    return registry


def test_a_case_opens_only_on_the_active_release() -> None:
    # On the active release, with its digest, on the queue it was activated on: else refused,
    # saying why, and nothing recorded (brief, D51).
    registry = with_open_cases()
    refused = [
        Opening("refund-7", "refunds", REFUND_1),
        Opening("refund-7", "refunds", Released("refund", 2, Hash(1, "99" * 32))),
        Opening("refund-7", "refunds-old", REFUND_2),
        Opening("claim-7", "refunds", Released("claim", 1, Hash(1, "33" * 32))),
        Opening("refund-7", "refunds", None),
    ]
    said = [opened(registry, asked)[1].said for asked in refused]
    assert said == [
        ["refund-7 can't open on refund 1: refund 2 is active in production"],
        ["refund-7 can't open on refund 2: production's refund 2 has another digest"],
        ["refund-7 can't open on refund 2 on refunds-old: production activated it on refunds"],
        ["claim-7 can't open on claim 1: production has no claim activated"],
        ["refund-7 can't open as a draft in production: open it on a release"],
    ]
    after, answer = opened(registry, Opening("refund-7", "refunds", REFUND_2))
    assert answer.done and open_on(after, REFUND_2) == ["refund-7"]
    again, twice = opened(after, Opening("refund-7", "refunds", REFUND_2))  # an activity retried
    assert twice.done and again == after


def test_an_environment_is_production_unless_made_for_development() -> None:
    # A draft opens only in an environment created for development; hardened, it is production,
    # and nothing makes it a development one again: stricter downstream, never looser.
    staging = Registry("staging", development=True)
    _, draft = opened(staging, Opening("refund-7", "refunds", None))
    assert draft.done and draft.said == ["refund-7 opened as a draft in staging"]
    hardened, answer = harden(staging, "pia")
    assert answer.said == ["pia made staging a production environment: drafts no longer open"]
    _, refused = opened(hardened, Opening("refund-8", "refunds", None))
    assert refused.said == ["refund-8 can't open as a draft in staging: open it on a release"]
    _, again = harden(hardened, "pia")
    assert again.said == ["staging is a production environment already"]
    assert Registry("production").development is False  # the default


def test_a_release_with_open_cases_is_not_retired() -> None:
    # Refused while active, or while a case is open on it; a case Temporal says has ended without
    # saying it closed (terminated from outside) is dropped, saying so, and never blocks it.
    registry = with_open_cases("refund-7", "refund-8", "refund-9")
    _, active = retire(registry, Retiring(REFUND_2, "pia"), {})
    assert active.said == [
        "refund 2 not retired: it is active in production: activate another first"
    ]
    ended = {"refund-8": "terminated"}  # what the registry's activity found; the rest run
    after, refused = retire(registry, Retiring(REFUND_1, "pia"), ended)
    assert not refused.done
    assert refused.said == [
        "refund-8 ended (terminated) without saying it closed: no longer open on refund 1",
        (
            "refund 1 not retired: 2 cases are open on it in production (refund-7, refund-9): "
            "migrate them, or let them close"
        ),
    ]
    assert open_on(after, REFUND_1) == ["refund-7", "refund-9"]
    after, _ = closed(after, "refund-7")
    after, _ = moved(after, Moving("refund-9", REFUND_2))
    after, done = retire(after, Retiring(REFUND_1, "pia"), {})
    assert done.said == ["pia retired refund 1 in production"]
    assert after.retired == ["refund 1"] and after.log[-1] == done.said[0]


def test_a_retired_release_starts_nothing() -> None:
    # Retired for good: it opens no case, is no migration's target and is never activated again;
    # a release never activated here is no target either, since activation never checked it.
    registry, _ = retire(with_open_cases(), Retiring(REFUND_1, "pia"), {})
    _, opening = opened(registry, Opening("refund-7", "refunds", REFUND_1))
    _, moving = moved(registry, Moving("refund-7", REFUND_1))
    _, activating_it = activate(registry, activating(REFUND_1))
    _, again = retire(registry, Retiring(REFUND_1, "pia"), {})
    refund_3 = Released("refund", 3, Hash(1, "44" * 32))
    _, never = moved(registry, Moving("refund-7", refund_3))
    _, unknown = retire(registry, Retiring(refund_3, "pia"), {})
    assert [
        opening.said,
        moving.said,
        activating_it.said,
        again.said,
        never.said,
        unknown.said,
    ] == [
        ["refund-7 can't open on refund 1: refund 1 is retired in production"],
        ["refund-7 can't move to refund 1: refund 1 is retired in production"],
        [
            "refund 1 not activated in production:",
            "refund 1 is retired in production: it opens no case",
        ],
        ["refund 1 is retired in production already"],
        ["refund-7 can't move to refund 3: production never activated refund 3: activate it first"],
        ["refund 3 not retired: production never activated it"],
    ]


KYC_CASES = worker("refunds-a", SERVES, binds=KYC_BOUND)


def test_a_workflow_type_never_moves_under_open_cases() -> None:
    # Refund 1 calls kyc.check@1, bound to KycCheck. While a case is open on it, a worker binding
    # it to another type is refused; another task queue is taken (brief, D29).
    registry = production(KYC_CASES)
    released = Activating(
        REFUND_1, WITH_KYC, "refunds", {"refunds": ["refunds-a"], "kyc": ["kyc-a"]}, "pia"
    )
    registry, _ = publish(registry, team("kyc-a", {"kyc.check@1": KYC}))
    registry, done = activate(registry, released)
    assert done.done
    registry, _ = opened(registry, Opening("refund-7", "refunds", REFUND_1))
    moved_queue = worker("refunds-b", SERVES, binds={"kyc.check@1": Bound("KycCheck", "kyc-2")})
    retyped = worker("refunds-c", SERVES, binds={"kyc.check@1": Bound("KycCheckV2", "kyc")})
    registry, queue_moved = publish(registry, moved_queue)
    _, type_moved = publish(registry, retyped)
    assert queue_moved.done
    assert type_moved.said == [
        (
            "kyc.check@1 is bound to KycCheck, and 1 open case of refund 1 calls it: a workflow type "
            "never moves under open cases; move its task queue, or bind a new contract version"
        )
    ]
    registry, _ = closed(registry, "refund-7")
    _, taken = publish(registry, retyped)
    assert taken.done  # no open case calls it now
