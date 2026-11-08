"""Provider interfaces (PLAN.md section 9) plus shared retry / usage plumbing.

Implementations are chosen by configuration (`registry.py`). Every provider
call reports usage through `record_usage`, which writes a UsageLog row via a
pluggable sink (set by the app at startup) so this module stays DB-agnostic.
"""

from __future__ import annotations

import contextvars
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Non-retryable provider failure."""


class RetryableError(ProviderError):
    """Transient failure (timeout, 429, 5xx)."""

    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


@dataclass
class UsageContext:
    book_id: int | None = None
    page_id: int | None = None
    purpose: str = ""


_usage_ctx: contextvars.ContextVar[UsageContext | None] = contextvars.ContextVar("usage_ctx", default=None)


class usage_context:
    """`with usage_context(book_id=1, purpose="page"):` tags provider calls."""

    def __init__(self, **kw: Any):
        self.kw = kw
        self.token: contextvars.Token | None = None

    def __enter__(self) -> UsageContext:
        cur = _usage_ctx.get() or UsageContext()
        new = UsageContext(
            book_id=self.kw.get("book_id", cur.book_id),
            page_id=self.kw.get("page_id", cur.page_id),
            purpose=self.kw.get("purpose", cur.purpose),
        )
        self.token = _usage_ctx.set(new)
        return new

    def __exit__(self, *exc: Any) -> None:
        if self.token is not None:
            _usage_ctx.reset(self.token)


def current_usage_context() -> UsageContext:
    return _usage_ctx.get() or UsageContext()


@dataclass
class UsageRecord:
    provider: str
    model: str
    kind: str
    units: float
    est_cost_usd: float
    book_id: int | None = None
    page_id: int | None = None
    purpose: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


UsageSink = Callable[[UsageRecord], None]
_sinks: list[UsageSink] = []


def add_usage_sink(sink: UsageSink) -> None:
    if sink not in _sinks:
        _sinks.append(sink)


def remove_usage_sink(sink: UsageSink) -> None:
    if sink in _sinks:
        _sinks.remove(sink)


def clear_usage_sinks() -> None:
    _sinks.clear()


def record_usage(provider: str, model: str, kind: str, units: float, est_cost_usd: float, **extra: Any) -> None:
    ctx = current_usage_context()
    rec = UsageRecord(provider, model, kind, units, est_cost_usd, ctx.book_id, ctx.page_id, ctx.purpose, extra)
    for sink in list(_sinks):
        try:
            sink(rec)
        except Exception:  # pragma: no cover - logging must never break generation
            log.exception("usage sink failed")


def with_retries(
    fn: Callable[[], Any],
    *,
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Run `fn` retrying RetryableError with exponential backoff + jitter."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except RetryableError as e:
            last = e
            if i == attempts - 1:
                break
            delay = e.retry_after if e.retry_after is not None else min(max_delay, base_delay * (2**i))
            delay += random.uniform(0, delay * 0.1)
            log.warning("retryable provider error (%s); retry %d in %.1fs", e, i + 1, delay)
            sleep(delay)
    assert last is not None
    raise last


def classify_http_status(status: int, body: str, retry_after: str | None = None) -> None:
    """Raise the right error type for a non-2xx HTTP response."""
    if status == 429 or status >= 500 or status == 408:
        ra = None
        if retry_after:
            try:
                ra = float(retry_after)
            except ValueError:
                ra = None
        raise RetryableError(f"HTTP {status}: {body[:300]}", retry_after=ra)
    raise ProviderError(f"HTTP {status}: {body[:500]}")


# ------------------------------------------------------------------ interfaces


class ImageProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        size_hint: tuple[int, int] = (1024, 1024),
        reference_images: list[bytes] | None = None,
        seed: int | None = None,
    ) -> bytes:
        """Return PNG/JPEG bytes."""


class VisionLLM(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def analyze(self, images: list[bytes], prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> dict:
        """Return parsed JSON (dict)."""


class TextLLM(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> str | dict:
        """Return text, or a dict when a schema is given."""
