"""The contract hash: what a contract promises, as a SHA-256 (everything but its wording)."""

import hashlib
import json

from ventoux.core.contract import ActivityContract


def contract_hash(contract: ActivityContract) -> str:
    """SHA-256 of what the contract promises: everything but `display`, schemas as JSON Schema."""
    promise = contract.model_dump(mode="json", exclude={"display", "input", "output"})
    promise["input"] = contract.input.model_json_schema()
    promise["output"] = contract.output.model_json_schema()
    promise["outcomes"] = sorted(
        contract.outcomes
    )  # a set of answers: their order promises nothing
    # Canonical JSON: the same promise always gives the same bytes, so the same hash.
    canonical = json.dumps(promise, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
