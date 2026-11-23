"""Validates and grounds a model reply before it can be stored (US-19, US-20).

Checks, in order:
1. The reply parses into SummaryDraft (schema, limits, review_status == DRAFT).
2. Every follow-up action matches a documented action after normalising case and punctuation.
3. Every number in the draft appears in the source the model was given.
4. No clinical-decision wording appears unless the same word is in the source note.
5. The staff message contains no patient-contact wording.

Any failure raises AIError, which summary_service turns into a FAILED row and a 502.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from pydantic import ValidationError

from app.ai.azure_client import INVALID_OUTPUT, UNGROUNDED_OUTPUT, AIError
from app.ai.prompt import PreparedPrompt
from app.schemas.summary import SummaryDraft

# Clinical-decision wording the model must not introduce.
BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdiagnos\w*",
        r"\bprescri\w*",
        r"\burgen\w*",
        r"\beligib\w*",
        r"\btriag\w*",
        r"\brandomi[sz]\w*",
        r"\brecommend\w*\s+(?:a\s+|the\s+)?treatment\w*",
        r"\btreatment\s+plan\w*",
        r"\bshould\s+(?:start|stop|take|increase|decrease|begin|continue)\b",
    )
]

# Wording that would turn the staff note into a message to the participant.
CONTACT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdear\b",
        r"\bplease\s+contact\b",
        r"\bcall\s+(?:you|the\s+participant)\b",
        r"\bwe\s+will\s+(?:call|text|email|contact)\b",
        r"\btext\s+message\b",
        r"\bsms\b",
    )
]

NUMBER_PATTERN = re.compile(r"\d+(?:[.,/:-]\d+)*")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _strip_code_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


def parse_draft(raw: str) -> SummaryDraft:
    if not raw or not raw.strip():
        raise AIError(INVALID_OUTPUT, "empty reply")
    try:
        data = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError:
        raise AIError(INVALID_OUTPUT, "reply is not valid JSON") from None
    try:
        return SummaryDraft.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise AIError(INVALID_OUTPUT, f"schema check failed on: {', '.join(fields)}") from None


def _draft_texts(draft: SummaryDraft) -> list[str]:
    texts = [draft.visit_summary, *draft.recorded_observations, *draft.follow_up_actions, *draft.missing_information]
    if draft.follow_up_message_draft:
        texts.append(draft.follow_up_message_draft)
    return texts


def check_actions_grounded(draft: SummaryDraft, documented_actions: Iterable[str]) -> None:
    allowed = {normalize(a) for a in documented_actions}
    for action in draft.follow_up_actions:
        if normalize(action) not in allowed:
            raise AIError(UNGROUNDED_OUTPUT, "follow-up action not found in documented actions")


def check_numbers_grounded(draft: SummaryDraft, source_text: str) -> None:
    source_numbers = set(NUMBER_PATTERN.findall(source_text))
    for text in _draft_texts(draft):
        for number in NUMBER_PATTERN.findall(text):
            if number not in source_numbers and number not in source_text:
                raise AIError(UNGROUNDED_OUTPUT, "draft contains a number not present in the source")


def _introduced(patterns: Iterable[re.Pattern], text: str, source_lower: str) -> bool:
    """True if a pattern matches the draft text but its matched words are not in the source."""
    for pattern in patterns:
        for match in pattern.finditer(text):
            if match.group(0).lower() not in source_lower:
                return True
    return False


def check_blocked_wording(draft: SummaryDraft, source_text: str) -> None:
    source_lower = source_text.lower()
    for text in _draft_texts(draft):
        if _introduced(BLOCKED_PATTERNS, text, source_lower):
            raise AIError(UNGROUNDED_OUTPUT, "draft contains blocked clinical-decision wording")
    if draft.follow_up_message_draft and _introduced(CONTACT_PATTERNS, draft.follow_up_message_draft, source_lower):
        raise AIError(UNGROUNDED_OUTPUT, "staff message contains patient-contact wording")


def validate_draft(raw: str, prepared: PreparedPrompt) -> SummaryDraft:
    """Return a SummaryDraft that is safe to store, or raise AIError."""
    draft = parse_draft(raw)
    if not draft.visit_summary.strip() and not draft.missing_information:
        raise AIError(INVALID_OUTPUT, "both visit_summary and missing_information are empty")
    check_actions_grounded(draft, prepared.documented_actions)
    check_numbers_grounded(draft, prepared.source_text)
    check_blocked_wording(draft, prepared.source_text)
    return draft