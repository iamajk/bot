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

MY_SITES = CHAT_SITES

STARTUP_DELAY_SECONDS = 40


def preflight_check() -> bool:
    ok = True
    if not MY_SITES:
        print("ERROR: no sites assigned to Bot 3")
        ok = False
    return ok


async def main() -> None:
    log("bot3", "AI Chat Bot 3 starting")
    if not preflight_check():
        sys.exit(1)
    delay = STARTUP_DELAY_SECONDS + random.uniform(0, 6)
    log("bot3", f"Waiting {delay:.0f}s to stagger from other bots...")
    await asyncio.sleep(delay)
    log("bot3", f"Bot 3 sites: {[s['name'] for s in MY_SITES]}")
    manager = BotManager(site_configs=MY_SITES)
    try:
        await manager.run()
    except KeyboardInterrupt:
        log("bot3", "Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
