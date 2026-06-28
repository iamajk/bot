import asyncio
import os
import random
from playwright.async_api import async_playwright, Page, Browser

from config import POLL_INTERVAL, PERSONALITIES, GIRL_NAMES


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
        # Pick a fresh girl name per bot instance (changes on every 15-min restart)
        self._girl_name: str = random.choice(GIRL_NAMES)
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
        elif name == "OpenTalk":
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
        elif name == "TalkWithStranger":
            await self._setup_tws(page)
        else:
            self._ctx = page

    async def _setup_tws(self, page: Page) -> None:
        """TalkWithStranger: wait for chat UI to load, dismiss any popups."""
        self._ctx = page
        try:
            for btn_text in ["I Agree", "Accept", "OK", "Got it", "Continue"]:
                try:
                    await page.click(f"text={btn_text}", timeout=3000)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
            log(self.name, "TalkWithStranger setup done — waiting for stranger")
        except Exception as e:
            log(self.name, f"TalkWithStranger setup error: {e}")
        await asyncio.sleep(4)
        self._skip_after = 8
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
        """OpenTalk: just use main page, click start."""
        self._ctx = page
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
            log(self.name, "Incog setup done — starting chat")
        except Exception as e:
            log(self.name, f"Incog setup error: {e}")
        await asyncio.sleep(4)
        self._skip_after = 5
        self._reply_count = 0
        self._chat_start_time = 0  # opener waits for connection

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
        ok = await self._viby_enter()
        # Always reset the timer — opener's _wait_connected handles the rest.
        # (If we skip this on failure, the stale timer triggers an instant reload loop.)
        self._chat_start_time = 0
        if not ok:
            log(self.name, "Viby entry not confirmed — opener will wait for connection")

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
        """For sites that show a placeholder when connected, wait until connected."""
        target = self.site.get("connected_placeholder")
        if not target:
            return True
        input_sel = self.site["input_selector"].split(",")[0].strip()
        for _ in range(timeout):
            try:
                el = await self._ctx.query_selector(input_sel)
                # Must be VISIBLE (some sites keep the input in the DOM but hidden
                # while searching — visibility is the real "connected" signal)
                if el and await el.is_visible():
                    p = await el.get_attribute("placeholder") or ""
                    if target.lower() in p.lower():
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
        await asyncio.sleep(0.3)
        sent_ok = 0
        for msg in sequence:
            if await self._send(msg):
                sent_ok += 1
            await asyncio.sleep(0.3)
        if sent_ok == 0:
            # All sends failed — likely an ad popup is blocking the page
            self._stuck_count += 1
            if self._stuck_count >= 2:
                await self._recover()
                return
        else:
            self._stuck_count = 0
        log(self.name, f"{sent_ok}/3 msgs sent — waiting to skip")
        self._chat_start_time = asyncio.get_event_loop().time()
        self._reply_count = 0

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
        try:
            await box.click(timeout=4000)
            await box.fill("")
            await box.type(text, delay=random.randint(3, 10))
            if self.site.get("send_via_js"):
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

                now = asyncio.get_event_loop().time()
                if self._chat_start_time == 0:
                    await self._send_opener()
                elif (now - self._chat_start_time) >= self._skip_after:
                    log(self.name, "Time up — skipping")
                    await self._skip_chat()
            except Exception as e:
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

    async def _run_site_setup(self, page: Page) -> None:
        """Run the correct site-specific setup (used on first load and recovery)."""
        name = self.name
        if name == "Meetzur":
            await self._setup_meetzur(page)
        elif name == "OpenTalk":
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
        else:
            self._ctx = page

    async def _recover(self) -> None:
        """Reload the page to clear ad popups / stuck states, then re-run setup."""
        log(self.name, "Stuck — reloading page to recover")
        self._stuck_count = 0
        if not self._page:
            return
        try:
            await self._page.goto(self.site["url"], wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            await self._run_site_setup(self._page)
            log(self.name, "Recovered — resuming")
        except Exception as e:
            log(self.name, f"Recover failed: {e}")

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
                self._skip_after = 5
                await asyncio.sleep(3)
                self._chat_start_time = 0
        except Exception:
            pass

    async def _skip_chat(self) -> None:
        """Click Skip/Next to move to a new stranger."""
        skip_sel = self.site.get("disconnect_selector") or self.site.get("start_selector")
        reconnect_sel = self.site.get("reconnect_selector")
        confirm_sel = self.site.get("confirm_selector")
        if not skip_sel or not self._ctx:
            return
        setup_sel = self.site.get("setup_click")

        # Every 10 skips, refresh the page to avoid blocks / memory build-up
        self._skip_total += 1
        if self._skip_total % 10 == 0:
            log(self.name, f"{self._skip_total} skips — refreshing page")
            await self._recover()
            return

        # Viby: modal won't reopen via "End Chat" — reload + re-enter each skip
        if self.site.get("reload_on_skip"):
            try:
                btn = await self._ctx.query_selector(skip_sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=4000)  # politely end the chat first
            except Exception:
                pass
            wait = self.site.get("post_skip_wait", 0)
            if wait:
                log(self.name, f"Break {wait:.0f}s before next stranger")
                await asyncio.sleep(wait)
            await self._recover()  # reload + re-enter for a fresh stranger
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
            if confirm_sel:
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

    async def _run_session(self) -> None:
        personality_keys = list(PERSONALITIES.keys())
        async with async_playwright() as pw:
            chrome_path = _find_chrome()
            launch_kwargs: dict = {
                "headless": False,
                "args": ["--no-sandbox", "--start-maximized"],
            }
            if chrome_path:
                launch_kwargs["executable_path"] = chrome_path
            browser: Browser = await pw.chromium.launch(**launch_kwargs)
            # One shared context so all sites open as TABS in a single window,
            # and no_viewport lets each tab fill the maximized window (input visible).
            context = await browser.new_context(no_viewport=True)
            tasks = []
            for i, site in enumerate(self.site_configs):
                personality = personality_keys[i % len(personality_keys)]
                page = await context.new_page()
                bot = ChatBot(site_config=site, personality_key=personality)
                tasks.append(asyncio.create_task(bot.run(page)))
                log("manager", f"Tab opened for '{site['name']}' [{personality}]")
                await asyncio.sleep(1)  # stagger tab launches slightly

            try:
                # Run the bots, but only for the restart window
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.RESTART_EVERY_SECONDS,
                )
            except asyncio.TimeoutError:
                log("manager", f"{self.RESTART_EVERY_SECONDS // 60} min up — restarting browser")
            except asyncio.CancelledError:
                pass
            finally:
                for t in tasks:
                    t.cancel()
                try:
                    await browser.close()
                except Exception:
                    pass
                log("manager", "Browser closed.")
