"""
find_selectors.py — Opens each chat site and prints candidate CSS selectors
for message containers and input boxes.
Run once, read the output, then update config.py.
"""

import asyncio
from playwright.async_api import async_playwright

SITES = [
    {"name": "OpenTalk", "url": "https://opentalk.club/text/"},
    {"name": "StrangerLine", "url": "https://strangerline.io/chat/"},
    {"name": "Meetzur", "url": "https://www.meetzur.com/chat"},
]

# Tags/attributes we look for
INPUT_TAGS = ["textarea", "input[type='text']", "input:not([type])", "[contenteditable='true']"]
MSG_CANDIDATES = [
    "[class*='message']", "[class*='msg']", "[class*='chat']",
    "[class*='bubble']", "[class*='text']", "[id*='message']",
    "[id*='chat']", "[id*='msg']",
]

async def inspect_site(page, name, url):
    print(f"\n{'='*60}")
    print(f"  {name}  ->  {url}")
    print(f"{'='*60}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"  [!] Page load error: {e}")
        return

    await asyncio.sleep(3)  # let JS render

    # ── INPUT BOX ─────────────────────────────────────────────
    print("\n[ INPUT BOXES FOUND ]")
    for sel in INPUT_TAGS:
        els = await page.query_selector_all(sel)
        for el in els:
            vis = await el.is_visible()
            ph  = await el.get_attribute("placeholder") or ""
            cls = await el.get_attribute("class") or ""
            id_ = await el.get_attribute("id") or ""
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            print(f"  tag={tag}  visible={vis}  id={id_!r}  class={cls!r}  placeholder={ph!r}")
            print(f"    → suggested selector: ", end="")
            if id_:
                print(f"#{id_}")
            elif cls:
                first_cls = cls.strip().split()[0]
                print(f".{first_cls}")
            else:
                print(sel)

    # ── SEND BUTTON ───────────────────────────────────────────
    print("\n[ SEND BUTTONS FOUND ]")
    btn_sels = ["button[type='submit']", "button", "[class*='send']", "[id*='send']"]
    for sel in btn_sels:
        els = await page.query_selector_all(sel)
        for el in els:
            vis = await el.is_visible()
            if not vis:
                continue
            txt = (await el.inner_text()).strip()[:40]
            cls = await el.get_attribute("class") or ""
            id_ = await el.get_attribute("id") or ""
            if any(kw in txt.lower() or kw in cls.lower() or kw in id_.lower()
                   for kw in ["send", "submit", "chat", "go", "start", "➤", "►"]):
                print(f"  text={txt!r}  id={id_!r}  class={cls!r}")
                if id_:
                    print(f"    → suggested selector: #{id_}")
                elif cls:
                    first_cls = cls.strip().split()[0]
                    print(f"    → suggested selector: .{first_cls}")

    # ── MESSAGE CONTAINERS ────────────────────────────────────
    print("\n[ MESSAGE CONTAINERS FOUND ]")
    for sel in MSG_CANDIDATES:
        els = await page.query_selector_all(sel)
        if els:
            sample = els[0]
            cls = await sample.get_attribute("class") or ""
            id_ = await sample.get_attribute("id") or ""
            tag = await sample.evaluate("e => e.tagName.toLowerCase()")
            txt = (await sample.inner_text()).strip()[:60]
            print(f"  selector={sel!r}  count={len(els)}  tag={tag}  id={id_!r}  class={cls!r}")
            print(f"    sample text: {txt!r}")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
                headless=False,
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            )
        for site in SITES:
            page = await browser.new_page()
            await inspect_site(page, site["name"], site["url"])
            await page.close()
        await browser.close()
        print("\n\nDone. Use the selectors above to update config.py.")

asyncio.run(main())
