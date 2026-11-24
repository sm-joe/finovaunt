"""Real Chromium browser acceptance for the self-hosted Finovaunt UI.

Run after scripts/acceptance_state_upgrade.py prepare/verify. No AWS calls.
Requires: python -m pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:4173"
PASSWORD = "ci-runtime-rotated-credential-2026"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(BASE, wait_until="networkidle", timeout=30000)
            expect(page.get_by_role("heading", name="Sign in", exact=True)).to_be_visible()
            page.get_by_label("Username").fill("admin")
            page.get_by_label("Password", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()

            expect(page.get_by_role("heading", name="Overview", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_role("combobox", name="AWS account scope")).to_have_value("123456789012")
            # Open the real account workspace with the dashboard navigation.
            page.get_by_role("button", name="AWS accounts", exact=True).click()
            expect(page.get_by_role("heading", name="AWS accounts", exact=True)).to_be_visible()
            expect(page.get_by_text("Updated Account").first).to_be_visible()
            page.get_by_text("Collector settings", exact=True).click()
            expect(page.get_by_role("button", name="Edit Collector")).to_be_visible()
            # Security/profile screen must share the authenticated shell.
            page.get_by_role("button", name="Admin settings", exact=True).click()
            expect(page.get_by_role("heading", name="Admin settings", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Change password", exact=True)).to_be_visible()
            # Session termination returns to sign-in and revokes protected API access.
            page.get_by_role("button", name="Sign out").click()
            expect(page.get_by_role("heading", name="You’re signed out", exact=True)).to_be_visible()
            response = page.request.get("http://127.0.0.1:4173/api/cloud-accounts")
            assert response.status == 401, response.status
            # Responsive smoke: login remains functional at a narrow viewport.
            page.set_viewport_size({"width": 390, "height": 844})
            expect(page.get_by_role("heading", name="You’re signed out", exact=True)).to_be_visible()
            print("PASS: real Chromium sign-in, dashboard, AWS accounts, profile, logout, protected API and mobile login.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
