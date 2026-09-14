"""Contract core for Evidence Writer.

No LLM runtime is included in this release.
"""

from .contracts import EvidenceWriterBundle
from .policies import (
    PolicyViolation,
    ensure_bundle_valid,
    ensure_contract_data_valid,
    validate_bundle,
    validate_contract_data,
)

__all__ = [
    "EvidenceWriterBundle",
    "PolicyViolation",
    "ensure_bundle_valid",
    "ensure_contract_data_valid",
    "validate_bundle",
    "validate_contract_data",
]
