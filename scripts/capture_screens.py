"""Capture UI screenshots at 1440, 1024, and 390 px for verification.

Adheres strictly to ROADMAP.md Section 0 and Part C acceptance criteria.
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

VIEWPORTS = [
    {"name": "1440px", "width": 1440, "height": 900},
    {"name": "1024px", "width": 1024, "height": 768},
    {"name": "390px", "width": 390, "height": 844},
]


def capture_screens(prefix: str, url: str = "http://localhost:3000", wait_ms: int = 1500) -> list[str]:
    root_dir = Path(__file__).resolve().parent.parent
    screens_dir = root_dir / "docs" / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            time.sleep(wait_ms / 1000.0)

            filename = f"{prefix}_{vp['name']}.png"
            file_path = screens_dir / filename
            page.screenshot(path=str(file_path), full_page=False)
            saved_files.append(str(file_path))
            print(f"Captured: {file_path}")
            context.close()
        browser.close()

    return saved_files


if __name__ == "__main__":
    step_prefix = sys.argv[1] if len(sys.argv) > 1 else "screen"
    capture_screens(step_prefix)
