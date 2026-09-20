#!/usr/bin/env python3
"""Click through the front end, against a running site.

Screenshots only prove the page renders. This drives the parts of it that a
screenshot cannot reach -- the controls, the price box, the builder, and a
share link round-tripping into a fresh tab -- and fails on any browser console
error or uncaught exception.

    PORT=8123 uv run python scripts/dev_server.py
    SITE=http://127.0.0.1:8123 uv run --group dev python scripts/smoke_ui.py

With no SITE it runs against the local dev server on port 8123.
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright, expect

SITE = os.environ.get("SITE", "http://127.0.0.1:8123")
# Idle is "no `.loading` element anywhere". Checked with a locator rather than
# `wait_for_function`, because the live site serves `script-src 'self'` and a
# string predicate would be evaluated in the page's own world and blocked.
async def settle(page):
    await page.wait_for_timeout(250)
    await expect(page.locator(".loading")).to_have_count(0, timeout=40_000)
    await page.wait_for_timeout(300)

async def main():
    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(SITE, wait_until="networkidle")
        await settle(page)

        # diet chip
        await page.get_by_role("button", name="Vegan", exact=True).click()
        await settle(page)
        assert "aria-pressed=\"true\"" in await page.inner_html(".chips")
        # day
        await page.select_option("aside select >> nth=1", "wed")
        await settle(page)
        # sex / activity
        await page.select_option("aside select >> nth=3", "female")
        await settle(page)
        # grams slider
        await page.fill("aside input[type=range]", "1900")
        await page.dispatch_event("aside input[type=range]", "change")
        await settle(page)
        assert "1900" in await page.inner_text("aside")

        # price edit re-solves
        await page.get_by_text("The gap", exact=True).click()
        await settle(page)
        box = page.locator("input.price-input").first
        before = await page.inner_text(".headline")
        await box.fill("99")
        await box.dispatch_event("change")
        await settle(page)
        after = await page.inner_text(".headline")
        assert before != after, "price change did not re-solve"

        # audit students slider
        await page.get_by_text("For whoever writes the menu", exact=True).click()
        await settle(page)
        s = page.locator("#view input[type=range]").first
        await s.fill("2000")
        await s.dispatch_event("change")
        await settle(page)
        assert "2000" in await page.inner_text("#view")

        # the builder tab on a preset offers to start one instead
        await page.get_by_text("Build a menu", exact=True).click()
        await settle(page)
        assert "build your own menu" in (await page.inner_text("#view")).lower()
        await page.get_by_role("button", name="Start an empty menu").click()
        await settle(page)
        assert "your menu" in (await page.inner_text("#view")).lower()
        assert await page.input_value("aside select >> nth=0") == "custom"
        await page.get_by_role("button", name="IIIT hostel mess").first.click()
        await settle(page)
        link = await page.input_value("input.share-url")
        assert "#m=" in link
        # remove a dish, add one back through the picker
        chips = page.locator(".meal .chip.dish")
        n = await chips.count()
        await chips.first.click()
        await settle(page)
        assert await page.locator(".meal .chip.dish").count() == n - 1
        await page.get_by_role("button", name="+ Add a dish").first.click()
        await page.fill(".picker input", "paneer")
        await page.wait_for_timeout(200)
        await page.locator(".dish-option").first.click()
        await settle(page)
        assert await page.locator(".meal .chip.dish").count() == n

        # the gap solves against what was built
        await page.get_by_text("The gap", exact=True).click()
        await settle(page)
        assert "targets" in (await page.inner_text("#view")).lower()

        # and the link restores it in a fresh page
        page2 = await b.new_page(viewport={"width": 1440, "height": 1000})
        page2.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page2.on("pageerror", lambda e: errors.append(str(e)))
        await page2.goto(link, wait_until="networkidle")
        await settle(page2)
        await page2.get_by_text("Build a menu", exact=True).click()
        await settle(page2)
        assert await page2.input_value("input.share-url") == link, "link did not round-trip"

        # empty menu asks for dishes rather than erroring
        await page2.get_by_role("button", name="Empty the whole menu").click()
        await settle(page2)
        await page2.get_by_text("The gap", exact=True).click()
        await settle(page2)
        assert "nothing on" in (await page2.inner_text("#view")).lower()

        await b.close()
    if errors:
        sys.exit("console/page errors:\n  " + "\n  ".join(errors[:8]))
    print("smoke OK")

asyncio.run(main())
