"""Capture clean Item 5 production screenshots at 1440px and 390px using Playwright."""

from __future__ import annotations
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)


def capture_screenshots():
    print("Launching Playwright Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 1. Desktop 1440px
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        print("Navigating to http://localhost:3000 at 1440px...")
        page.goto("http://localhost:3000", wait_until="networkidle")
        
        # Trigger investigation
        print("Clicking INVESTIGATE RECALL...")
        page.locator("#btn-investigate").click()
        
        # Wait for completion (status containing complete or episode closed)
        print("Waiting for trace completion...")
        page.wait_for_function(
            "() => document.body.innerText.includes('complete') || document.body.innerText.includes('Episode closed') || document.body.innerText.includes('quiescent')",
            timeout=30000
        )
        # Give SVG render 1.5s to settle
        time.sleep(1.5)
        
        p1440 = SCREENS_DIR / "after_1440px.png"
        page.screenshot(path=str(p1440), full_page=True)
        print(f"Captured: {p1440}")
        
        # Open Why Drawer via Review Queue
        try:
            print("Navigating to Review Queue tab...")
            page.locator("button:has-text('Review Queue')").click()
            time.sleep(0.5)
            why_btn = page.locator("button:has-text('Inspect Why Chain of Custody')").first
            if why_btn.count() > 0:
                print("Clicking Inspect Why Chain of Custody...")
                why_btn.click()
                time.sleep(1.0)
                p_drawer = SCREENS_DIR / "after_1440px_drawer.png"
                page.screenshot(path=str(p_drawer), full_page=True)
                print(f"Captured: {p_drawer}")
        except Exception as e:
            print(f"Why Drawer capture skipped/failed: {e}")
        context.close()
        
        # 2. Mobile 390px
        context_mobile = browser.new_context(viewport={"width": 390, "height": 844})
        page_mobile = context_mobile.new_page()
        print("Navigating to http://localhost:3000 at 390px...")
        page_mobile.goto("http://localhost:3000", wait_until="networkidle")
        time.sleep(1.0)
        p390 = SCREENS_DIR / "after_390px.png"
        page_mobile.screenshot(path=str(p390), full_page=True)
        print(f"Captured: {p390}")
        context_mobile.close()
        
        browser.close()
        print("All screenshots successfully captured!")


if __name__ == "__main__":
    capture_screenshots()
