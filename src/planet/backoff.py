"""When to try a failing feed again: exponential backoff, capped.

After the n-th consecutive failure a feed waits BASE * 2**(n-1), at most CAP:
1h, 2h, 4h, ... 64h, then every 72h until it works again. Any success resets
the count. With hourly runs, the first failure costs nothing extra: the feed
is simply tried on the next run.
"""

from __future__ import annotations

BASE_S = 3600.0
CAP_S = 72 * 3600.0
# Scheduled runs drift by seconds to minutes. A feed counts as due if its
# retry time falls within this window after the run starts; otherwise a 1h
# wait could miss the next hourly run by a second and skip it.
GRACE_S = 15 * 60.0


def delay_s(failures: int) -> float:
    """Wait after `failures` consecutive failures (failures >= 1)."""
    if failures < 1:
        raise ValueError(f"failures must be >= 1, got {failures}")
    # min() on the exponent keeps 2**n small for long-dead feeds.
    return min(BASE_S * 2 ** min(failures - 1, 32), CAP_S)


def is_due(retry_at: float | None, now: float) -> bool:
    """Whether a feed whose next attempt is `retry_at` should be fetched now."""
    return retry_at is None or retry_at <= now + GRACE_S
