"""Script to capture mid-run and completion screenshots and verify dynamic footer updates."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENS_DIR = ROOT_DIR / "docs" / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # -------------------------------------------------------------
        # 1. Desktop Viewport (1440 x 900)
        # -------------------------------------------------------------
        context_desktop = await browser.new_context(viewport={"width": 1440, "height": 900})
        page_desktop = await context_desktop.new_page()

        print("[1/5] Navigating to production app at http://localhost:3000 (1440px)...")
        await page_desktop.goto("http://localhost:3000", wait_until="domcontentloaded")
        await page_desktop.wait_for_timeout(2000)

        # Trigger incident run on Seed 101 with pacing
        print("[2/5] Triggering incident run for Seed 101 (Paced stream)...")
        trigger_btn = page_desktop.locator("button:has-text('INVESTIGATE RECALL')").first
        if await trigger_btn.is_visible():
            await trigger_btn.click()
            
            # Mid-run screenshot: wait 1.5 seconds during active event streaming
            await page_desktop.wait_for_timeout(1500)
            mid_run_path = SCREENS_DIR / "mid_run_1440px.png"
            await page_desktop.screenshot(path=str(mid_run_path), full_page=False)
            footer_mid = await page_desktop.locator("footer").inner_text()
            print(f"  [SAVED MID-RUN] {mid_run_path}")
            print(f"  Mid-Run Footer Status: {footer_mid.encode('ascii', errors='replace').decode('ascii').replace(chr(10), ' | ')}")

            # Completion screenshot: wait for full quiescence and episode.closed event
            print("  Waiting for episode.closed event (STATUS: complete)...")
            await page_desktop.locator("#footer-status:has-text('complete')").wait_for(timeout=35000)
            await page_desktop.wait_for_timeout(600)
            comp_path = SCREENS_DIR / "after_1440px.png"
            await page_desktop.screenshot(path=str(comp_path), full_page=False)
            footer_comp = await page_desktop.locator("footer").inner_text()
            print(f"  [SAVED COMPLETION] {comp_path}")
            print(f"  Completion Footer Status: {footer_comp.encode('ascii', errors='replace').decode('ascii').replace(chr(10), ' | ')}")

        # Verify drawer toggle and capture drawer screenshot
        drawer_btn = page_desktop.locator("button:has-text('LEDGER [L]')").first
        if await drawer_btn.is_visible():
            await drawer_btn.click()
            await page_desktop.wait_for_timeout(1000)
            drawer_path = SCREENS_DIR / "after_1440px_drawer.png"
            await page_desktop.screenshot(path=str(drawer_path), full_page=False)
            print(f"  [SAVED] {drawer_path}")
            await page_desktop.keyboard.press("Escape")
            await page_desktop.wait_for_timeout(500)

        await context_desktop.close()

        # -------------------------------------------------------------
        # 2. Mobile Viewport (390 x 844)
        # -------------------------------------------------------------
        print("[3/5] Navigating to production app at http://localhost:3000 (390px mobile)...")
        context_mobile = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
            is_mobile=True,
            has_touch=True,
        )
        page_mobile = await context_mobile.new_page()
        await page_mobile.goto("http://localhost:3000", wait_until="domcontentloaded")
        await page_mobile.wait_for_timeout(2000)

        trigger_btn_mob = page_mobile.locator("button:has-text('INVESTIGATE RECALL')").first
        if await trigger_btn_mob.is_visible():
            await trigger_btn_mob.click()
            await page_mobile.locator("#footer-status:has-text('complete')").wait_for(timeout=35000)
            await page_mobile.wait_for_timeout(600)

        mobile_after_path = SCREENS_DIR / "after_390px.png"
        await page_mobile.screenshot(path=str(mobile_after_path), full_page=True)
        print(f"  [SAVED MOBILE] {mobile_after_path}")

        await context_mobile.close()
        await browser.close()
        print("[4/5] All production screenshots captured successfully!")


if __name__ == "__main__":
    asyncio.run(main())
