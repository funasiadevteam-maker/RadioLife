#!/usr/bin/env python3
"""BigFM decks — screenshot capture (Playwright, headless Chromium).

Captures ~25 screenshots at 3 viewports:
  • Web listener  — 1440x900
  • Web advertiser — 1440x900
  • Web admin — 1440x900
  • Mobile Expo — 390x844

Auth via email/password (session cookies) — Emergent playbook token
placeholder is NOT in the current test_credentials.md, so we use the
classic auth flow which is faster than SSO anyway.

Output: /app/decks/screenshots/*.png
"""
from __future__ import annotations
import asyncio, json, sys, os
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/app/decks/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

WEB   = "https://mobile-games-v2.preview.emergentagent.com"
EXPO  = "https://stream-bridge-9.expo.preview.emergentagent.com"

ADMIN     = ("admin@bigfm.dubai",       "AdminPass123!")
ADVER     = ("advertiser@bigfm.dubai",  "AdvertiserP8!23")
LISTENER  = ("test@bigfm.dubai",        "TestUser123!")

STATUS = []

def log(msg: str) -> None:
    print(f"[capture] {msg}", flush=True)
    STATUS.append(msg)


async def login_web(page, email: str, password: str) -> None:
    """Login via /login page.  Uses auth-email-input testids."""
    await page.goto(f"{WEB}/login", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_selector('[data-testid="auth-email-input"]', timeout=25000)
    await page.fill('[data-testid="auth-email-input"]', email)
    await page.fill('[data-testid="auth-password-input"]', password)
    await page.click('[data-testid="auth-submit-btn"]', force=True)
    # Wait for redirect to /
    await page.wait_for_timeout(3200)


async def shoot(page, url: str, out: str, *, wait_ms: int = 3500,
                            full_page: bool = False,
                            pre_actions=None) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        # Dismiss cookie banner if present
        try:
            await page.evaluate("""() => {
                const nodes = document.querySelectorAll(
                  'button, a, div');
                for (const n of nodes) {
                    const t = (n.textContent || '').trim().toLowerCase();
                    if (t === 'accept all' || t === 'essential only' ||
                        t === 'accept') {
                        n.click(); return;
                    }
                }
            }""")
            await page.wait_for_timeout(400)
        except Exception:
            pass
        if pre_actions:
            try:
                await pre_actions(page)
            except Exception as e:
                log(f"  pre_actions err: {e}")
        await page.screenshot(path=out, full_page=full_page)
        log(f"  ✓ {out}")
        return True
    except Exception as e:
        log(f"  ✗ FAIL {out} => {e}")
        return False


async def capture_web_listener(pw) -> None:
    log("=== web listener ===")
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-listener",
        headless=True,
        viewport={"width": 1440, "height": 900},
        device_scale_factor=1,
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await login_web(page, *LISTENER)
    log(f"  logged in as listener; url={page.url}")

    # 1. Home RadioLife
    await shoot(page, f"{WEB}/?design=radiolife",
                            str(OUT / "01_home_radiolife.png"), wait_ms=5000)
    # 2. Radio Browse Legacy
    await shoot(page, f"{WEB}/radio/browse?design=legacy",
                            str(OUT / "02_radio_browse_legacy.png"), wait_ms=5000)
    # 3. Marketplace
    await shoot(page, f"{WEB}/marketplace?design=radiolife",
                            str(OUT / "03_marketplace_radiolife.png"), wait_ms=5000)
    # 4. News live
    await shoot(page, f"{WEB}/news/live?design=radiolife",
                            str(OUT / "04_news_live_radiolife.png"), wait_ms=5000)
    # 5. Podcasts
    await shoot(page, f"{WEB}/podcasts?design=radiolife",
                            str(OUT / "05_podcasts_radiolife.png"), wait_ms=5000)
    # 6. Wallet
    await shoot(page, f"{WEB}/wallet?design=radiolife",
                            str(OUT / "06_wallet_radiolife.png"), wait_ms=5000)
    # 7. Trivia
    await shoot(page, f"{WEB}/trivia?design=radiolife",
                            str(OUT / "07_trivia_radiolife.png"), wait_ms=5000)
    # 8. Station detail — find a flagship station id
    try:
        # Go to browse, click first station tile
        await page.goto(f"{WEB}/radio/browse", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        # Try to find first station link
        tile = await page.query_selector('a[href^="/station/"]')
        if tile:
            href = await tile.get_attribute("href")
            await shoot(page, f"{WEB}{href}?design=radiolife",
                                    str(OUT / "08_station_detail.png"), wait_ms=5000)
        else:
            # Fallback — use a known flagship id
            await shoot(page, f"{WEB}/station/imp_fun_big_1062_uae?design=radiolife",
                                    str(OUT / "08_station_detail.png"), wait_ms=5000)
    except Exception as e:
        log(f"  station detail fallback: {e}")
        await shoot(page, f"{WEB}/station/imp_fun_big_1062_uae?design=radiolife",
                                str(OUT / "08_station_detail.png"), wait_ms=5000)
    await ctx.close()


async def capture_web_advertiser(pw) -> None:
    log("=== web advertiser ===")
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-adver",
        headless=True,
        viewport={"width": 1440, "height": 900},
        device_scale_factor=1,
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await login_web(page, *ADVER)
    log(f"  logged in as advertiser; url={page.url}")

    routes = [
        ("/advertiser/dashboard",                            "09_adver_dashboard.png"),
        ("/advertiser/dashboard/flagship-boosts",  "10_adver_flagship_boosts.png"),
        ("/advertiser/dashboard/retargeting",         "11_adver_retargeting.png"),
        ("/advertiser/dashboard/takeover-hours",  "12_adver_takeover_hours.png"),
        ("/advertiser/dashboard/location-boosts",  "13_adver_location_boosts.png"),
        ("/advertiser/dashboard/coupons",              "14_adver_coupons.png"),
        ("/advertiser/dashboard/marketplace-slots", "15_adver_marketplace_slots.png"),
    ]
    for path, fname in routes:
        await shoot(page, f"{WEB}{path}",
                                str(OUT / fname), wait_ms=5000)
    await ctx.close()


async def capture_web_admin(pw) -> None:
    log("=== web admin ===")
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-admin",
        headless=True,
        viewport={"width": 1440, "height": 900},
        device_scale_factor=1,
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await login_web(page, *ADMIN)
    log(f"  logged in as admin; url={page.url}")

    routes = [
        ("/admin",                       "16_admin_home.png",       6500),
        ("/admin/qa",                    "17_admin_qa.png",         6500),
        ("/admin/location-intel", "18_admin_location_intel.png", 8500),
        ("/admin/rj-personas",       "19_admin_rj_personas.png",     5000),
        ("/admin/news",                "20_admin_news.png",           5000),
    ]
    for path, fname, wait in routes:
        await shoot(page, f"{WEB}{path}", str(OUT / fname), wait_ms=wait)
    await ctx.close()


async def capture_mobile(pw) -> None:
    log("=== expo mobile ===")
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-mobile",
        headless=True,
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"),
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    # Expo login
    try:
        await page.goto(f"{EXPO}/login", wait_until="domcontentloaded",
                                timeout=45000)
        await page.wait_for_timeout(8000)
        # Placeholder-based selectors (RN web)
        email_input = page.locator('input[placeholder="you@example.com"]').first
        pw_input    = page.locator('input[placeholder="Password"]').first
        await email_input.fill(LISTENER[0])
        await pw_input.fill(LISTENER[1])
        await page.wait_for_timeout(400)
        btn = page.locator('div[data-testid="auth-submit-btn"]').first
        await btn.click(force=True)
        await page.wait_for_timeout(9000)
        log(f"  mobile logged in; url={page.url}")
    except Exception as e:
        log(f"  mobile login WARN: {e}")

    # 21 home
    await shoot(page, f"{EXPO}/home",         str(OUT / "21_mobile_home.png"), wait_ms=6500)
    # 22 news
    await shoot(page, f"{EXPO}/news",         str(OUT / "22_mobile_news.png"), wait_ms=6500)
    # 23 podcasts
    await shoot(page, f"{EXPO}/podcasts", str(OUT / "23_mobile_podcasts.png"), wait_ms=6500)
    # 24 marketplace
    await shoot(page, f"{EXPO}/coupons",   str(OUT / "24_mobile_marketplace.png"), wait_ms=6500)
    # Bonus 25 — mobile wallet
    await shoot(page, f"{EXPO}/wallet",     str(OUT / "25_mobile_wallet.png"), wait_ms=6500)
    await ctx.close()


async def main() -> None:
    async with async_playwright() as pw:
        await capture_web_listener(pw)
        await capture_web_advertiser(pw)
        await capture_web_admin(pw)
        await capture_mobile(pw)
    # Summary
    log("done. files:")
    for p in sorted(OUT.glob("*.png")):
        log(f"  {p.name}  {p.stat().st_size // 1024} kB")

if __name__ == "__main__":
    asyncio.run(main())
