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

from playwright.async_api import async_playwright, expect

SITE = sys.argv[1] if len(sys.argv) > 1 else "https://d2u44arueak38s.cloudfront.net"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "hackathon" / "demo"

# (preset value, tab label, file name)
SHOTS = [
    ("iiit", "The gap", "01-the-gap.png"),
    ("iiit", "Spending", "02-what-each-rupee-buys.png"),
    ("iiit", "Kitchen", "03-the-menu-audit.png"),
    ("iiit", "Sources", "04-where-the-numbers-come-from.png"),
    ("dining-hall", "The gap", "05-us-dining-hall.png"),
    ("dining-hall", "Kitchen", "06-us-dining-hall-audit.png"),
    ("custom", "Build", "07-build-a-menu.png"),
]

# Every "solving…" message on the page is a `.loading` element, so the page is
# idle exactly when there are none of them left.
#
# This deliberately does not use `wait_for_function`: Playwright evaluates a
# string predicate in the page's own world with `new Function`, and the site
# serves `script-src 'self'` with no `'unsafe-eval'`, so the CSP that makes
# the site worth shipping would block the check. Locator assertions run in
# Playwright's utility world, which page CSP does not govern.
async def settle(page):
    await page.wait_for_timeout(250)  # let the click re-render before looking
    try:
        await expect(page.locator(".loading")).to_have_count(0, timeout=40_000)
    except AssertionError:
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
