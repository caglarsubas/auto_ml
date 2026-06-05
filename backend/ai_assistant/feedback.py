"""Assistant response feedback collection for Prometa.

The chat UI sends feedback after the assistant turn has completed, so this
module validates the payload, redacts obvious PII by default, and records a
dedicated Prometa ``feedback.record`` span with the best target ids available.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .prometa_config import (
    flush as prometa_flush,
    has_active_span,
    record_user_feedback,
    set_user_feedback,
)


DEFAULT_FEEDBACK_SOURCE = 'declarai-ai-chat-panel'
MAX_COMMENT_CHARS = 4096
MAX_ID_CHARS = 256
MAX_SOURCE_CHARS = 80

_TOKEN_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_PHONE_RE = re.compile(
    r'(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)'
)
_LONG_NUMBER_RE = re.compile(r'\b\d{9,}\b')


class FeedbackValidationError(ValueError):
    """Structured validation failure for the feedback API."""

    def __init__(self, errors: dict[str, str]):
        super().__init__('invalid feedback payload')
        self.errors = errors


@dataclass(frozen=True)
class AssistantFeedback:
    liked: bool | None
    rating: int | None
    comment: str | None
    source: str
    feedback_id: str
    user_id: str | None
    submitted_at: str
    target_trace_id: str | None
    target_span_id: str | None
    target_session_id: str | None
    comment_redacted: bool = False

    def prometa_kwargs(self) -> dict[str, Any]:
        return {
            'liked': self.liked,
            'rating': self.rating,
            'comment': self.comment,
            'source': self.source,
            'feedback_id': self.feedback_id,
            'user_id': self.user_id,
            'submitted_at': self.submitted_at,
            'target_trace_id': self.target_trace_id,
            'target_span_id': self.target_span_id,
            'target_session_id': self.target_session_id,
        }


def normalize_feedback_payload(data: dict[str, Any], request=None) -> AssistantFeedback:
    errors: dict[str, str] = {}
    allow_pii = _allow_pii(data)

    liked = _normalize_liked(data.get('liked'), errors)
    rating = _normalize_rating(data.get('rating'), errors)
    comment, comment_redacted = _normalize_comment(
        data.get('comment'), allow_pii=allow_pii, errors=errors)

    if liked is None and rating is None and not comment:
        errors['feedback'] = 'Provide liked, rating, or comment.'

    source = _normalize_source(data.get('source'))
    feedback_id = _normalize_id(data.get('feedback_id')) or str(uuid.uuid4())
    submitted_at = _normalize_submitted_at(data.get('submitted_at'), errors)

    target_trace_id = _first_valid_id(data, 'target_trace_id', 'trace_id', 'chat_trace_id')
    target_span_id = _first_valid_id(data, 'target_span_id', 'span_id', 'chat_span_id')
    target_session_id = _first_valid_id(
        data,
        'target_session_id',
        'session_id',
        'conversation_id',
        'chat_session_id',
    )
    if target_session_id is None:
        file_id = _normalize_file_id(data.get('file_id'))
        if file_id is not None:
            target_session_id = f'declarai-file-{file_id}'

    user_id = _normalize_user_id(
        data.get('user_id') or _request_user_id(request),
        allow_pii=allow_pii,
    )

    if errors:
        raise FeedbackValidationError(errors)

    return AssistantFeedback(
        liked=liked,
        rating=rating,
        comment=comment,
        source=source,
        feedback_id=feedback_id,
        user_id=user_id,
        submitted_at=submitted_at,
        target_trace_id=target_trace_id,
        target_span_id=target_span_id,
        target_session_id=target_session_id,
        comment_redacted=comment_redacted,
    )


def submit_feedback_to_prometa(feedback: AssistantFeedback,
                               *, prefer_active_span: bool = False) -> dict[str, Any]:
    kwargs = feedback.prometa_kwargs()
    recorded = False
    method = 'record_user_feedback'

    if prefer_active_span and has_active_span():
        recorded = set_user_feedback(**kwargs)
        method = 'set_user_feedback'

    if not recorded:
        recorded = record_user_feedback(**kwargs)
        method = 'record_user_feedback'

    return {
        'status': 'success',
        'feedback_id': feedback.feedback_id,
        'prometa_recorded': recorded,
        'prometa_method': method,
        'comment_redacted': feedback.comment_redacted,
        'user_id_included': bool(feedback.user_id),
        'target': {
            'trace_id': feedback.target_trace_id,
            'span_id': feedback.target_span_id,
            'session_id': feedback.target_session_id,
        },
    }


def _allow_pii(data: dict[str, Any]) -> bool:
    if data.get('allow_pii') is True or data.get('allow_pii_feedback') is True:
        return True
    return os.environ.get('PROMETA_FEEDBACK_ALLOW_PII') == '1'


def _normalize_liked(value: Any, errors: dict[str, str]) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    errors['liked'] = 'liked must be a boolean.'
    return None


def _normalize_rating(value: Any, errors: dict[str, str]) -> int | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        errors['rating'] = 'rating must be an integer from 1 to 5.'
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError):
        errors['rating'] = 'rating must be an integer from 1 to 5.'
        return None
    if rating < 1 or rating > 5:
        errors['rating'] = 'rating must be an integer from 1 to 5.'
        return None
    return rating


def _normalize_comment(value: Any, *, allow_pii: bool,
                       errors: dict[str, str]) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    comment = str(value).strip()
    if not comment:
        return None, False
    if len(comment) > MAX_COMMENT_CHARS:
        errors['comment'] = f'comment must be {MAX_COMMENT_CHARS} characters or fewer.'
        return None, False
    if allow_pii:
        return comment, False

    redacted = comment
    redacted = _EMAIL_RE.sub('[redacted-email]', redacted)
    redacted = _SSN_RE.sub('[redacted-ssn]', redacted)
    redacted = _PHONE_RE.sub('[redacted-phone]', redacted)
    redacted = _LONG_NUMBER_RE.sub('[redacted-number]', redacted)
    return redacted, redacted != comment


def _normalize_source(value: Any) -> str:
    source = str(value or DEFAULT_FEEDBACK_SOURCE).strip()[:MAX_SOURCE_CHARS]
    return source if _TOKEN_RE.match(source) else DEFAULT_FEEDBACK_SOURCE


def _normalize_submitted_at(value: Any, errors: dict[str, str]) -> str:
    if value is None or value == '':
        return _utc_now_iso()
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and len(value) <= 128:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            errors['submitted_at'] = 'submitted_at must be an ISO timestamp.'
            return _utc_now_iso()
    else:
        errors['submitted_at'] = 'submitted_at must be an ISO timestamp.'
        return _utc_now_iso()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _first_valid_id(data: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = _normalize_id(data.get(name))
        if value:
            return value
    return None


def _normalize_id(value: Any, *, max_chars: int = MAX_ID_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > max_chars:
        return None
    return text if _TOKEN_RE.match(text) else None


def _normalize_file_id(value: Any) -> int | None:
    try:
        file_id = int(value)
    except (TypeError, ValueError):
        return None
    return file_id if file_id > 0 else None


def _normalize_user_id(value: Any, *, allow_pii: bool) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 128:
        return None
    if allow_pii:
        return text
    if _EMAIL_RE.search(text) or _PHONE_RE.search(text) or _SSN_RE.search(text):
        return None
    return text if _TOKEN_RE.match(text) else None


def _request_user_id(request) -> str | None:
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    value = getattr(user, 'id', None)
    if value is not None:
        return str(value)
    get_username = getattr(user, 'get_username', None)
    if callable(get_username):
        return get_username()
    return getattr(user, 'username', None)


@method_decorator(csrf_exempt, name='dispatch')
class AIFeedbackView(APIView):
    """POST /api/ai-assistant/feedback/"""

    def post(self, request, *args, **kwargs):
        try:
            feedback = normalize_feedback_payload(request.data, request=request)
            result = submit_feedback_to_prometa(feedback, prefer_active_span=False)
            return Response(result, status=status.HTTP_200_OK)
        except FeedbackValidationError as exc:
            return Response(
                {'status': 'error', 'errors': exc.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            prometa_flush()
