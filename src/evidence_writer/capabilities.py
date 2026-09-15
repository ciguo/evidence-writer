"""Closed, deterministic runtime registry for production writing capabilities.

Capability definitions are internal instructions, not evidence.  In particular,
they cannot expand the factual authority granted by ``WriterHandoff``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


CAPABILITY_REGISTRY_VERSION = "0.1.0"


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    objective: str
    trigger: str
    execution_directive: str
    skip_if: str
    success_check: str
    fact_authority: Literal["NONE"] = "NONE"


_DEFINITIONS = (
    CapabilityDefinition(
        "CAP-JUDGMENT-ON-MATERIAL",
        "Keep judgments visibly bounded by the available material.",
        "The draft needs interpretation but the evidence supports only a bounded judgment.",
        "State the material first, then make the narrowest supported judgment and mark its limit.",
        "Skip when the material does not support any judgment or the point is already explicit.",
        "Every judgment is traceable to authorized material and remains within its stated scope.",
    ),
    CapabilityDefinition(
        "CAP-REDUCE-EXPLANATION",
        "Reduce explanation that repeats what the evidence already makes clear.",
        "The intended argument is obscured by repeated or overextended explanation.",
        "Remove repeated explanation and retain only the steps needed to connect evidence to position.",
        "Skip when reduction would hide a qualification, evidence boundary, or necessary reasoning step.",
        "The reasoning remains understandable without repetition or lost qualifications.",
    ),
    CapabilityDefinition(
        "CAP-EMOTION-DELAYED-NAMING",
        "Let supported material establish the situation before naming the intended emotion.",
        "Author Intent calls for emotion that should emerge after the material is presented.",
        "Delay naming the emotion until after the authorized material and its limits are established.",
        "Skip when naming emotion would imply unsupported psychology or when no emotional naming is needed.",
        "Emotional language arrives after the material and makes no claim about another person's inner state.",
    ),
    CapabilityDefinition(
        "CAP-OPEN-QUESTION",
        "End a line of thought with a bounded question that keeps inquiry open.",
        "The evidence leaves a consequential uncertainty aligned with the intended destination.",
        "Convert the unresolved, evidence-bounded issue into an open question rather than a conclusion.",
        "Skip when the question would introduce a new premise, imply a fact, or evade an available conclusion.",
        "The question follows from authorized material and does not smuggle in an unsupported assertion.",
    ),
    CapabilityDefinition(
        "CAP-QUIET-ENDING",
        "Close without overstating certainty or adding a rhetorical climax.",
        "The ending should preserve restraint after the central position has been established.",
        "End on the smallest supported observation, limit, or implication without summarizing everything again.",
        "Skip when the Author Intent requires a direct actionable close or an explicit open question.",
        "The ending is complete but restrained and introduces no new factual material.",
    ),
    CapabilityDefinition(
        "CAP-KNOWLEDGE-AS-PROCESS",
        "Present knowledge as a bounded process of observation, checking, and revision.",
        "The material distinguishes what is known now from what remains to be checked.",
        "Organize the passage around what was observed, what can be inferred, and what still requires verification.",
        "Skip when a process structure would imply research actions that did not occur or are not authorized.",
        "Each stage of knowing uses the correct evidence status and fabricates no research action.",
    ),
    CapabilityDefinition(
        "CAP-BOUNDED-AUTHOR-POSITION",
        "Express the author's position without turning it into factual authority.",
        "Author Intent supplies a position that must remain subordinate to the evidence boundary.",
        "Frame the position explicitly as the author's bounded stance and keep factual claims in the handoff's terms.",
        "Skip when the position conflicts with the evidence boundary or would assert unsupported expertise.",
        "The stance is clear, bounded, and cannot be mistaken for new evidence or professional judgment.",
    ),
    CapabilityDefinition(
        "CAP-FACTS-ON-ACTION-LINE",
        "Place authorized facts next to the action or decision they can legitimately inform.",
        "A factual point has a direct, supported bearing on an action line in the argument.",
        "Position the authorized fact immediately before the bounded action or decision it informs.",
        "Skip when the action did not occur, is not authorized, or the connection would imply causality or intent.",
        "The action line is anchored to authorized facts without fabricating action, outcome, or causal force.",
    ),
)

CAPABILITY_REGISTRY: Mapping[str, CapabilityDefinition] = MappingProxyType(
    {definition.capability_id: definition for definition in _DEFINITIONS}
)

if len(CAPABILITY_REGISTRY) != len(_DEFINITIONS):  # fail closed at import time
    raise RuntimeError("runtime capability IDs must be unique")


def get_capability(capability_id: str) -> CapabilityDefinition:
    """Return a registered definition, failing closed for unknown IDs."""

    try:
        return CAPABILITY_REGISTRY[capability_id]
    except KeyError as error:
        raise ValueError(f"unknown runtime capability ID: {capability_id}") from error
