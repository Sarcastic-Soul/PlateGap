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

THROTTLED = ('{"Reason": "ConcurrentInvocationLimitExceeded", '
             '"Type": "User", "message": "Rate Exceeded."}')


async def throttling(browser, errors, budget):
    """Answer the first `budget` POSTs with the 429 a throttled Lambda sends.

    `budget=4` is exactly what a page load costs, so every call the app makes
    on arrival is thrown away and only the retry can save it. `budget=None`
    never lets one through, which is what the message has to survive.
    """
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    # The 429s are the point of this page, so the browser logging each one is
    # not a finding. Anything else it complains about still is.
    page.on("console", lambda m: errors.append(m.text)
            if m.type == "error" and "429" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    left = [budget]

    async def intercept(route, request):
        if request.method != "POST":
            await route.continue_()
        elif left[0] is None or left[0] > 0:
            if left[0] is not None:
                left[0] -= 1
            await route.fulfill(status=429, content_type="application/json",
                                body=THROTTLED)
        else:
            await route.continue_()

    await page.route("**/*", intercept)
    await page.goto(SITE, wait_until="domcontentloaded")
    return page


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

        # A throttled start recovers by itself, because the burst is shorter
        # than the retry. Every call the page makes on arrival is refused.
        page3 = await throttling(b, errors, 4)
        await settle(page3)
        assert await page3.locator(".error").count() == 0, \
            "a retryable throttle reached the screen"
        assert "targets" in (await page3.inner_text("#view")).lower()

        # And when it never clears, it says what happened rather than
        # "request failed", which reads like the solver is broken.
        page4 = await throttling(b, errors, None)
        await settle(page4)
        said = await page4.inner_text("#view")
        assert "busy" in said.lower(), said[:200]

        await b.close()
    if errors:
        sys.exit("console/page errors:\n  " + "\n  ".join(errors[:8]))
    print("smoke OK")

asyncio.run(main())
