"""Playwright-Rendering für JS-only Deal-Detailseiten."""

from __future__ import annotations


def render_detail(url: str, thread_id: str) -> dict:
    """Lädt ``url`` headless und parst ``threadDetail`` aus ``__INITIAL_STATE__``."""
    from playwright.sync_api import sync_playwright

    from .http_client import UA
    from .parser import parse_detail_from_playwright_html, parse_thread_detail_dict

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context(user_agent=UA, locale="de-DE").new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_function(
                    "() => window.__INITIAL_STATE__ && window.__INITIAL_STATE__.threadDetail",
                    timeout=15_000,
                )
                td = page.evaluate("() => window.__INITIAL_STATE__.threadDetail")
                return parse_thread_detail_dict(td, thread_id)
            except Exception:
                return parse_detail_from_playwright_html(page.content(), thread_id)
        finally:
            browser.close()
