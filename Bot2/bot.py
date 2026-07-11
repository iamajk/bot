import asyncio
import os
import random
from playwright.async_api import async_playwright, Page, Browser

from config import POLL_INTERVAL, PERSONALITIES, GIRL_NAMES

_FATAL_ERROR_MARKERS = (
    "Connection closed while reading from the driver",
    "browser has been closed",
    "Target page, context or browser has been closed",
    "Target closed",
    "has been closed",
)


def _is_fatal_connection_error(e: Exception) -> bool:
    """True if the browser/Playwright driver itself has died — retrying is useless
    until the whole session restarts."""
    msg = str(e)
    return any(marker in msg for marker in _FATAL_ERROR_MARKERS)


async def _human_mouse_move(page: Page) -> None:
    """Move the mouse through a few random waypoints before acting, instead of
    teleporting straight to a click target — cheap heuristic against bot checks."""
    try:
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        w, h = viewport["width"], viewport["height"]
        steps = random.randint(2, 4)
        for _ in range(steps):
            x = random.randint(50, max(51, w - 50))
            y = random.randint(50, max(51, h - 50))
            await page.mouse.move(x, y, steps=random.randint(8, 20))
            await asyncio.sleep(random.uniform(0.05, 0.2))
    except Exception:
        pass


def _find_chrome() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Chromium\Application\chromium.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None  # fall back to Playwright's bundled Chromium
from ai import generate_reply, quick_reply
from utils import (
    log, human_delay, typing_delay,
    is_worth_replying, should_drop_short_reply,
    pick_short_reply, should_mention_platform,
)


