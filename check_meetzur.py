import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        page = await browser.new_page()
        await page.goto("https://www.meetzur.com/chat", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        btn = await page.query_selector(".myButton")
        if btn:
            await btn.click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(4)

        # Find the servsig chat frame
        chat_frame = None
        for f in page.frames:
            if "servsig.com" in f.url:
                chat_frame = f
                print(f"Chat frame URL: {f.url}")
                break

        if not chat_frame:
            print("servsig frame not found")
            await browser.close()
            return

        await asyncio.sleep(2)

        print("\n--- INPUTS ---")
        for tag in ["textarea", "input[type='text']", "input", "[contenteditable='true']"]:
            els = await chat_frame.query_selector_all(tag)
            for el in els:
                try:
                    vis = await el.is_visible()
                    cls = await el.get_attribute("class") or ""
                    id_ = await el.get_attribute("id") or ""
                    ph  = await el.get_attribute("placeholder") or ""
                    t   = await el.evaluate("e => e.tagName.toLowerCase()")
                    print(f"  tag={t} visible={vis} id={id_!r} class={cls!r} ph={ph!r}")
                except Exception as e:
                    print(f"  error: {e}")

        print("\n--- MESSAGE CONTAINERS ---")
        for sel in ["[class*='msg']", "[class*='message']", "[class*='chat']",
                    "[id*='msg']", "[id*='message']", "[id*='chat']",
                    "[class*='log']", "[id*='log']", "[class*='history']",
                    "[class*='line']", "[class*='row']", "p", "li"]:
            els = await chat_frame.query_selector_all(sel)
            if els:
                s   = els[0]
                cls = await s.get_attribute("class") or ""
                id_ = await s.get_attribute("id") or ""
                t   = await s.evaluate("e => e.tagName.toLowerCase()")
                txt = (await s.inner_text()).strip()[:80]
                print(f"  sel={sel!r} count={len(els)} tag={t} id={id_!r} class={cls!r}")
                print(f"    text={txt!r}")

        print("\n--- ALL VISIBLE BUTTONS ---")
        els = await chat_frame.query_selector_all("button, input[type='submit'], input[type='button']")
        for el in els:
            try:
                vis = await el.is_visible()
                if not vis:
                    continue
                txt = (await el.inner_text()).strip()[:40]
                val = await el.get_attribute("value") or ""
                cls = await el.get_attribute("class") or ""
                id_ = await el.get_attribute("id") or ""
                print(f"  text={txt!r} val={val!r} id={id_!r} class={cls!r}")
            except Exception:
                pass

        await browser.close()

asyncio.run(main())
