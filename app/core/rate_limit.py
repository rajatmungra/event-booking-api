import math
import time
from collections import defaultdict, deque

from app.core.exceptions import TooManyRequests


class RateLimiter:
    """Sliding window: at most `max_attempts` per key in the last `window_seconds`.

    Counts live in this process's memory, so they reset on restart and aren't shared between
    several API instances (that would need e.g. Redis).
    """

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        attempts = self.attempts[key]
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            retry_after = math.ceil(attempts[0] + self.window_seconds - now)
            raise TooManyRequests(
                details={"retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)
        # Forget keys with no recent attempts so memory doesn't grow forever.
        if len(self.attempts) > 10_000:
            for stale in [
                k for k, v in self.attempts.items() if v[-1] <= now - self.window_seconds
            ]:
                del self.attempts[stale]


login_limiter = RateLimiter(max_attempts=5, window_seconds=60)
