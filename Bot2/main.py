import sys
import io
import asyncio
import random

# Force UTF-8 so logs print cleanly on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import CHAT_SITES, ANTHROPIC_API_KEY
from bot import BotManager
from utils import log

# Bot 2 runs ALL sites (full coverage), same as Bot 1. The startup stagger below
# keeps the two bots offset in time to reduce the chance they match each other.
MY_SITES = CHAT_SITES

STARTUP_DELAY_SECONDS = 20


def preflight_check() -> bool:
    ok = True
    if ANTHROPIC_API_KEY == "your-api-key-here" or not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set in config.py")
        ok = False
    if not MY_SITES:
        print("ERROR: no sites assigned to Bot 2 (check BOT2_SITES in main.py)")
        ok = False
    return ok


async def main() -> None:
    log("bot2", "AI Chat Bot 2 starting")
    if not preflight_check():
        sys.exit(1)
    # Stagger start (plus a little jitter) so Bot 2 is offset from Bot 1
    delay = STARTUP_DELAY_SECONDS + random.uniform(0, 6)
    log("bot2", f"Waiting {delay:.0f}s to stagger from Bot 1...")
    await asyncio.sleep(delay)
    log("bot2", f"Bot 2 sites: {[s['name'] for s in MY_SITES]}")
    manager = BotManager(site_configs=MY_SITES)
    try:
        await manager.run()
    except KeyboardInterrupt:
        log("bot2", "Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
