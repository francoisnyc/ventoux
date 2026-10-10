"""The contract hash: what a contract promises, as a SHA-256 (everything but its wording)."""

import hashlib
import json

from ventoux.core.contract import Contract


def contract_hash(contract: Contract) -> str:
    """SHA-256 of what the contract promises: everything but `display`, schemas as JSON Schema."""
    # Pydantic: `model_dump(mode="json")` gives the object as plain JSON values (dicts, lists,
    # texts, numbers); `model_json_schema()` describes a model class as JSON Schema.
    promise = contract.model_dump(mode="json", exclude={"display", "input", "output"})
    promise["input"] = contract.input.model_json_schema()
    promise["output"] = contract.output.model_json_schema()
    # The outcomes are a set of answers: their order promises nothing. A workflow has none.
    if "outcomes" in promise:
        promise["outcomes"] = sorted(promise["outcomes"])
    # Canonical JSON: the same promise always gives the same bytes, so the same hash.
    canonical = json.dumps(promise, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
