"""The only module that talks to the AI provider (OpenAI or Anthropic, set by AI_PROVIDER).

Every call asks for structured output validated against a Pydantic model, and
every failure is turned into an AIError whose message is safe to show the user
(no exception text, no key, no provider internals).
"""

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger("ai")

T = TypeVar("T", bound=BaseModel)

_client = None

SETUP_HINT = "python -m backend.set_api_key"


class AIError(Exception):
    """Failure the user can be told about. `user_message` is Arabic, safe to display."""

    def __init__(self, user_message: str, *, retryable: bool = True):
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


class AIOutputInvalid(AIError):
    """The model answered, but the content broke our rules; `problems` are fed back on retry."""

    def __init__(self, problems: list[str]):
        super().__init__("أنتج الذكاء الاصطناعي مخرجات غير صالحة. حاول مرة أخرى.")
        self.problems = problems


# Safe user-facing messages: (Arabic text, retryable)
AUTH_FAILED = (f"مفتاح الذكاء الاصطناعي غير صالح. حدّثه عبر: {SETUP_HINT}", False)
NO_PERMISSION = ("المفتاح لا يملك صلاحية استخدام النموذج المحدد.", False)
MODEL_NOT_FOUND = ("النموذج المحدد في الإعدادات (AI_MODEL) غير موجود.", False)
RATE_LIMITED = ("تم تجاوز حد الطلبات أو الرصيد لدى مزود الذكاء الاصطناعي. انتظر قليلًا أو راجع الرصيد.", True)
SERVICE_ERROR = ("تعذّر الحصول على رد من خدمة الذكاء الاصطناعي. حاول مرة أخرى.", True)
CONNECTION_ERROR = ("تعذّر الاتصال بخدمة الذكاء الاصطناعي. تحقق من الإنترنت ثم حاول مرة أخرى.", True)
REFUSED = ("رفض نموذج الذكاء الاصطناعي هذا الطلب. جرّب مرة أخرى أو عدّل الهدف المكتوب في الملف.", True)


def _fail(kind: tuple[str, bool]) -> AIError:
    return AIError(kind[0], retryable=kind[1])


def _schema_problems(e: ValidationError) -> AIOutputInvalid:
    return AIOutputInvalid([f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:15]])


def generate_structured(
    prompt: str, output_model: type[T], *, task: str, max_tokens: int = 32000, effort: str | None = None
) -> T:
    """Send one prompt and return the response parsed into `output_model`.
    `effort` overrides AI_EFFORT (e.g. AI_FAST_EFFORT for quick in-game turns)."""
    if not config.ai_configured():
        raise AIError(f"مفتاح الذكاء الاصطناعي غير مُعدّ على الخادم. شغّل: {SETUP_HINT}", retryable=False)
    effort = effort or config.AI_EFFORT
    if config.AI_PROVIDER == "openai":
        return _openai(prompt, output_model, task=task, max_tokens=max_tokens, effort=effort)
    return _anthropic(prompt, output_model, task=task, max_tokens=max_tokens, effort=effort)


# ---------------------------------------------------------------------------
# OpenAI (Responses API + structured outputs)
# ---------------------------------------------------------------------------

def _openai(prompt: str, output_model: type[T], *, task: str, max_tokens: int, effort: str) -> T:
    import openai

    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=config.AI_API_KEY, timeout=config.AI_TIMEOUT_SECONDS, max_retries=2)
    try:
        response = _client.responses.parse(
            model=config.AI_MODEL,
            input=[{"role": "user", "content": prompt}],
            text_format=output_model,
            reasoning={"effort": effort},
            max_output_tokens=max_tokens,
            store=False,  # do not keep assessment content on the provider side
        )
    except openai.AuthenticationError:
        log.error("[%s] authentication failed — check OPENAI_API_KEY", task)
        raise _fail(AUTH_FAILED)
    except openai.PermissionDeniedError:
        log.error("[%s] permission denied for model %s", task, config.AI_MODEL)
        raise _fail(NO_PERMISSION)
    except openai.NotFoundError:
        log.error("[%s] model not found: %s", task, config.AI_MODEL)
        raise _fail(MODEL_NOT_FOUND)
    except openai.RateLimitError:
        log.warning("[%s] rate limited / quota exceeded", task)
        raise _fail(RATE_LIMITED)
    except openai.APIStatusError as e:
        log.error("[%s] API error status=%s request_id=%s", task, e.status_code, e.request_id)
        raise _fail(SERVICE_ERROR)
    except openai.APIConnectionError:
        log.error("[%s] connection error / timeout", task)
        raise _fail(CONNECTION_ERROR)
    except ValidationError as e:
        log.warning("[%s] output failed schema validation", task)
        raise _schema_problems(e)

    usage = response.usage
    log.info(
        "[%s] provider=openai model=%s status=%s in=%s out=%s id=%s",
        task, response.model, response.status,
        usage.input_tokens if usage else "?", usage.output_tokens if usage else "?", response.id,
    )

    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        if reason == "content_filter":
            raise _fail(REFUSED)
        raise AIOutputInvalid(["Output was cut off before completion. Keep every field concise."])
    for item in response.output:
        for part in getattr(item, "content", None) or []:
            if part.type == "refusal":
                raise _fail(REFUSED)
    if response.output_parsed is None:
        raise AIOutputInvalid(["Response did not contain JSON matching the schema."])
    return response.output_parsed


# ---------------------------------------------------------------------------
# Anthropic (Messages API + structured outputs)
# ---------------------------------------------------------------------------

def _anthropic(prompt: str, output_model: type[T], *, task: str, max_tokens: int, effort: str) -> T:
    import anthropic

    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.AI_API_KEY, timeout=config.AI_TIMEOUT_SECONDS, max_retries=2)
    try:
        with _client.beta.messages.stream(
            model=config.AI_MODEL,
            max_tokens=max_tokens,
            output_config={"effort": effort},
            output_format=output_model,
            # If a safety classifier declines (e.g. security-related questions),
            # let the API retry on its recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        log.error("[%s] authentication failed — check ANTHROPIC_API_KEY", task)
        raise _fail(AUTH_FAILED)
    except anthropic.PermissionDeniedError:
        log.error("[%s] permission denied for model %s", task, config.AI_MODEL)
        raise _fail(NO_PERMISSION)
    except anthropic.NotFoundError:
        log.error("[%s] model not found: %s", task, config.AI_MODEL)
        raise _fail(MODEL_NOT_FOUND)
    except anthropic.RateLimitError:
        log.warning("[%s] rate limited", task)
        raise _fail(RATE_LIMITED)
    except anthropic.APIStatusError as e:
        log.error("[%s] API error status=%s request_id=%s", task, e.status_code, e.request_id)
        raise _fail(SERVICE_ERROR)
    except anthropic.APIConnectionError:
        log.error("[%s] connection error / timeout", task)
        raise _fail(CONNECTION_ERROR)
    except ValidationError as e:
        log.warning("[%s] output failed schema validation", task)
        raise _schema_problems(e)

    usage = response.usage
    log.info(
        "[%s] provider=anthropic model=%s stop=%s in=%s out=%s id=%s",
        task, response.model, response.stop_reason, usage.input_tokens, usage.output_tokens, response.id,
    )

    if response.stop_reason == "refusal":
        raise _fail(REFUSED)
    if response.stop_reason == "max_tokens":
        raise AIOutputInvalid(["Output was cut off (max_tokens). Keep every field concise."])
    if response.parsed_output is None:
        raise AIOutputInvalid(["Response did not contain JSON matching the schema."])
    return response.parsed_output
