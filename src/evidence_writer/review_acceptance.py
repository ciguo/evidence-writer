"""Deterministic acceptance rules for Final Review output."""

from __future__ import annotations

from .contracts import (
    DraftArtifact,
    ReviewAction,
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
)
from .policies import PolicyViolation


def _issue(
    out: list[PolicyViolation], code: str, path: str, message: str
) -> None:
    out.append(PolicyViolation(code, path, message))


def _apply_local_repairs(
    draft_text: str,
    findings: list[ReviewFinding],
) -> tuple[str | None, list[PolicyViolation]]:
    lines = draft_text.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    out: list[PolicyViolation] = []

    for index, finding in enumerate(findings):
        path = f"review.findings.{index}"
        original = finding.original_text
        repaired = finding.repaired_text
        start_line = finding.location.start_line
        end_line = finding.location.end_line

        if start_line < 1 or end_line < start_line or end_line > len(lines):
            _issue(
                out,
                "LOCAL_REPAIR_LOCATION_INVALID",
                f"{path}.location",
                "LOCAL_REPAIR location is outside the draft",
            )
            continue
        if not repaired or repaired == original or repaired not in original:
            _issue(
                out,
                "LOCAL_REPAIR_NOT_DELETION_ONLY",
                f"{path}.repaired_text",
                "LOCAL_REPAIR must be a non-empty deletion-only edit",
            )
            continue

        slice_start = sum(len(line) for line in lines[: start_line - 1])
        slice_end = sum(len(line) for line in lines[:end_line])
        located_text = draft_text[slice_start:slice_end]
        if located_text.count(original) != 1:
            _issue(
                out,
                "LOCAL_REPAIR_SOURCE_MISMATCH",
                f"{path}.original_text",
                "original_text must occur exactly once at the declared location",
            )
            continue
        replace_start = slice_start + located_text.index(original)
        replacements.append(
            (replace_start, replace_start + len(original), repaired)
        )

    replacements.sort(key=lambda item: item[0])
    for previous, current in zip(replacements, replacements[1:]):
        if previous[1] > current[0]:
            _issue(
                out,
                "LOCAL_REPAIR_OVERLAP",
                "review.findings",
                "LOCAL_REPAIR findings must not overlap",
            )

    if out:
        return None, out
    final_text = draft_text
    for start, end, repaired in reversed(replacements):
        final_text = final_text[:start] + repaired + final_text[end:]
    return final_text, out


def validate_review_acceptance(
    draft: DraftArtifact,
    review: ReviewResult,
) -> list[PolicyViolation]:
    """Reject any Final Review output that can expand the Draft's evidence."""

    out: list[PolicyViolation] = []
    if review.review_verdict is ReviewVerdict.PASS:
        if review.findings:
            _issue(
                out,
                "PASS_HAS_FINDINGS",
                "review.findings",
                "PASS cannot contain review findings",
            )
        if review.final_text != draft.draft_markdown:
            _issue(
                out,
                "PASS_TEXT_CHANGED",
                "review.final_text",
                "PASS final_text must exactly equal the reviewed draft",
            )
    elif review.review_verdict is ReviewVerdict.LOCAL_REPAIR:
        if any(
            finding.action is not ReviewAction.LOCAL_REPAIR
            for finding in review.findings
        ):
            _issue(
                out,
                "LOCAL_REPAIR_FINDINGS_INVALID",
                "review.findings",
                "LOCAL_REPAIR may contain local repair findings only",
            )
        computed, repair_violations = _apply_local_repairs(
            draft.draft_markdown,
            review.findings,
        )
        out.extend(repair_violations)
        if computed is not None and review.final_text != computed:
            _issue(
                out,
                "LOCAL_REPAIR_FINAL_MISMATCH",
                "review.final_text",
                "final_text must equal the deterministic local repairs",
            )
    else:
        if review.final_text is not None:
            _issue(
                out,
                "RETURN_TO_WRITER_HAS_FINAL",
                "review.final_text",
                "RETURN_TO_WRITER cannot produce final_text",
            )
        if any(
            finding.action is ReviewAction.LOCAL_REPAIR
            for finding in review.findings
        ):
            _issue(
                out,
                "RETURN_TO_WRITER_REPAIR_CONFLICT",
                "review.findings",
                "RETURN_TO_WRITER cannot contain local repairs",
            )
    return out
