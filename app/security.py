"""Security helpers: prompt-injection screening, id pseudonymisation, upload sniffing, rate limiting."""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict, deque
from typing import Optional

_INJECTION = re.compile(
    r"(?:ignore|disregard|forget|override|bypass)\W+(?:all\W+|any\W+|the\W+|your\W+|previous\W+|prior\W+|above\W+)*"
    r"(?:instructions?|prompts?|rules?)"
    r"|system\s*prompt|you\s+are\s+now|act\s+as\b|reveal\s+(?:your|the)\s+(?:prompt|instructions|key)"
    r"|developer\s+mode|jailbreak|api[_\s-]?key|prompt\s*injection"
    r"|(?:dan|chatgpt|claude|gemini)\s*mode",
    re.IGNORECASE,
)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def pseudonymize(user_id: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:12]


def sniff_image(data: bytes) -> Optional[str]:
    """Trust the bytes, not the filename or the declared content type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class RateLimiter:
    """Sliding-window limiter, in memory. Use Cloud Armor or Redis if you run many instances."""

    def __init__(self, limit: int, window: float = 60.0, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            # Prevent unbounded growth by pruning expired keys when table reaches capacity
            if len(self.hits) >= self.max_keys:
                stale = [k for k, q in list(self.hits.items()) if not q or now - q[-1] > self.window]
                for k in stale:
                    del self.hits[k]

            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def clear(self) -> None:
        with self.lock:
            self.hits.clear()


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}
