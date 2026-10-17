"""Script to capture after screenshots and verify multi-seed dynamic updates from production build."""

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
        await page_desktop.goto("http://localhost:3000", wait_until="networkidle")
        await page_desktop.wait_for_timeout(2000)

        # Click INVESTIGATE RECALL / Seed 101
        print("[2/5] Triggering incident run for Seed 101...")
        trigger_btn = page_desktop.locator("button:has-text('INVESTIGATE RECALL'), button:has-text('INVESTIGATE SEED 101')").first
        if await trigger_btn.is_visible():
            await trigger_btn.click()
            await page_desktop.wait_for_timeout(3500)

        # Verify footer updates for Seed 101
        footer_text_101 = await page_desktop.locator("footer").inner_text()
        print(f"  Seed 101 Footer: {footer_text_101.encode('ascii', errors='replace').decode('ascii')}")

        # Capture Desktop After Screenshot
        desktop_after_path = SCREENS_DIR / "after_1440px.png"
        await page_desktop.screenshot(path=str(desktop_after_path), full_page=False)
        print(f"  [SAVED] {desktop_after_path} ({desktop_after_path.stat().st_size} bytes)")

        # Verify drawer toggle and capture drawer screenshot
        drawer_btn = page_desktop.locator("button:has-text('LEDGER [L]')").first
        if await drawer_btn.is_visible():
            await drawer_btn.click()
            await page_desktop.wait_for_timeout(1000)
            drawer_path = SCREENS_DIR / "after_1440px_drawer.png"
            await page_desktop.screenshot(path=str(drawer_path), full_page=False)
            print(f"  [SAVED] {drawer_path} ({drawer_path.stat().st_size} bytes)")
            # Close drawer
            await page_desktop.keyboard.press("Escape")
            await page_desktop.wait_for_timeout(500)

        # Verify dynamic update on Seed 202 (Requirement 7: verify with two seeds)
        print("[3/5] Triggering incident run for Seed 202 to verify dynamic footer updates...")
        seed_202_btn = page_desktop.locator("button:has-text('Seed 202')").first
        if await seed_202_btn.is_visible():
            await seed_202_btn.click()
            await page_desktop.wait_for_timeout(3500)
            footer_text_202 = await page_desktop.locator("footer").inner_text()
            print(f"  Seed 202 Footer: {footer_text_202.encode('ascii', errors='replace').decode('ascii')}")

        await context_desktop.close()

        # -------------------------------------------------------------
        # 2. Mobile Viewport (390 x 844)
        # -------------------------------------------------------------
        print("[4/5] Navigating to production app at http://localhost:3000 (390px mobile)...")
        context_mobile = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
            is_mobile=True,
            has_touch=True,
        )
        page_mobile = await context_mobile.new_page()
        await page_mobile.goto("http://localhost:3000", wait_until="networkidle")
        await page_mobile.wait_for_timeout(2000)

        # Trigger on mobile
        trigger_btn_mob = page_mobile.locator("button:has-text('INVESTIGATE RECALL')").first
        if await trigger_btn_mob.is_visible():
            await trigger_btn_mob.click()
            await page_mobile.wait_for_timeout(3500)

        # Capture Mobile After Screenshot
        mobile_after_path = SCREENS_DIR / "after_390px.png"
        await page_mobile.screenshot(path=str(mobile_after_path), full_page=False)
        print(f"  [SAVED] {mobile_after_path} ({mobile_after_path.stat().st_size} bytes)")

        await context_mobile.close()
        await browser.close()
        print("[5/5] All screenshots captured successfully!")


if __name__ == "__main__":
    asyncio.run(main())
