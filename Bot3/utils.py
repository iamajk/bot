import asyncio
import random
import re
from datetime import datetime

from config import (
    REPLY_DELAY_MIN,
    REPLY_DELAY_MAX,
    SHORT_REPLY_CHANCE,
    PROMO_TRIGGERS,
    MIN_MESSAGE_LENGTH,
)


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

def log(label: str, message: str) -> None:
    """Print a timestamped log line, safe for any terminal encoding."""
    ts = datetime.now().strftime("%H:%M:%S")
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(f"[{ts}] [{label}] {safe}", flush=True)


# ─────────────────────────────────────────────
# DELAYS
# ─────────────────────────────────────────────

async def human_delay(min_s: float = None, max_s: float = None) -> None:
    """Wait a random number of seconds to simulate a human typing pause."""
    lo = min_s if min_s is not None else REPLY_DELAY_MIN
    hi = max_s if max_s is not None else REPLY_DELAY_MAX
    wait = random.uniform(lo, hi)
    await asyncio.sleep(wait)


async def typing_delay(text: str) -> None:
    """Short delay to simulate typing speed."""
    await asyncio.sleep(random.uniform(0.3, 0.8))


# ─────────────────────────────────────────────
# MESSAGE FILTERING
# ─────────────────────────────────────────────

def is_worth_replying(message: str) -> bool:
    """Return True if the message is long enough and not just punctuation/noise."""
    cleaned = message.strip()
    if len(cleaned) < MIN_MESSAGE_LENGTH:
        return False
    # Ignore messages that are only symbols / numbers
    if re.fullmatch(r"[^a-zA-Z]+", cleaned):
        return False
    return True


def should_drop_short_reply() -> bool:
    """Randomly decide to send a casual short reply instead of an AI reply."""
    return random.randint(1, SHORT_REPLY_CHANCE) == 1


def pick_short_reply() -> str:
    """Return a random casual filler reply."""
    options = [
        "lol", "haha", "fr", "ngl same", "true", "yeah same",
        "lowkey yeah", "lmao", "omg", "bruh", "wait really?",
        "no way", "facts", "mood", "ikr",
    ]
    return random.choice(options)


# ─────────────────────────────────────────────
# PROMO DETECTION
# ─────────────────────────────────────────────

def should_mention_platform(message: str) -> bool:
    """Return True if the message contains a trigger keyword for a soft promo."""
    lower = message.lower()
    return any(trigger in lower for trigger in PROMO_TRIGGERS)


# ─────────────────────────────────────────────
# CONTEXT HELPERS
# ─────────────────────────────────────────────

def build_context_snippet(history: list[dict]) -> str:
    """Convert recent conversation history to a readable string for the AI prompt."""
    lines = []
    for turn in history:
        role = "Stranger" if turn["role"] == "user" else "You"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)
