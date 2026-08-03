"""BigFM decks v2 — capture the additional screenshots needed for the
Advertiser Module + Predict & Win / Merchant-Lead-Gen sections.

Existing 24 shots (01-24) live under /app/decks/screenshots/ and are
reused as-is by build_decks_v2.py.  This script only writes NEW files
(25+) so the v1 numbering isn't disturbed."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/app/decks/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

WEB = "https://mobile-games-v2.preview.emergentagent.com"
ADMIN    = ("admin@bigfm.dubai",  "AdminPass123!")
LISTENER = ("test@bigfm.dubai",     "TestUser123!")


async def login(page, email, pw):
    await page.goto(f"{WEB}/login", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_selector('[data-testid="auth-email-input"]', timeout=25000)
    await page.fill('[data-testid="auth-email-input"]', email)
    await page.fill('[data-testid="auth-password-input"]', pw)
    await page.click('[data-testid="auth-submit-btn"]', force=True)
    await page.wait_for_timeout(3500)


async def shoot(page, url, out_name, wait_ms=5000):
    try:
        await page.goto(f"{WEB}{url}", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        # cookie banner dismiss
        await page.evaluate("""() => {
            for (const n of document.querySelectorAll('button,a,div')) {
                const t = (n.textContent || '').trim().toLowerCase();
                if (t === 'accept all' || t === 'essential only') { n.click(); return; }
            }
        }""")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / out_name), full_page=False)
        size = (OUT / out_name).stat().st_size
        print(f"  ✓ {out_name}  {size//1024} kB  url={page.url}")
    except Exception as e:
        print(f"  ✗ {out_name}  err={e}")


async def as_admin(pw):
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-v2-admin",
        headless=True,
        viewport={"width": 1440, "height": 900},
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await login(page, *ADMIN)
    print(f"[admin] logged in; url={page.url}")
    # New captures (25+):
    await shoot(page, "/admin/ad-review",                              "28_admin_ad_review.png")
    await shoot(page, "/admin/refunds",                                    "29_admin_refunds.png")
    await shoot(page, "/advertiser/dashboard/campaigns/new",  "30_adver_campaign_wizard.png")
    await shoot(page, "/admin/predict-win/campaigns",              "32_admin_predict_win.png")
    await shoot(page, "/advertiser/predict-win",                          "33_adver_predict_win.png")
    await shoot(page, "/advertiser/games",                                    "34_adver_games.png")
    await shoot(page, "/advertiser/dashboard/analytics",                                    "35_adver_analytics.png", wait_ms=6500)
    await ctx.close()


async def as_listener(pw):
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/pw-v2-list",
        headless=True,
        viewport={"width": 1440, "height": 900},
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await login(page, *LISTENER)
    print(f"[listener] logged in; url={page.url}")
    # Advertiser-apply as a user WITHOUT any advertiser record
    # (test@ has role=user, so /advertiser/apply renders the signup form)
    await shoot(page, "/advertiser/apply",                     "25_adver_apply.png")
    # Public /predict-win landing
    await shoot(page, "/predict-win",                                "31_predict_win.png")
    await ctx.close()


async def main():
    async with async_playwright() as pw:
        await as_admin(pw)
        await as_listener(pw)
    print("\ndone.")


asyncio.run(main())
