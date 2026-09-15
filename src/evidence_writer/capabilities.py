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
        "避免先抛抽象结论，再用材料装饰。",
        "现实评论、文化评论、产业/政策题；安全包中已有可观察对象、制度、关系、文本或数据。",
        "重要判断尽量先落在已授权的具体对象、关系或材料上，再向外延伸；不要新增例子来支撑判断。",
        "安全包没有足够具体材料；文章本身是纯个人感受。",
        "判断所指对象清楚；没有新增事实；没有变成“多写细节”。",
    ),
    CapabilityDefinition(
        "CAP-REDUCE-EXPLANATION",
        "减少“事实后再解释一遍”的 AI 逻辑水印。",
        "facts/judgments already illuminate each other; Writer tends to append summaries/mechanisms/meaning.",
        "when authorized material already carries judgment, do not add same-meaning explanation; preserve necessary logic, don’t close every paragraph.",
        "medical/policy/professional explanation if omission causes substantive misunderstanding.",
        "information intact, logic intact, author judgment still visible.",
    ),
    CapabilityDefinition(
        "CAP-EMOTION-DELAYED-NAMING",
        "real emotion without immediately naming/defending/uplifting it.",
        "personal experience/memorial/controlled emotion; Author Intent has real emotion; authorized actions/relations/objects/experience position exist.",
        "let authorized action/relation/waiting/friction/hesitation carry emotion first; direct feeling later if needed; do not justify why feeling is correct.",
        "no real experience; industry/professional explainer; risk key misunderstanding.",
        "emotion perceptible but not managed; no fabricated life detail; direct emotion not sterilized.",
    ),
    CapabilityDefinition(
        "CAP-OPEN-QUESTION",
        "allow unresolved question; avoid “困境—领悟—升华”.",
        "CENTRAL_TENSION lacks sufficient answer; author wants incompleteness.",
        "if material lacks full answer, leave real unresolved question; do not fabricate conclusion for structural completeness.",
        "explicit explanation/operational guidance/clear judgment required.",
        "openness comes from material resistance, not faux profundity; reader still knows topic.",
    ),
    CapabilityDefinition(
        "CAP-QUIET-ENDING",
        "avoid summary/uplift/gold-line ending.",
        "ENDING_DESTINATION = QUIET_STOP or OPEN_REMAINDER; main judgment done.",
        "stop near last still-pressurized fact/action/judgment/question; no repeat conclusion; no higher abstraction.",
        "knowledge article needs explicit conclusion/steps/boundary.",
        "natural stop; no second uplift.",
    ),
    CapabilityDefinition(
        "CAP-KNOWLEDGE-AS-PROCESS",
        "professional knowledge without textbook/terminology display.",
        "medicine/tech/consumer/professional explanation; safe package has real phenomena/process/verifiable sequence.",
        "enter terms/explanation from authorized phenomenon/process/problem, preserving accuracy; knowledge serves current problem.",
        "definition must precede; no process material.",
        "object understood before term; no unauthorized “accessible” analogy facts.",
    ),
    CapabilityDefinition(
        "CAP-BOUNDED-AUTHOR-POSITION",
        "author judgment/emotion present without expanding fact authority.",
        "viewpoint/value judgment; Author Intent has clear stance.",
        "first-person care/doubt/dislike/delight/irony/respect allowed; external assertions still only from handoff.",
        "pure explainer and author position adds no value.",
        "distinguish “作者怎么看” from “外部世界是什么”; “我觉得” not used to package new facts.",
    ),
    CapabilityDefinition(
        "CAP-FACTS-ON-ACTION-LINE",
        "dense facts not background manual.",
        "safe package has real verified timeline/action/event process.",
        "attach authorized facts to real action/timeline; institutions/numbers/rules enter with process.",
        "no real action line; only statistical aggregation; requires fabricated scene.",
        "facts have position/rhythm; no fabricated scene/interview/dialogue/actions.",
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
