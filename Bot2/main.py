import sys
import io
import os
import asyncio
import random

# Force UTF-8 so logs print cleanly on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Show the Viby login prompt FIRST, at the very top of the terminal, before
# anything else starts logging and pushes it down/off screen.
_SESSION_FILE = os.path.join(os.path.dirname(__file__), "browser_session.json")
if not os.path.exists(_SESSION_FILE):
    print("=" * 60)
    print("VIBY LOGIN REQUIRED ON FIRST RUN")
    print("Sign in on the Viby tab once it opens:")
    print("  Login: 1@gmail.com / 123456  (or register a new account)")
    print("This will be saved automatically for all future restarts.")
    print("=" * 60)

from config import CHAT_SITES, ANTHROPIC_API_KEY
from bot import BotManager
from utils import log

# Bot 2 runs a different set of sites than Bot 1, so no stagger is needed —
# they can never end up paired with each other.
MY_SITES = CHAT_SITES


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
