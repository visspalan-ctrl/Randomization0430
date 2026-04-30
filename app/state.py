from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import random
from typing import Dict, List, Optional, Tuple


DEFAULT_BLOCK_SIZES = (4, 8, 12)
LOCK_THRESHOLD = 5
LOCK_WINDOW_MINUTES = 10


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class FailedAttemptWindow:
    attempts: List[datetime] = field(default_factory=list)
    locked_until: Optional[datetime] = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def register_failure(self, now: datetime) -> None:
        window_start = now - timedelta(minutes=LOCK_WINDOW_MINUTES)
        self.attempts = [t for t in self.attempts if t >= window_start]
        self.attempts.append(now)
        if len(self.attempts) >= LOCK_THRESHOLD:
            self.locked_until = now + timedelta(minutes=LOCK_WINDOW_MINUTES)

    def clear(self) -> None:
        self.attempts = []
        self.locked_until = None


class BlockRandomizer:
    def __init__(self) -> None:
        self.block_sizes: Tuple[int, ...] = DEFAULT_BLOCK_SIZES
        self.current_block: List[str] = []
        self.assigned = {"GENAI": 0, "HUMAN": 0}

    def set_block_sizes(self, block_sizes: Tuple[int, ...]) -> None:
        self.block_sizes = block_sizes
        self.current_block = []

    def next_group(self) -> str:
        if not self.current_block:
            block_size = random.choice(self.block_sizes)
            half = block_size // 2
            block = ["GENAI"] * half + ["HUMAN"] * half
            random.shuffle(block)
            self.current_block = block
        group = self.current_block.pop(0)
        self.assigned[group] += 1
        return group


class AppState:
    def __init__(self) -> None:
        self.randomizer = BlockRandomizer()
        self.failed_attempts: Dict[Tuple[str, str], FailedAttemptWindow] = {}


app_state = AppState()
