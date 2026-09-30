"""Live browser proof of the Phase 1 exit gate.

Drives a REAL Chromium against the REAL Next.js frontend and the REAL FastAPI
backend: fills the signup form by typing, lands on the dashboard, reloads to
prove the session persists, and signs out. Screenshots at every step.

Not a substitute for the API test suite — this proves the two halves are
actually wired together in a browser, which no unit test can.
"""

from __future__ import annotations

import asyncio
import sys
import time

from playwright.async_api import async_playwright

WEB = "http://localhost:3000"
SHOTS = "/tmp/kynd_phase1_shots"
EMAIL = f"browser-{int(time.time())}@kynd.io"
PASSWORD = "correct-horse-battery-staple"
WORKSPACE = "Browser Proof Co"


async def main() -> int:
    failures: list[str] = []

    def check(condition: bool, label: str) -> None:
        print(f"  {'PASS' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(label)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        print("\n=== 1. SIGNUP FORM ===")
        await page.goto(f"{WEB}/signup")
        await page.wait_for_selector('input[autocomplete="email"]', timeout=60000)
        await page.screenshot(path=f"{SHOTS}/01_signup_empty.png")

        await page.fill('input[autocomplete="email"]', EMAIL)
        await page.fill('input[autocomplete="name"]', "Franco")
        # The workspace field is the only text input without an autocomplete
        # attribute, which makes it addressable without relying on DOM order.
        await page.fill('input[type="text"]:not([autocomplete])', WORKSPACE)
        await page.fill('input[autocomplete="new-password"]', PASSWORD)
        await page.screenshot(path=f"{SHOTS}/02_signup_filled.png")

        values = await page.evaluate(
            """() => Array.from(document.querySelectorAll('input'))
                    .map(i => ({type: i.type, value: i.value}))"""
        )
        print("  form state:", values)
        check(
            any(v["value"] == EMAIL for v in values),
            "email typed into the email field",
        )
        check(
            any(v["type"] == "password" and v["value"] == PASSWORD for v in values),
            "password typed into the password field",
        )

        print("\n=== 2. SUBMIT -> DASHBOARD ===")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=15000)
        # Wait for CONTENT, not networkidle. In dev mode Next.js compiles the
        # route on first visit, and networkidle fires while the page is still
        # showing "Loading your workspace" — the earlier version of this script
        # screenshotted a spinner and called it a failed render.
        await page.wait_for_selector(f"text={WORKSPACE}", timeout=60000)
        await page.screenshot(path=f"{SHOTS}/03_dashboard.png", full_page=True)

        body = await page.inner_text("body")
        check("/dashboard" in page.url, "redirected to the dashboard")
        check(WORKSPACE in body, "workspace name is rendered")
        check(EMAIL in body, "user email is rendered")
        check("OWNER" in body, "role is rendered")
        check("workspace:delete" in body, "OWNER permissions are rendered")

        # The header rendering while the body still says "Loading" is a real
        # defect the text assertions above cannot see — they pass on the
        # header alone. This was caught by screenshotting the live browser and
        # is now asserted so it cannot come back.
        check(
            "Loading" not in body,
            "no leftover spinner once the dashboard has rendered",
        )
        check("Setup status" in body, "dashboard body content rendered, not just the header")

        cookies = await context.cookies()
        session_cookie = next((c for c in cookies if c["name"] == "kynd_session"), None)
        check(session_cookie is not None, "session cookie was set")
        if session_cookie:
            check(session_cookie["httpOnly"], "session cookie is HttpOnly")

        js_can_read = await page.evaluate("() => document.cookie")
        check(
            "kynd_session" not in js_can_read,
            "session cookie is invisible to JavaScript (XSS cannot steal it)",
        )

        print("\n=== 3. RELOAD -> SESSION PERSISTS ===")
        await page.reload(wait_until="networkidle")
        check("/dashboard" in page.url, "still on the dashboard after a reload")
        check(WORKSPACE in await page.inner_text("body"), "workspace still rendered")

        print("\n=== 4. TEAM PAGE ===")
        await page.goto(f"{WEB}/dashboard/team")
        await page.wait_for_selector(f"text={EMAIL}", timeout=60000)
        await page.screenshot(path=f"{SHOTS}/04_team.png", full_page=True)
        team_body = await page.inner_text("body")
        check(EMAIL in team_body, "member row is rendered from the API")
        check("OWNER" in team_body, "member role is rendered")

        print("\n=== 5. SIGN OUT ===")
        await page.click("text=Sign out")
        await page.wait_for_url("**/login", timeout=15000)
        await page.screenshot(path=f"{SHOTS}/05_after_logout.png")
        check("/login" in page.url, "redirected to login after sign out")

        print("\n=== 6. DASHBOARD IS PROTECTED WHEN SIGNED OUT ===")
        await page.goto(f"{WEB}/dashboard", wait_until="networkidle")
        check("/login" in page.url, "signed-out visit to /dashboard redirects to login")
        await page.screenshot(path=f"{SHOTS}/06_protected.png")

        print("\n=== 7. LOG BACK IN ===")
        await page.goto(f"{WEB}/login", wait_until="networkidle")
        await page.fill('input[autocomplete="email"]', EMAIL)
        await page.fill('input[autocomplete="current-password"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=15000)
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=f"{SHOTS}/07_relogin.png", full_page=True)

        relogin_body = await page.inner_text("body")
        check("/dashboard" in page.url, "logged back in")
        check(WORKSPACE in relogin_body, "state persisted across sessions")

        print("\n=== 8. WRONG PASSWORD IS REJECTED ===")
        await page.click("text=Sign out")
        await page.wait_for_url("**/login", timeout=15000)
        await page.fill('input[autocomplete="email"]', EMAIL)
        await page.fill('input[autocomplete="current-password"]', "wrong-password-here")
        await page.click('button[type="submit"]')
        # Wait for the message itself. Waiting only for [role="alert"] to exist
        # resolved while the request was still in flight and read an empty
        # banner — the assertion passed on nothing.
        await page.wait_for_selector("text=Invalid email or password", timeout=30000)
        alert = await page.inner_text('[role="alert"]')
        await page.screenshot(path=f"{SHOTS}/08_bad_password.png")
        print(f"  error shown: {alert!r}")
        check("/login" in page.url, "stayed on login after a bad password")
        check("Invalid email or password" in alert, "readable error, no stack trace")
        check(
            "Traceback" not in alert and ".py" not in alert,
            "no internal detail leaked to the customer",
        )

        # A 401 from the deliberate wrong-password attempt in step 8 is the
        # API behaving correctly; the browser logs every failed response as a
        # console error regardless. Filtering it is not hiding a defect —
        # asserting on it would mean asserting that authentication does NOT
        # reject bad passwords.
        real_errors = [
            e
            for e in console_errors
            if "favicon" not in e.lower() and "401" not in e
        ]
        check(not real_errors, f"no unexpected console errors (saw {len(real_errors)})")
        for err in real_errors[:5]:
            print("    console:", err[:160])

        await browser.close()

    print("\n" + "=" * 62)
    if failures:
        print(f"RESULT: {len(failures)} FAILED")
        for failure in failures:
            print("  -", failure)
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
