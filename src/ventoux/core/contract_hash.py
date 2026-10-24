"""The contract hash: what a contract promises, as a SHA-256 (everything but its wording)."""

import hashlib
import json

from ventoux.core.contract import Contract
from ventoux.core.promise import promise_of


def contract_hash(contract: Contract) -> str:
    """SHA-256 of what the contract promises (`promise_of`)."""
    return promise_hash(promise_of(contract))


def promise_hash(promise: object) -> str:
    """SHA-256 of a promise: the hash `contracts.lock.json` records (method 1)."""
    # Canonical JSON: the same promise always gives the same bytes, so the same hash.
    canonical = json.dumps(promise, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
