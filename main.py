import sys
import io
import asyncio

# Force UTF-8 so logs print cleanly on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import CHAT_SITES, ANTHROPIC_API_KEY
from bot import BotManager
from utils import log

# Bot 1 runs ALL sites (full coverage). NOTE: because Bot 2 also runs all sites,
# the two bots share matching pools and CAN occasionally be paired with each
# other — the startup stagger makes this rare but not impossible.
MY_SITES = CHAT_SITES


def preflight_check() -> bool:
    ok = True
    if ANTHROPIC_API_KEY == "your-api-key-here" or not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set in config.py")
        ok = False
    if not MY_SITES:
        print("ERROR: no sites assigned to Bot 1 (check BOT1_SITES in main.py)")
        ok = False
    return ok


async def main() -> None:
    log("main", "AI Chat Bot 1 starting")
    if not preflight_check():
        sys.exit(1)
    log("main", f"Bot 1 sites: {[s['name'] for s in MY_SITES]}")
    manager = BotManager(site_configs=MY_SITES)
    try:
        await manager.run()
    except KeyboardInterrupt:
        log("main", "Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