class ChatBot:
    def __init__(self, site_config: dict, personality_key: str = "chill"):
        self.site = site_config
        self.name = site_config.get("name", "bot")
        self.personality_key = personality_key
        self.history: list[dict] = []
        self.seen_messages: set[str] = set()
        self.promo_done = False
        self._ctx = None  # active page or frame
        self._chat_start_time: float = 0
        self._skip_after: float = 5
        self._reply_count: int = 0
        self._stuck_count: int = 0
        self._skip_total: int = 0
        self._page = None
        self._recover_fail_count: int = 0
        # Pick a fresh girl name per bot instance (changes on every 15-min restart)
        self._girl_name: str = random.choice(GIRL_NAMES)
        self.had_saved_session: bool = False
        log(self.name, f"Created — personality: {personality_key}")

    # ── SETUP ──────────────────────────────────────────────────────────────

    async def _setup_page(self, page: Page) -> None:
        log(self.name, f"Loading {self.site['url']}")
        loaded = False
        for attempt in range(2):
            try:
                await page.goto(self.site["url"], wait_until="domcontentloaded", timeout=60000)
                loaded = True
                break
            except Exception as e:
                log(self.name, f"Page load slow/failed (try {attempt+1}): {e}")
                await asyncio.sleep(2)
        if not loaded:
            # Proceed anyway — the page may be partially usable; setup/recovery will retry
            log(self.name, "Continuing despite slow load")

        await asyncio.sleep(3)

        # Site-specific setup
        name = self.name
        if name == "Meetzur":
            await self._setup_meetzur(page)
        elif name.startswith("OpenTalk"):
            await self._setup_opentalk(page)
        elif name == "TalkWithStranger":
            await self._setup_talkwithstranger(page)
        elif name == "OnlineStranger":
            await self._setup_onlinestranger(page)
        elif name == "Viby":
            await self._setup_viby(page)
        elif name == "SillyChat":
            await self._setup_silly(page)
        elif name == "IncogChats":
            await self._setup_incog(page)
        elif name == "RandomStranger":
            await self._setup_rsc(page)
        elif name == "OmeGG":
            await self._setup_ome(page)
        elif name == "StrangerLine":
            await self._setup_strangerline(page)
        elif name == "KnotChat":
            await self._setup_knotchat(page)
        elif name == "RandomChatTWS":
            await self._setup_randomchattws(page)
        else:
            self._ctx = page

    async def _setup_randomchattws(self, page: Page) -> None:
        """RandomChat.talkwithstranger.com: dismiss the online-count popup,
        click '1-1 Chat' to enter. Also handles a Cloudflare Turnstile checkbox
        if one appears, using Playwright's cross-origin frame access."""
        self._ctx = page
        try:
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await _human_mouse_move(page)

            # Dismiss the "X people online right now" popup if present
            try:
                await page.evaluate("""() => {
                    const btns = [...document.querySelectorAll('button,[role=button],svg,span')]
                        .filter(el => el.offsetParent !== null);
                    const close = btns.find(el => ['×','✕','✖','x'].includes((el.textContent||'').trim()));
                    if (close) close.click();
                }""")
            except Exception:
                pass
            await asyncio.sleep(0.5)

            # Solve a Cloudflare Turnstile checkbox if one shows up
            for frame in page.frames:
                if "challenges.cloudflare.com" in frame.url or "turnstile" in frame.url.lower():
                    try:
                        checkbox = await frame.wait_for_selector(
                            "input[type=checkbox], .cb-i, #cb", timeout=4000
                        )
                        if checkbox:
                            box = await checkbox.bounding_box()
                            if box:
                                await page.mouse.move(
                                    box["x"] + box["width"] / 2 + random.uniform(-3, 3),
                                    box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                                    steps=random.randint(10, 18),
                                )
                                await asyncio.sleep(random.uniform(0.3, 0.7))
                            await checkbox.click(timeout=5000)
                            log(self.name, "Clicked Turnstile checkbox")
                            await asyncio.sleep(random.uniform(2, 4))
                    except Exception:
                        pass
                    break

            # Click "1-1 Chat" to actually enter the chat
            await _human_mouse_move(page)
            await self._randomchattws_enter(page)

            log(self.name, "RandomChatTWS setup done — waiting for stranger")
        except Exception as e:
            log(self.name, f"RandomChatTWS setup error: {e}")
        await asyncio.sleep(random.uniform(4, 6))
        self._skip_after = random.uniform(10, 14)
        self._reply_count = 0
        self._chat_start_time = 0

    async def _randomchattws_close_popup(self, page: Page) -> None:
        """Close the '<N> people online right now' banner (it overlaps controls)."""
        try:
            await page.evaluate("""() => {
                const nodes = [...document.querySelectorAll('*')].filter(el => el.offsetParent !== null);
                const banner = nodes.find(el =>
                    /people online right now/i.test(el.textContent || '') && el.children.length < 12);
                if (banner) {
                    const scope = banner.closest('div') || banner;
                    const x = [...scope.querySelectorAll('button,svg,span,[aria-label*=close i]')]
                        .find(c => ['×','✕','✖','x'].includes((c.textContent||'').trim())
                                   || (c.getAttribute && (c.getAttribute('aria-label')||'').toLowerCase().includes('close')));
                    if (x) x.click();
                }
                // Generic X fallback
                const gx = nodes.find(el => el.children.length === 0
                    && ['×','✕','✖'].includes((el.textContent||'').trim()));
                if (gx) gx.click();
            }""")
        except Exception:
            pass

    async def _randomchattws_enter(self, page: Page) -> bool:
        """If sitting on the landing page, close the popup and click '1-1 Chat'.
        Uses a native Playwright click first (waits for actionability), then a
        JS mouse-event dispatch as backup."""
        if not page:
            return False
        try:
            await self._randomchattws_close_popup(page)
            await asyncio.sleep(0.3)
            # 1) Native click — most reliable, waits for the button to be ready.
            try:
                loc = page.get_by_text("1-1 Chat", exact=True).last
                if await loc.count() > 0:
                    await loc.click(timeout=4000, force=True)
                    log(self.name, "Clicked 1-1 Chat")
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    return True
            except Exception:
                pass
            # 2) JS dispatch fallback
            clicked = await page.evaluate("""() => {
                const el = [...document.querySelectorAll('button,a,[role=button],div,span')]
                    .find(x => /^1-1 chat$/i.test((x.textContent||'').trim()) && x.offsetParent !== null);
                if (el) {
                    const t = el.closest('button,a,[role=button]') || el;
                    ['mousedown','mouseup','click'].forEach(e =>
                        t.dispatchEvent(new MouseEvent(e, {bubbles:true, cancelable:true})));
                    return true;
                }
                return false;
            }""")
            if clicked:
                log(self.name, "Clicked 1-1 Chat (js)")
                await asyncio.sleep(random.uniform(1.0, 2.0))
            return clicked
        except Exception:
            return False

    async def _setup_knotchat(self, page: Page) -> None:
        """KnotChat: Text tab → Start Chatting → Female + 18-23 → START CHATTING
        → Sign In Anonymously. Uses natural mouse movement + human-like delays
        to reduce the chance of tripping the Cloudflare check."""
        self._ctx = page
        try:
            await _human_mouse_move(page)
            try:
                await page.click("text=Text", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(random.uniform(0.8, 1.6))
            await _human_mouse_move(page)
            await page.click("text=Start Chatting", timeout=8000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            await _human_mouse_move(page)
            await page.click("text=FEMALE", timeout=5000)
            await asyncio.sleep(random.uniform(0.4, 0.9))
            await page.click("text=18", timeout=5000)
            await asyncio.sleep(random.uniform(0.6, 1.0))

            # Click the modal's "START CHATTING" — try native click (waits for the
            # button to be actionable) then JS-dispatch a real click as backup.
            await _human_mouse_move(page)
            for _ in range(5):
                done = False
                try:
                    btn = page.locator("button:has-text('START CHATTING')").last
                    if await btn.count() > 0:
                        await btn.click(timeout=3000, force=True)
                        done = True
                except Exception:
                    pass
                if not done:
                    try:
                        done = await page.evaluate("""() => {
                            const b = [...document.querySelectorAll('button')]
                                .filter(x => /start chatting/i.test((x.textContent||'').trim())
                                             && x.offsetParent !== null).pop();
                            if (b) {
                                ['mousedown','mouseup','click'].forEach(t =>
                                    b.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true})));
                                return true;
                            }
                            return false;
                        }""")
                    except Exception:
                        pass
                # Did the modal go away? Then we're through.
                try:
                    still = await page.query_selector("text=Welcome to")
                    if not still:
                        break
                except Exception:
                    break
                await asyncio.sleep(0.9)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            # Sign-in gate — this is the step that hit Cloudflare last time
            await _human_mouse_move(page)
            try:
                await page.click("text=Sign In Anonymously", timeout=6000)
                await asyncio.sleep(random.uniform(1.0, 2.0))
            except Exception:
                pass

            log(self.name, "KnotChat setup done — waiting for stranger")
        except Exception as e:
            log(self.name, f"KnotChat setup error: {e}")
        await asyncio.sleep(4)
        # No confirmed in-chat "skip/leave" button for this flow — rely on the
        # partner leaving naturally + auto-reconnect (via "Restart") instead of
        # force-skipping, which would just re-blast messages to the same person.
        self._skip_after = 10 ** 9
        self._reply_count = 0
        self._chat_start_time = 0

    async def _setup_meetzur(self, page: Page) -> None:
        """Handle Meetzur: agree button → iframe → JS checkbox → enter chat → start."""
        # 1. Click "I Agree, Chat Now"
        try:
            btn = await page.wait_for_selector(".myButton", timeout=8000)
            await btn.click()
            log(self.name, "Clicked .myButton")
            await asyncio.sleep(3)
        except Exception as e:
            log(self.name, f".myButton not found: {e}")

        # 2. Switch into iframe
        try:
            frame_el = await page.wait_for_selector("iframe#chat_frame", timeout=15000)
            frame = await frame_el.content_frame()
            if not frame:
                log(self.name, "Could not get iframe content frame")
                self._ctx = page
                return
            self._ctx = frame
            log(self.name, "Switched into iframe")
        except Exception as e:
            log(self.name, f"iframe not found: {e}")
            self._ctx = page
            return

        await asyncio.sleep(3)

        # 3. Use JavaScript to check the checkbox and click Enter Chat
        try:
            await self._ctx.evaluate("""
                () => {
                    const cb = document.getElementById('agreeCheckbox');
                    if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change')); }
                    const btn = document.getElementById('enterBtn');
                    if (btn) { btn.removeAttribute('disabled'); btn.click(); }
                }
            """)
            log(self.name, "JS: checked agreeCheckbox and clicked enterBtn")
            await asyncio.sleep(3)
        except Exception as e:
            log(self.name, f"JS enter failed: {e}")

        # 4. Meetzur auto-connects — just trigger opener
        self._chat_start_time = 0
        self._skip_after = 5
        self._reply_count = 0

    async def _setup_opentalk(self, page: Page) -> None:
        """OpenTalk: 18+ terms gate (checkbox + Continue) → click start."""
        self._ctx = page
        await self._accept_opentalk_gate()
        # Click Start button
        await self._click_start()
        await asyncio.sleep(2)
        # Skip gender onboarding by clicking first button
        try:
            btn = await page.query_selector(".ot-onb-action")
            if btn and await btn.is_visible():
                await btn.click()
                log(self.name, "Clicked onboarding gender button")
                await asyncio.sleep(2)
        except Exception:
            pass

    async def _accept_opentalk_gate(self) -> None:
        """OpenTalk sometimes shows a 'Before you continue' 18+ checkbox gate."""
        page = self._ctx
        if not page:
            return
        try:
            checked = await page.evaluate("""() => {
                const cb = [...document.querySelectorAll('input[type=checkbox]')]
                    .find(x => x.offsetParent !== null && !x.checked);
                if (!cb) return false;
                cb.click();
                cb.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            }""")
            if checked:
                await asyncio.sleep(0.5)
                await page.evaluate("""() => {
                    const b = [...document.querySelectorAll('button')]
                        .find(x => x.textContent.trim() === 'Continue' && !x.disabled);
                    if (b) b.click();
                }""")
                log(self.name, "Accepted 18+ terms gate")
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _setup_ome(self, page: Page) -> None:
        """Ome.gg: cookie consent → gender + 18+ boxes → Text mode → Start Text Chat."""
        self._ctx = page
        try:
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Got it'); if(b)b.click();}""")
            await asyncio.sleep(1)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Female'); if(b)b.click();}""")
            await asyncio.sleep(0.5)
            for cb in await page.query_selector_all("input[type=checkbox]"):
                try:
                    await cb.check(timeout=2000)
                except Exception:
                    pass
            await asyncio.sleep(0.5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes("Let's Go")); if(b)b.click();}""")
            await asyncio.sleep(5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Text'); if(b)b.click();}""")
            await asyncio.sleep(0.5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Start Text Chat')); if(b)b.click();}""")
            log(self.name, "Ome setup done — starting chat")
        except Exception as e:
            log(self.name, f"Ome setup error: {e}")
        await asyncio.sleep(4)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # opener waits for connection

    async def _setup_rsc(self, page: Page) -> None:
        """RandomStrangerChats: cookie consent → nickname → START THE CHAT."""
        self._ctx = page
        try:
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()==='I agree'); if(b)b.click();}""")
            await asyncio.sleep(1)
            nick = await page.query_selector("input[placeholder*='call you']")
            if nick and await nick.is_visible():
                await nick.click()
                await nick.fill(self._girl_name + str(random.randint(10, 99)))
            await asyncio.sleep(0.5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button,a')].find(x=>/start the chat/i.test(x.textContent.trim())); if(b)b.click();}""")
            log(self.name, "RSC setup done — starting chat")
        except Exception as e:
            log(self.name, f"RSC setup error: {e}")
        await asyncio.sleep(4)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # opener waits for connection

    async def _setup_incog(self, page: Page) -> None:
        """IncogChats: Guest → gender → Start → I Agree → nickname → Start chatting."""
        self._ctx = page
        try:
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue as Guest'); if(b)b.click();}""")
            await asyncio.sleep(5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Female'); if(b)b.click();}""")
            await asyncio.sleep(0.5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Start Chatting'); if(b)b.click();}""")
            await asyncio.sleep(3)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('I Agree')); if(b)b.click();}""")
            await asyncio.sleep(3)
            nick = await page.query_selector("input[type=text]")
            if nick and await nick.is_visible():
                await nick.click()
                await nick.fill(self._girl_name + str(random.randint(10, 99)))
            await asyncio.sleep(0.5)
            await page.evaluate("""() => {const b=[...document.querySelectorAll('button')].find(x=>/start chatting/i.test(x.textContent.trim())); if(b)b.click();}""")
            await asyncio.sleep(2)
            await self._incog_click_start_new_chat()
            log(self.name, "Incog setup done — starting chat")
        except Exception as e:
            log(self.name, f"Incog setup error: {e}")
        await asyncio.sleep(4)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # opener waits for connection

    async def _incog_click_start_new_chat(self) -> None:
        """IncogChats sometimes lands on an idle screen with a 'Start New Chat'
        button that must be clicked to begin searching for a stranger."""
        page = self._ctx
        if not page:
            return
        try:
            clicked = await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')]
                    .find(x => /start new chat/i.test(x.textContent.trim()) && x.offsetParent !== null);
                if (b) { b.click(); return true; }
                return false;
            }""")
            if clicked:
                log(self.name, "Clicked Start New Chat")
                await asyncio.sleep(2)
        except Exception:
            pass

    async def _setup_silly(self, page: Page) -> None:
        """SillyChat: accept terms ('I Agree'), then it auto-connects."""
        self._ctx = page
        try:
            await page.evaluate("""() => {
                const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='I Agree');
                if(b) b.click();
            }""")
            log(self.name, "Clicked I Agree")
        except Exception as e:
            log(self.name, f"I Agree not found: {e}")
        await asyncio.sleep(3)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # opener waits for connection

    async def _setup_viby(self, page: Page) -> None:
        """Viby: landing → modal (Female + age) → chat. Robust to any entry state."""
        self._ctx = page
        self._skip_after = 8
        self._reply_count = 0
        if not self.had_saved_session:
            log(self.name, "=" * 60)
            log(self.name, "NO SAVED LOGIN FOUND — please sign in on the Viby tab now.")
            log(self.name, "Login: 1@gmail.com / 123456  (or register a new account)")
            log(self.name, "You have 45 seconds.")
            log(self.name, "Once signed in, the bot saves this login automatically")
            log(self.name, "and you won't need to do this again on future restarts.")
            log(self.name, "=" * 60)
            await asyncio.sleep(45)
        ok = await self._viby_enter()
        # Always reset the timer — opener's _wait_connected handles the rest.
        # (If we skip this on failure, the stale timer triggers an instant reload loop.)
        self._chat_start_time = 0
        if not ok:
            log(self.name, "Viby entry not confirmed — opener will wait for connection")

    async def _viby_homepage_fallback(self) -> None:
        """After End Chat, Viby sometimes drops back to the full homepage instead
        of the 'Partner left' screen. Detect that and re-enter via Start Chat."""
        page = self._ctx
        if not page:
            return
        try:
            inp = await page.query_selector("input.input-field[type=text]")
            if inp and await inp.is_visible():
                return  # already in an active chat, nothing to do
            sc = await page.query_selector("text=Start Chat")
            if sc and await sc.is_visible():
                log(self.name, "Landed on homepage — re-entering chat")
                ok = await self._viby_enter()
                if ok:
                    self.seen_messages.clear()
                    self.history.clear()
                    self.promo_done = False
                    self._reply_count = 0
                    self._chat_start_time = 0
                    await asyncio.sleep(1)
        except Exception:
            pass

    async def _viby_enter(self) -> bool:
        """Get into a live Viby chat from landing/modal/ended state."""
        page = self._ctx
        # already in chat?
        try:
            inp = await page.query_selector("input.input-field[type=text]")
            if inp and await inp.is_visible():
                return True
        except Exception:
            pass
        for _ in range(3):
            # ensure the age modal is open
            num = await page.query_selector("input[type=number]")
            if not (num and await num.is_visible()):
                try:
                    sc = await page.query_selector("text=Start Chat")
                    if sc and await sc.is_visible():
                        await sc.click(timeout=4000)
                except Exception:
                    pass
                try:
                    num = await page.wait_for_selector("input[type=number]", timeout=5000)
                except Exception:
                    num = None
            if num and await num.is_visible():
                # select Female (modal buttons take JS clicks)
                await page.evaluate("""() => {
                    const b=[...document.querySelectorAll('button')].find(x=>x.className.includes('border-2')&&x.textContent.trim()==='Female');
                    if(b) b.click();
                }""")
                try:
                    await num.click(timeout=4000)
                    await num.fill(random.choice(["20", "21", "22", "23", "24"]))
                except Exception:
                    pass
                await asyncio.sleep(0.4)
                await page.evaluate("""() => {
                    const b=document.querySelector('button.btn-primary.w-full');
                    if(b) b.click();
                }""")
                try:
                    await page.wait_for_selector("input.input-field[type=text]", timeout=12000)
                    return True
                except Exception:
                    pass
            await asyncio.sleep(1)
        return False

    async def _setup_onlinestranger(self, page: Page) -> None:
        """OnlineStranger: accept terms gate, then auto-connects."""
        self._ctx = page
        try:
            cb = await page.wait_for_selector("#terms", timeout=10000)
            if cb:
                await cb.check()
                log(self.name, "Checked terms")
        except Exception as e:
            log(self.name, f"terms checkbox not found: {e}")
        try:
            cont = await page.wait_for_selector("text=Continue", timeout=5000)
            if cont:
                await cont.click()
                log(self.name, "Clicked Continue")
        except Exception as e:
            log(self.name, f"Continue not found: {e}")
        await asyncio.sleep(4)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # triggers opener (waits for connect first)

    async def _setup_talkwithstranger(self, page: Page) -> None:
        """TalkWithStranger: click '1-1 Chat' to enter, then blast openers."""
        self._ctx = page
        setup_sel = self.site.get("setup_click")
        try:
            btn = await page.wait_for_selector(setup_sel, timeout=15000)
            if btn:
                await btn.click()
                log(self.name, "Clicked 1-1 Chat")
        except Exception as e:
            log(self.name, f"1-1 Chat button not found: {e}")
        # Wait for chat UI / stranger, then trigger opener
        await asyncio.sleep(5)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # triggers opener on next loop

    async def _setup_strangerline(self, page: Page) -> None:
        """StrangerLine: click Start New Chat button."""
        self._ctx = page
        await self._click_start()

    async def _click_onboard_if_needed(self) -> None:
        """Click gender/onboarding buttons if they appear (OpenTalk shows these mid-session)."""
        onboard_sel = self.site.get("onboard_click")
        if not onboard_sel or not self._ctx:
            return
        try:
            btn = await self._ctx.query_selector(onboard_sel)
            if btn and await btn.is_visible():
                await btn.click()
                log(self.name, "Clicked onboarding button")
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _click_start(self) -> None:
        """Click the start/new-chat button. Resets per-session state."""
        start_sel = self.site.get("start_selector")
        if not start_sel:
            return
        ctx = self._ctx
        try:
            btn = await ctx.wait_for_selector(start_sel, timeout=8000)
            if btn and await btn.is_visible():
                await btn.click()
                log(self.name, f"Clicked start: {start_sel}")
                self.seen_messages.clear()
                self.history.clear()
                self.promo_done = False
                await asyncio.sleep(2)
                self._skip_after = 5
                self._reply_count = 0
                self._chat_start_time = 0  # triggers opener on next loop
        except Exception as e:
            log(self.name, f"Start button not found ({start_sel}): {e}")

    async def _wait_connected(self, timeout: int = 25) -> bool:
        """Wait until a stranger is actually connected before sending."""
        target = self.site.get("connected_placeholder")
        connected_text = self.site.get("connected_text")
        input_ready = self.site.get("connected_when_input_ready")
        if not target and not connected_text and not input_ready:
            return True
        for _ in range(timeout):
            try:
                for sel in self.site["input_selector"].split(","):
                    el = await self._ctx.query_selector(sel.strip())
                    if not el or not await el.is_visible():
                        continue
                    if input_ready:
                        disabled = await el.get_attribute("disabled")
                        readonly = await el.get_attribute("readonly")
                        if disabled is None and readonly is None:
                            return True
                    if target:
                        p = await el.get_attribute("placeholder") or ""
                        if target.lower() in p.lower():
                            return True
                if connected_text:
                    body = (await self._ctx.inner_text("body")) or ""
                    body_lower = body.lower()
                    phrases = connected_text if isinstance(connected_text, (list, tuple)) else [connected_text]
                    if any(p.lower() in body_lower for p in phrases):
                        return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def _send_opener(self) -> None:
        """Send 3 messages then wait to skip — never waits for stranger reply."""
        # For sites like TalkWithStranger, wait until a stranger actually connects
        if not await self._wait_connected(timeout=15):
            log(self.name, "No stranger yet — restarting search")
            self._stuck_count += 1
            # Recover faster (popups/ads block connection — reload clears them)
            if self._stuck_count >= 2:
                await self._recover()
                return
            setup_sel = self.site.get("setup_click")
            if setup_sel:
                try:
                    b = await self._ctx.query_selector(setup_sel)
                    if b and await b.is_visible():
                        await b.click()
                except Exception:
                    pass
            await asyncio.sleep(2)
            return  # _chat_start_time stays 0 → retry next loop
        age = random.choice(["20", "21", "22", "23", "24", "25"])
        country = random.choice([
            "australia", "aus", "canada", "uk", "usa", "germany",
            "new zealand", "nz", "ireland", "sweden",
        ])
        intro = random.choice([
            f"hey f {age} {country} here",
            f"hi f {age} from {country}",
            f"f {age} {country} here",
            f"hey f {age} here from {country}",
        ])
        pitch = random.choice([
            "strangermeet.org - free, no login, has chat rooms & games too",
            "strangermeet.org - totally free, chat rooms + games, real people",
            "strangermeet.org - no signup, chat rooms and fun games, way better",
            "strangermeet.org - free site with chat rooms & games, best one out there",
            "strangermeet.org - join free, lots of chat rooms and games to play",
        ])
        sequence = [intro, pitch, "strangermeet.org"]
        # Some sites (e.g. IncogChats) silently filter messages containing a URL —
        # obfuscate the domain so it passes the filter but stays human-readable.
        obf = self.site.get("obfuscate_url")
        if obf:
            if isinstance(obf, (list, tuple)):
                # Use a DIFFERENT spelling for each URL message (pitch vs site-name)
                url_idxs = [i for i, m in enumerate(sequence) if "strangermeet.org" in m]
                forms = random.sample(list(obf), min(len(url_idxs), len(obf)))
                seq = list(sequence)
                for n, i in enumerate(url_idxs):
                    form = forms[n] if n < len(forms) else random.choice(obf)
                    seq[i] = sequence[i].replace("strangermeet.org", form)
                sequence = seq
            else:
                sequence = [m.replace("strangermeet.org", obf) for m in sequence]
        human_pace = self.site.get("human_pace")
        await asyncio.sleep(random.uniform(0.4, 0.8) if human_pace else 0.3)
        sent_ok = 0
        for msg in sequence:
            if await self._send(msg):
                sent_ok += 1
            await asyncio.sleep(random.uniform(0.6, 1.2) if human_pace else 0.3)
        if sent_ok == 0:
            # All sends failed — likely an ad popup is blocking the page
            self._stuck_count += 1
            if self._stuck_count >= 2:
                await self._recover()
                return
        else:
            self._stuck_count = 0
        self._reply_count = 0
        if sent_ok == len(sequence) and self.site.get("skip_immediately_after_send"):
            log(self.name, f"{sent_ok}/{len(sequence)} msgs sent — skipping now")
            await self._skip_chat()
            return
        log(self.name, f"{sent_ok}/{len(sequence)} msgs sent — waiting to skip")
        self._chat_start_time = asyncio.get_event_loop().time()

    # ── DISCONNECT DETECTION & AUTO-RECONNECT ──────────────────────────────

    async def _check_reconnect(self) -> None:
        """If a 'Start'/'New Chat' button is visible, click it to reconnect."""
        disc_sel = self.site.get("disconnect_selector")
        if not disc_sel or not self._ctx:
            return
        try:
            btn = await self._ctx.query_selector(disc_sel)
            if btn and await btn.is_visible():
                txt = (await btn.inner_text()).strip().lower()
                if any(k in txt for k in ["start", "new chat", "next", "reconnect"]):
                    log(self.name, "Disconnected — reconnecting...")
                    await asyncio.sleep(random.uniform(2, 5))
                    await btn.click()
                    self.seen_messages.clear()
                    self.history.clear()
                    self.promo_done = False
                    log(self.name, "Reconnected — new chat incoming")
                    self._chat_start_time = 0  # triggers opener on next loop
                    self._reply_count = 0
                    await asyncio.sleep(2)
        except Exception:
            pass

    # ── MESSAGE READING ────────────────────────────────────────────────────

    async def _get_new_message(self) -> str | None:
        selector = self.site["message_selector"]
        skip_kw = self.site.get("system_skip_keywords", [])
        ctx = self._ctx
        try:
            elements = await ctx.query_selector_all(selector)
            for el in reversed(elements):
                try:
                    text = (await el.inner_text()).strip()
                    if not text or text in self.seen_messages:
                        continue
                    tl = text.lower()
                    if any(k in tl for k in skip_kw):
                        self.seen_messages.add(text)
                        continue
                    if not is_worth_replying(text):
                        self.seen_messages.add(text)
                        continue
                    return text
                except Exception:
                    continue
        except Exception as e:
            log(self.name, f"Read error: {e}")
        return None

    # ── SENDING ────────────────────────────────────────────────────────────

    async def _send(self, text: str) -> bool:
        input_sel = self.site["input_selector"]
        send_sel  = self.site.get("send_selector")
        ctx = self._ctx
        box = None
        for sel in input_sel.split(","):
            try:
                b = await ctx.wait_for_selector(sel.strip(), timeout=3000)
                if b and await b.is_visible():
                    box = b
                    break
            except Exception:
                pass
        if not box:
            log(self.name, "Input box not found — skipping send")
            return False
        send_btn_text = self.site.get("send_button_text")
        human_pace = self.site.get("human_pace")
        try_all = self.site.get("send_try_all")
        try:
            await box.click(timeout=4000)
            await box.fill("")
            await box.type(text, delay=random.randint(12, 35) if human_pace else random.randint(3, 10))
            await asyncio.sleep(random.uniform(0.2, 0.6) if human_pace else 0.1)
            if try_all:
                # Try every known submit method. The input clears after a
                # successful send, so any extra attempts are harmless no-ops.
                first = input_sel.split(",")[0].strip()
                try:
                    await ctx.keyboard.press("Enter")
                except Exception:
                    pass
                await asyncio.sleep(0.15)
                try:
                    await ctx.evaluate("""(label) => {
                        const els = [...document.querySelectorAll('button,a,[role=button],input[type=submit],div,span')]
                            .filter(el => el.offsetParent !== null);
                        const hit = els.find(el => (el.textContent || el.value || '').trim().toUpperCase() === label);
                        if (hit) {
                            const target = hit.closest('button,a,[role=button]') || hit;
                            target.click();
                            if (target !== hit) { try { hit.click(); } catch(e) {} }
                        }
                    }""", (send_btn_text or "SEND").upper())
                except Exception:
                    pass
                await asyncio.sleep(0.15)
                try:
                    await ctx.evaluate("""(sel) => {
                        const inp = document.querySelector(sel);
                        if (!inp) return;
                        let row = inp.parentElement;
                        for (let i = 0; i < 5 && row; i++) {
                            const btns = [...row.querySelectorAll('button,[role=button],svg')]
                                .filter(el => el.offsetParent !== null);
                            if (btns.length) { btns[btns.length - 1].click(); return; }
                            row = row.parentElement;
                        }
                    }""", first)
                except Exception:
                    pass
            elif self.site.get("send_via_js"):
                # Click the last button in the input's row (the send icon button)
                await asyncio.sleep(0.2)
                await ctx.evaluate("""(sel) => {
                    const inp = document.querySelector(sel);
                    if (!inp) return;
                    let row = inp.closest('div');
                    while (row && row.querySelectorAll('button').length === 0) row = row.parentElement;
                    if (!row) return;
                    const btns = [...row.querySelectorAll('button')];
                    if (btns.length) btns[btns.length - 1].click();
                }""", input_sel.split(",")[0].strip())
            elif send_btn_text:
                try:
                    await ctx.keyboard.press("Enter")
                except Exception:
                    pass
                await asyncio.sleep(0.15)
                clicked = await ctx.evaluate("""(label) => {
                    const btns = [...document.querySelectorAll('button,a,[role=button],input[type=submit]')]
                        .filter(el => el.offsetParent !== null);
                    const b = btns.find(el => (el.textContent || el.value || '').trim().toUpperCase() === label.toUpperCase());
                    if (b) { b.click(); return true; }
                    return false;
                }""", send_btn_text)
                if not clicked:
                    try:
                        await ctx.click(f"text={send_btn_text}", timeout=2000)
                    except Exception:
                        pass
            elif send_sel:
                btn = await ctx.query_selector(send_sel)
                if btn:
                    await btn.click()
            else:
                await ctx.keyboard.press("Enter")
            log(self.name, f"Sent: {text}")
            return True
        except Exception as e:
            log(self.name, f"Send failed: {e}")
            return False

    # ── MAIN LOOP ──────────────────────────────────────────────────────────

    async def run(self, page: Page) -> None:
        self._page = page
        await self._setup_page(page)
        if not self._ctx:
            log(self.name, "Setup failed — bot stopped")
            return
        log(self.name, "Watching for messages...")
        while True:
            try:
                await self._dismiss_modals()
                await self._click_onboard_if_needed()
                await self._auto_reconnect_if_needed()
                if self.name == "Viby":
                    await self._viby_homepage_fallback()

                now = asyncio.get_event_loop().time()
                if self._chat_start_time == 0:
                    await self._send_opener()
                elif (now - self._chat_start_time) >= self._skip_after:
                    log(self.name, "Time up — skipping")
                    await self._skip_chat()
            except Exception as e:
                if _is_fatal_connection_error(e):
                    log(self.name, f"Browser/driver connection lost — stopping this tab: {e}")
                    return
                log(self.name, f"Loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    async def _dismiss_modals(self) -> None:
        """Close configured popups + common share/ad toasts that block the page."""
        if not self._ctx:
            return
        # Configured per-site dismiss buttons (e.g. "Maybe Later")
        for sel in self.site.get("dismiss_selectors") or []:
            try:
                btn = await self._ctx.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=3000)
                    log(self.name, f"Dismissed popup ({sel})")
            except Exception:
                pass
        # Generic "Invite friends / people online" share toast — close its X button
        if self.site.get("close_share_popups"):
            try:
                closed = await self._ctx.evaluate("""() => {
                    let n = 0;
                    document.querySelectorAll('*').forEach(el => {
                        const t = (el.textContent || '');
                        if ((t.includes('Invite friends') || t.includes('people online right now')) && el.children.length < 12) {
                            // find a close button within this toast and click it
                            el.querySelectorAll('button, [aria-label*="close" i], .close, svg').forEach(c => {
                                const ct = (c.textContent || '').trim();
                                const al = (c.getAttribute && (c.getAttribute('aria-label') || '')).toLowerCase();
                                if (ct === '×' || ct === '✕' || ct === '✖' || al.includes('close') || (c.className && String(c.className).toLowerCase().includes('close'))) {
                                    try { c.click(); n++; } catch(e) {}
                                }
                            });
                        }
                    });
                    return n;
                }""")
                if closed:
                    log(self.name, "Closed share popup")
            except Exception:
                pass

        # OpenTalk's 18+ terms gate can pop back up after a skip/reconnect
        if self.name.startswith("OpenTalk"):
            await self._accept_opentalk_gate()

        # IncogChats can land on an idle screen needing "Start New Chat" clicked
        if self.name == "IncogChats":
            await self._incog_click_start_new_chat()

        # RandomChatTWS: close the "people online" popup (it overlaps controls).
        # NOTE: the "Tap '1-1 Chat' to start" hint is a PERSISTENT UI label that
        # stays visible even mid-conversation — it is NOT a reliable "stuck"
        # signal, so we no longer re-click 1-1 Chat based on it (that was
        # interrupting active chats). Actual re-entry only happens in setup
        # (after a reload) where we know for certain we're on a fresh page.
        if self.name == "RandomChatTWS":
            await self._randomchattws_close_popup(self._ctx)

    async def _run_site_setup(self, page: Page) -> None:
        """Run the correct site-specific setup (used on first load and recovery)."""
        name = self.name
        if name == "Meetzur":
            await self._setup_meetzur(page)
        elif name.startswith("OpenTalk"):
            await self._setup_opentalk(page)
        elif name == "TalkWithStranger":
            await self._setup_talkwithstranger(page)
        elif name == "OnlineStranger":
            await self._setup_onlinestranger(page)
        elif name == "Viby":
            await self._setup_viby(page)
        elif name == "SillyChat":
            await self._setup_silly(page)
        elif name == "IncogChats":
            await self._setup_incog(page)
        elif name == "RandomStranger":
            await self._setup_rsc(page)
        elif name == "OmeGG":
            await self._setup_ome(page)
        elif name == "StrangerLine":
            await self._setup_strangerline(page)
        elif name == "KnotChat":
            await self._setup_knotchat(page)
        elif name == "RandomChatTWS":
            await self._setup_randomchattws(page)
        else:
            self._ctx = page

    async def _recover(self) -> None:
        """Reload the page to clear ad popups / stuck states, then re-run setup.
        Backs off with longer waits on repeated failures (e.g. a site temporarily
        rate-limiting/blocking rapid reloads) instead of hammering it immediately."""
        log(self.name, "Stuck — reloading page to recover")
        self._stuck_count = 0
        if not self._page:
            return
        if self._recover_fail_count > 0:
            backoff = min(5 * (2 ** self._recover_fail_count), 60)
            log(self.name, f"Backing off {backoff}s before retrying (site may be rate-limiting)")
            await asyncio.sleep(backoff)
        # Optionally wipe this site's cookies before reloading so each new
        # stranger sees a "fresh browser" (domain-scoped so other tabs are safe).
        clear_domain = self.site.get("clear_cookies_domain")
        if clear_domain and self._page:
            try:
                await self._page.context.clear_cookies(domain=clear_domain)
                log(self.name, f"Cleared cookies for {clear_domain}")
            except Exception:
                pass
        # Clear local/session storage too — some sites (e.g. TWS) "restore" the
        # last chat from storage on reload, which traps us with the same stranger.
        if self.site.get("clear_storage_on_reload") and self._page:
            try:
                await self._page.evaluate(
                    "() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e) {} }"
                )
            except Exception:
                pass
        try:
            await self._page.goto(self.site["url"], wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            await self._run_site_setup(self._page)
            log(self.name, "Recovered — resuming")
            self._recover_fail_count = 0
        except Exception as e:
            if _is_fatal_connection_error(e):
                raise
            self._recover_fail_count += 1
            log(self.name, f"Recover failed (attempt {self._recover_fail_count}): {e}")

    async def _auto_reconnect_if_needed(self) -> None:
        """If stranger disconnected and reconnect button is visible, click it."""
        reconnect_sel = self.site.get("reconnect_selector")
        if not reconnect_sel or not self._ctx:
            return
        try:
            btn = await self._ctx.query_selector(reconnect_sel)
            if btn and await btn.is_visible():
                await btn.click()
                log(self.name, "Stranger left — auto-reconnecting")
                self.seen_messages.clear()
                self.history.clear()
                self.promo_done = False
                self._reply_count = 0
                if not self.site.get("passive_skip_only"):
                    self._skip_after = 5
                await asyncio.sleep(1)
                self._chat_start_time = 0
        except Exception:
            pass

    async def _skip_chat(self) -> None:
        """Click Skip/Next to move to a new stranger."""
        skip_sel = self.site.get("disconnect_selector") or self.site.get("start_selector")
        reconnect_sel = self.site.get("reconnect_selector")
        confirm_sel = self.site.get("confirm_selector")
        if not self._ctx:
            return

        # Reload-based skip works even without a skip button — just reload the
        # page and re-run setup for a fresh stranger.
        if self.site.get("reload_on_skip"):
            self._skip_total += 1
            if skip_sel:
                # Robustly click the end-chat button (native force click + JS
                # dispatch), then confirm any "are you sure" dialog that appears.
                label = skip_sel.replace("text=", "").strip()
                clicked = False
                try:
                    loc = self._ctx.locator(f"text={label}").last
                    if await loc.count() > 0:
                        await loc.click(timeout=3000, force=True)
                        clicked = True
                except Exception:
                    pass
                if not clicked:
                    try:
                        await self._ctx.evaluate("""(txt) => {
                            const el = [...document.querySelectorAll('button,a,[role=button],div,span')]
                                .find(x => (x.textContent||'').trim().toLowerCase() === txt.toLowerCase()
                                           && x.offsetParent !== null);
                            if (el) {
                                const t = el.closest('button,a,[role=button]') || el;
                                ['mousedown','mouseup','click'].forEach(e =>
                                    t.dispatchEvent(new MouseEvent(e, {bubbles:true, cancelable:true})));
                            }
                        }""", label)
                    except Exception:
                        pass
                await asyncio.sleep(0.8)
                # Confirm a follow-up dialog (Yes / Confirm / Stop / End / OK)
                try:
                    await self._ctx.evaluate("""() => {
                        const words = ['yes','confirm','stop chat','stop','end chat','end','ok','sure'];
                        const els = [...document.querySelectorAll('button,a,[role=button]')]
                            .filter(x => x.offsetParent !== null);
                        const b = els.find(x => words.includes((x.textContent||'').trim().toLowerCase()));
                        if (b) b.click();
                    }""")
                except Exception:
                    pass
            wait = self.site.get("post_skip_wait", 0)
            if wait:
                log(self.name, f"Break {wait:.0f}s before next stranger")
                await asyncio.sleep(wait)
            await self._recover()  # reload + re-enter for a fresh stranger
            return

        if not skip_sel:
            return
        setup_sel = self.site.get("setup_click")

        # Every 10 skips, refresh the page to avoid blocks / memory build-up
        self._skip_total += 1
        if self._skip_total % 10 == 0:
            log(self.name, f"{self._skip_total} skips — refreshing page")
            await self._recover()
            return

        # JS-click the skip button (intercepted button / icon-only) — auto-reconnects
        js_skip_text = self.site.get("js_skip_text")
        js_skip_aria = self.site.get("js_skip_aria")
        js_skip_css = self.site.get("js_skip_css")
        if js_skip_text or js_skip_aria or js_skip_css:
            try:
                if js_skip_css:
                    await self._ctx.evaluate(
                        """(s) => {
                            const els=[...document.querySelectorAll(s)].filter(e=>e.offsetParent!==null);
                            const el=els[0];
                            if(el){ const target=el.closest('button,a,[role=button]')||el; target.click(); el.click(); }
                        }""",
                        js_skip_css,
                    )
                elif js_skip_aria:
                    await self._ctx.evaluate(
                        """(a) => {const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').includes(a)); if(b)b.click();}""",
                        js_skip_aria,
                    )
                else:
                    await self._ctx.evaluate(
                        """(txt) => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===txt); if(b)b.click();}""",
                        js_skip_text,
                    )
            except Exception:
                pass
            self.seen_messages.clear()
            self.history.clear()
            self.promo_done = False
            self._reply_count = 0
            wait = self.site.get("post_skip_wait", 1.5)
            log(self.name, f"Skipped (js) — waiting {wait:.0f}s before next chat")
            await asyncio.sleep(wait)
            self._chat_start_time = 0
            return

        # SillyChat: "Next" needs two RAPID clicks to actually disconnect
        if self.site.get("fast_skip"):
            try:
                btn = await self._ctx.query_selector(skip_sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=4000)
                    await asyncio.sleep(0.12)
                    await btn.click(timeout=4000)
            except Exception:
                pass
            log(self.name, "Skipped (fast double) — waiting for new stranger")
            self.seen_messages.clear()
            self.history.clear()
            self.promo_done = False
            self._reply_count = 0
            await asyncio.sleep(1.5)
            self._chat_start_time = 0
            return

        try:
            btn = await self._ctx.query_selector(skip_sel)
            if btn and await btn.is_visible():
                await btn.click(timeout=4000)
                await asyncio.sleep(0.8)

            # Step 2: confirmation dialog (e.g. "Sure?" / "Yes, End Chat")
            js_confirm_text = self.site.get("js_confirm_text")
            if js_confirm_text:
                try:
                    await asyncio.sleep(0.5)
                    await self._ctx.evaluate(
                        """(txt) => {
                            const els = [...document.querySelectorAll('button')]
                                .filter(x => x.textContent.trim() === txt && x.offsetParent !== null);
                            const last = els[els.length - 1];
                            if (last) last.click();
                        }""",
                        js_confirm_text,
                    )
                    await asyncio.sleep(1.0)
                except Exception:
                    pass
            elif confirm_sel:
                try:
                    c = await self._ctx.wait_for_selector(confirm_sel, timeout=3000)
                    if c and await c.is_visible():
                        await c.click(timeout=4000)
                        await asyncio.sleep(1.0)
                except Exception:
                    pass

            # Step 3: advance to a new stranger
            if reconnect_sel:
                # OnlineStranger / Meetzur: click "Find New Stranger" / "Start New Chat"
                try:
                    new_btn = await self._ctx.wait_for_selector(reconnect_sel, timeout=5000)
                    if new_btn and await new_btn.is_visible():
                        await new_btn.click(timeout=4000)
                except Exception:
                    pass
            elif setup_sel:
                # TalkWithStranger: re-click "1-1 Chat" to start a new search
                try:
                    b = await self._ctx.wait_for_selector(setup_sel, timeout=5000)
                    if b and await b.is_visible():
                        await b.click(timeout=4000)
                        log(self.name, "Re-clicked 1-1 Chat — searching")
                except Exception:
                    pass
            elif not confirm_sel and not self.site.get("single_skip"):
                # OpenTalk: second click on the same Skip button
                btn2 = await self._ctx.query_selector(skip_sel)
                if btn2 and await btn2.is_visible():
                    await btn2.click(timeout=4000)

            log(self.name, "Skipped — waiting for new stranger to connect")
            self.seen_messages.clear()
            self.history.clear()
            self.promo_done = False
            self._reply_count = 0
            self._skip_after = 5

            # _send_opener will wait for the actual connection before blasting
            await asyncio.sleep(2)
            self._chat_start_time = 0  # trigger opener
        except Exception as e:
            log(self.name, f"Skip error: {e}")
            self._stuck_count += 1
            if self._stuck_count >= 2:
                await self._recover()
                self._chat_start_time = 0

    async def _reply(self, message: str) -> None:
        # Max 2 replies after opener+pitch (total ~4 messages)
        if self._reply_count >= 2:
            return
        reply = quick_reply(message)
        if not reply:
            reply = pick_short_reply()
        await human_delay(0.5, 1.0)
        await self._send(reply)
        self._reply_count += 1


# ── MANAGER ────────────────────────────────────────────────────────────────

class BotManager:
    def __init__(self, site_configs: list[dict]):
        self.site_configs = site_configs

    # Restart the whole browser this often to clear caches/memory and stay fast
    RESTART_EVERY_SECONDS = 30 * 60

    async def run(self) -> None:
        # Outer loop: every RESTART_EVERY_SECONDS, tear everything down and start fresh.
        while True:
            await self._run_session()
            log("manager", "Session ended — restarting fresh in 3s to clear caches")
            await asyncio.sleep(3)

    STORAGE_STATE_PATH = os.path.join(os.path.dirname(__file__), "browser_session.json")

    async def _run_session(self) -> None:
        personality_keys = list(PERSONALITIES.keys())
        async with async_playwright() as pw:
            chrome_path = _find_chrome()
            launch_kwargs: dict = {
                "headless": False,
                "args": [
                    "--no-sandbox",
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
            }
            if chrome_path:
                launch_kwargs["executable_path"] = chrome_path
            browser: Browser = await asyncio.wait_for(
                pw.chromium.launch(**launch_kwargs), timeout=30
            )
            # One shared context so all sites open as TABS in a single window,
            # and no_viewport lets each tab fill the maximized window (input visible).
            # Reuse a saved login session (e.g. Viby) across restarts if present.
            context_kwargs: dict = {"no_viewport": True}
            if os.path.exists(self.STORAGE_STATE_PATH):
                context_kwargs["storage_state"] = self.STORAGE_STATE_PATH
            had_saved_session = "storage_state" in context_kwargs
            try:
                context = await browser.new_context(**context_kwargs)
            except Exception as e:
                log("manager", f"new_context with saved session failed ({e}) — starting fresh")
                had_saved_session = False
                context = await browser.new_context(no_viewport=True)
            tasks = []
            for i, site in enumerate(self.site_configs):
                personality = personality_keys[i % len(personality_keys)]
                page = await context.new_page()
                bot = ChatBot(site_config=site, personality_key=personality)
                bot.had_saved_session = had_saved_session
                tasks.append(asyncio.create_task(bot.run(page)))
                log("manager", f"Tab opened for '{site['name']}' [{personality}]")
                # Extra stagger for OpenTalk tabs so they don't start at the same
                # moment and end up paired with each other.
                extra_gap = 8 if site["name"].startswith("OpenTalk") else 1
                await asyncio.sleep(extra_gap)

            # Watchdog: if the browser dies unexpectedly (crash / manually closed),
            # detect it immediately instead of waiting for the full restart timer.
            disconnected_event = asyncio.Event()
            browser.on("disconnected", lambda: disconnected_event.set())

            async def _watch_disconnect():
                await disconnected_event.wait()
                log("manager", "Browser disconnected unexpectedly — restarting now")

            watchdog_task = asyncio.create_task(_watch_disconnect())
            gather_task = asyncio.gather(*tasks, return_exceptions=True)

            try:
                done, pending = await asyncio.wait(
                    [gather_task, watchdog_task],
                    timeout=self.RESTART_EVERY_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    log("manager", f"{self.RESTART_EVERY_SECONDS // 60} min up — restarting browser")
            except asyncio.CancelledError:
                pass
            finally:
                watchdog_task.cancel()
                gather_task.cancel()
                try:
                    await context.storage_state(path=self.STORAGE_STATE_PATH)
                    log("manager", "Saved login session for next restart")
                except Exception as e:
                    log("manager", f"Could not save session: {e}")
                for t in tasks:
                    t.cancel()
                try:
                    await asyncio.wait_for(browser.close(), timeout=15)
                except Exception:
                    pass
                log("manager", "Browser closed.")
