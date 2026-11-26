"""Validates and grounds a model reply before it can be stored (US-19, US-20).

Checks, in order:
1. The reply parses into SummaryDraft (1-5 summary points, at most 3 follow-up
   actions, length limits, review_status == DRAFT).
2. Every number in the draft appears in the source the model was given
   (compound forms such as "28/30" are split, so reformatting is allowed but
   calculated numbers are not).
3. No clinical-decision wording appears in the points or actions unless the same
   word is in the source note.
4. Follow-up actions contain no patient-contact wording.

The AI proposes the follow-up actions; the reviewer confirms, edits or adds to
them before anything is approved.

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
        r"\bmedicat\w*",
        r"\bdos(?:e|es|age|ing)\b",
        r"\brecommend\w*\s+(?:a\s+|the\s+)?treatment\w*",
        r"\btreatment\s+plan\w*",
        r"\bshould\s+(?:start|stop|take|increase|decrease|begin|continue)\b",
    )
]

# Wording that would turn a staff action into contact with the participant.
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
NUMBER_PART = re.compile(r"\d+(?:\.\d+)?")


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
    return [*draft.summary_points, *draft.follow_up_actions]


def check_numbers_grounded(draft: SummaryDraft, source_text: str) -> None:
    source_parts = set(NUMBER_PART.findall(source_text))
    for text in _draft_texts(draft):
        for number in NUMBER_PATTERN.findall(text):
            for part in NUMBER_PART.findall(number):
                if part not in source_parts:
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
    for action in draft.follow_up_actions:
        if _introduced(CONTACT_PATTERNS, action, source_lower):
            raise AIError(UNGROUNDED_OUTPUT, "follow-up action contains patient-contact wording")


def validate_draft(raw: str, prepared: PreparedPrompt) -> SummaryDraft:
    """Return a SummaryDraft that is safe to store, or raise AIError."""
    draft = parse_draft(raw)
    check_numbers_grounded(draft, prepared.source_text)
    check_blocked_wording(draft, prepared.source_text)
    return draft