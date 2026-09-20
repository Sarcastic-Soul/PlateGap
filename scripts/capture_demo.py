#!/usr/bin/env python3
"""Screenshot the live site, for the write-up.

Shoots the four tabs on the Indian mess preset and two on the US dining hall,
against whatever URL is passed (the live site by default). It fails loudly if
the browser console reports an error -- a screenshot of a broken page is worse
than no screenshot, and a duplicated CORS header once made the site look
perfectly healthy to curl while every request from a browser failed.

    uv run --group dev python scripts/capture_demo.py
    uv run --group dev python scripts/capture_demo.py http://127.0.0.1:8123
"""

import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "https://d2u44arueak38s.cloudfront.net"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "hackathon" / "demo"

# (preset value, tab label, file name)
SHOTS = [
    ("iiit", "The gap", "01-the-gap.png"),
    ("iiit", "What each rupee buys", "02-what-each-rupee-buys.png"),
    ("iiit", "For whoever writes the menu", "03-the-menu-audit.png"),
    ("iiit", "Where the numbers come from", "04-where-the-numbers-come-from.png"),
    ("dining-hall", "The gap", "05-us-dining-hall.png"),
    ("dining-hall", "For whoever writes the menu", "06-us-dining-hall-audit.png"),
]

# The page says one of these while a solve is in flight.
BUSY = "!/Running|Solving|Working|\\.\\.\\./.test(document.body.innerText)"


async def settle(page):
    try:
        await page.wait_for_function(BUSY, timeout=40_000)
    except Exception:
        print("  still busy after 40s", file=sys.stderr)
    await page.wait_for_timeout(1500)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await page.goto(SITE, wait_until="networkidle")
        await settle(page)

        preset = None
        for wanted, tab, name in SHOTS:
            if wanted != preset:
                await page.select_option("select", wanted)
                preset = wanted
                await settle(page)
            await page.get_by_text(tab, exact=True).first.click()
            await settle(page)
            await page.screenshot(path=OUT / name, full_page=True)
            print("wrote", name)
        await browser.close()

    if errors:
        sys.exit("browser console reported errors:\n  " + "\n  ".join(errors[:5]))


asyncio.run(main())
