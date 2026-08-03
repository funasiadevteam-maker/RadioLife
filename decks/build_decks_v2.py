#!/usr/bin/env python3
"""BigFM decks v2 — rebuilt per user revisions:
  R1 · Split multi-image slides (2×2 grids, 4-shot combos) so each
     screenshot renders full-width at native aspect ratio.
  R2 · Add "Advertiser Module" section (7 slides) — the full advertiser
     journey as its own product surface.
  R3 · Add "Merchant Lead-Gen Flywheel" section (4 slides) — Predict &
     Win + Trivia Sponsorships + Sponsored Games, framed as 0%
     commission lead-gen (distinct from ad-product revenue).
  R4 · Renumber consistently; footer n/total reflects new counts.

Outputs:
  /app/decks/BigFM_Investor_Deck_v2.pptx
  /app/decks/BigFM_Sales_Deck_v2.pptx

Keeps v1 files untouched.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from build_decks import (
    new_deck, add_bg, add_text, add_bullet_list, add_footer_and_number,
    add_image_with_border, gradient_accent_bar,
    add_title_slide, add_content_slide, add_table_slide,
    add_grid_tiles_slide, add_diagram_solution_slide,
    s, OUT_DIR,
    NAVY, NAVY2, PURPLE, PINK, CREAM, SUBTLE, DIM, WHITE, AMBER, GREEN,
    SLIDE_W, SLIDE_H,
)
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


# ─── extra helpers ────────────────────────────────────────

def add_hero_shot_slide(prs, num, total, *, title, subtitle, image,
                                                caption=None, tint=PURPLE):
    """One big screenshot at native 16:9 with a tight caption."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        title, size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            subtitle, size=14, color=SUBTLE)
    # 1440×900 shots → 16:10 aspect.  Slide inner area 12.5"×5.0".
    top = Inches(2.15)
    # Match the source screenshot aspect (1440x900 → 1.6 ratio)
    img_h = Inches(4.5)
    img_w = Inches(img_h.inches * 1.6)     # 7.2"
    x = Inches((13.333 - img_w.inches) / 2)
    add_image_with_border(slide, image, x, top, img_w, img_h, border=tint)
    if caption:
        add_text(slide, Inches(0.4), top + img_h + Inches(0.15),
                            Inches(12.5), Inches(0.4), caption,
                            size=12, color=SUBTLE, align=PP_ALIGN.CENTER)
    add_footer_and_number(slide, num, total)


def add_dual_shot_slide(prs, num, total, *, title, subtitle,
                                              images, tint=PURPLE):
    """Two screenshots side-by-side, each at native aspect.
    `images` = [(Path, caption)]."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        title, size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            subtitle, size=14, color=SUBTLE)
    top = Inches(2.15)
    each_w = Inches(6.05); each_h = Inches(3.78)     # 16:10 native
    gap = Inches(0.25)
    x0 = Inches((13.333 - (2 * each_w.inches + gap.inches)) / 2)
    for i, (img, cap) in enumerate(images[:2]):
        x = x0 + i * (each_w + gap)
        add_image_with_border(slide, img, x, top, each_w, each_h, border=tint)
        if cap:
            add_text(slide, x, top + each_h + Inches(0.1),
                                each_w, Inches(0.3), cap,
                                size=11, color=SUBTLE, align=PP_ALIGN.CENTER)
    add_footer_and_number(slide, num, total)


def add_dual_shot_with_bullets(prs, num, total, *, title, subtitle,
                                                              image, caption, bullets,
                                                              tint=PURPLE):
    """Left = hero shot at native ratio; right = key bullets."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        title, size=30, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            subtitle, size=14, color=SUBTLE)
    top = Inches(2.15)
    img_h = Inches(4.5); img_w = Inches(img_h.inches * 1.6)
    add_image_with_border(slide, image, Inches(0.4), top, img_w, img_h,
                                                border=tint)
    if caption:
        add_text(slide, Inches(0.4), top + img_h + Inches(0.1),
                            img_w, Inches(0.35), caption,
                            size=10, color=SUBTLE, align=PP_ALIGN.CENTER)
    # Bullets on the right
    right_x = Inches(0.4) + img_w + Inches(0.35)
    right_w = SLIDE_W - right_x - Inches(0.4)
    add_bullet_list(slide, right_x, top, right_w, Inches(4.5),
                                      bullets, size=13, line_spacing=1.35)
    add_footer_and_number(slide, num, total)


def add_section_break_slide(prs, num, total, *, section_number,
                                                          title, subtitle, tint=PURPLE):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, NAVY)
    # Full-height accent bar
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
        Inches(0.4), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = tint
    bar.line.fill.background()
    # Big section number
    add_text(slide, Inches(1.2), Inches(2.0), Inches(11), Inches(0.6),
                        section_number.upper(), size=13, color=tint, bold=True)
    add_text(slide, Inches(1.2), Inches(2.7), Inches(11), Inches(1.5),
                        title, size=52, bold=True, color=WHITE)
    add_text(slide, Inches(1.2), Inches(4.6), Inches(11), Inches(1.5),
                        subtitle, size=18, color=SUBTLE)
    add_footer_and_number(slide, num, total)


# ══════════ INVESTOR DECK v2 ══════════
def build_investor_v2():
    prs = new_deck()

    # Two-pass build so `n / total` at the footer is exact.
    # Pass 1 — collect the sequence of (add_fn, kwargs) tuples.
    # Pass 2 — call each with the resolved total.
    plan = []

    # 1 · Cover (no counter needed for cover — but keep for symmetry).
    plan.append((add_title_slide, dict(
        eyebrow="Series-A · Pitch",
        title="BigFM",
        subtitle="AI-powered radio + rewards + local commerce.",
        images=[s("21_mobile_home.png"),
                        s("03_marketplace_radiolife.png"),
                        s("16_admin_home.png")],
        footer_note=f"{datetime.now().strftime('%B %Y')}  ·  BigFM · Confidential"),
                    ))

    # 2 · Vision
    def vision(_prs, num, total):
        slide = _prs.slides.add_slide(_prs.slide_layouts[6])
        add_bg(slide, NAVY)
        gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
        add_text(slide, Inches(0.4), Inches(0.75), Inches(12), Inches(0.9),
                            "The Vision", size=32, bold=True, color=WHITE)
        add_text(slide, Inches(1.2), Inches(2.9), Inches(11), Inches(2),
                            "Personalized live radio that turns listening\ninto real-world rewards.",
                            size=38, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        add_text(slide, Inches(1.2), Inches(5.3), Inches(11), Inches(0.6),
                            "Web, mobile — one player, one wallet, one AI RJ.",
                            size=16, color=SUBTLE, align=PP_ALIGN.CENTER)
        add_footer_and_number(slide, num, total)
    plan.append((vision, {}))

    # 3 · Problem
    plan.append((add_content_slide, dict(
        title="The Problem", subtitle="Audio is broken along three axes.",
        bullets=[
            "Legacy radio is one-way and un-personalized — every listener hears the same content at the same time.",
            "Spotify solved on-demand but killed the shared radio moment — no live curation, no serendipity, no AI host.",
            "Local businesses can't buy hyperlocal audio ads programmatically — radio's ad stack still runs on faxed spot orders.",
        ],
        image=s("02_radio_browse_legacy.png"), image_layout="right",
        caption="Today's audio: fragmented, un-monetized locally, one-way.")))

    # 4 · Solution diagram
    plan.append((add_diagram_solution_slide, dict(
        title="The Solution",
        subtitle="One AI-curated radio stack — engagement layer + ad platform + local commerce.",
        rings=[
            ("Live radio · podcasts · news · trivia", "Non-interactive queue, AI RJ personas, breaking news"),
            ("Marketplace · wallet · rewards", "Save → visit → redeem → earn"),
            ("11 ad products", "Boosts, sponsored reads, retargeting, coupon CPA…"),
            ("Admin console · analytics · ops", "QA dashboard, location intel, revenue live"),
        ])))

    # 5-8 · SPLIT R1 — Listener Experience → 4 hero shots
    plan.append((add_hero_shot_slide, dict(
        title="Listener · Discover", subtitle="Home tab · flagship stations + breaking news + trending.",
        image=s("01_home_radiolife.png"),
        caption="RadioLife light theme — Home tab.")))
    plan.append((add_hero_shot_slide, dict(
        title="Listener · Save", subtitle="Marketplace tab · deals grid + featured slots + geo-relevant offers.",
        image=s("03_marketplace_radiolife.png"),
        caption="RadioLife light theme — Marketplace.", tint=PINK)))
    plan.append((add_hero_shot_slide, dict(
        title="Listener · Learn", subtitle="News tab · breaking ribbon + AI-summarised regional headlines + on-demand bulletins.",
        image=s("04_news_live_radiolife.png"),
        caption="RadioLife light theme — News · Live.")))
    plan.append((add_hero_shot_slide, dict(
        title="Listener · Redeem", subtitle="Wallet tab · coupons + points ledger + tier badges + scan-to-pay history.",
        image=s("06_wallet_radiolife.png"),
        caption="RadioLife light theme — Wallet.", tint=PINK)))

    # 9 · Radio Engine
    plan.append((add_content_slide, dict(
        title="The Radio Engine",
        subtitle="Server-side personalized queue + AI RJ voiceovers + geo-flagship routing.",
        bullets=[
            "Non-interactive queue: no on-demand search, no per-song skip abuse — protects rights + creates the moment.",
            "AI RJ personas (ElevenLabs) bridge songs with real-time weather / commute / mood context.",
            "Flagship routing gives 15 stations first-shelf placement per region, with pre-roll parity across community stations.",
            "Compliance rules baked in: hourly skip cap, cross-station artist cooldown, sponsor read frequency guard.",
        ],
        image=s("08_station_detail.png"), image_layout="right",
        caption="Big FM 106.2 · station page with flagship + AI RJ chips.")))

    # 10-11 · SPLIT R1 — Engagement Flywheel → Podcasts + Trivia (News covered in slide 7)
    plan.append((add_hero_shot_slide, dict(
        title="Engagement · Podcasts", subtitle="818 channels · 3,935 episodes · progressive completion rewards.",
        image=s("05_podcasts_radiolife.png"),
        caption="RadioLife — Podcasts catalog.")))
    plan.append((add_hero_shot_slide, dict(
        title="Engagement · Trivia", subtitle="Live trivia lobbies · sponsored rounds · leaderboard.",
        image=s("07_trivia_radiolife.png"),
        caption="RadioLife — Trivia lobby.", tint=PINK)))

    # 12 · Commerce Loop
    plan.append((add_content_slide, dict(
        title="Commerce Loop: Marketplace + Wallet + Rewards",
        subtitle="Save → visit → redeem → earn — three monetization tiers baked in.",
        bullets=[
            "Save a coupon in-app → adds to Wallet, redeemable at merchant.",
            "Visit merchant → geofence detects proximity → passive reward accrual.",
            "Scan-to-pay flow: Stripe Connect app fee split, real-time reconciliation.",
            "Points ledger: earn from listening, saving, redeeming — spend on premium unlocks.",
            "Every merchant txn: platform fee, coupon CPA charge, referral bonus — three layers.",
        ],
        image=s("03_marketplace_radiolife.png"), image_layout="right")))

    # 13 · AI RJ Personas
    plan.append((add_content_slide, dict(
        title="AI RJ Personas",
        subtitle="Voice-branded AI hosts (ElevenLabs) — advertisers can sponsor their reads.",
        bullets=[
            "10 curated personas across dayparts (morning, drive, lunch, night, Friday, devotional).",
            "Each persona has voice + tagline + LLM-driven script conditioned on song, weather, hour, city.",
            "Sponsored RJ reads are a first-class ad product — pay-per-play or takeover-hour bundles.",
            "Admins govern persona safety + brand consistency from the console.",
        ],
        image=s("19_admin_rj_personas.png"), image_layout="right",
        caption="Admin RJ personas management console.")))

    # 14 · Location-Aware
    plan.append((add_content_slide, dict(
        title="Location-Aware Everything",
        subtitle="Commute mode + geofences + hyperlocal analytics all share one geo pipeline.",
        bullets=[
            "Commute mode auto-detects morning / evening drive windows and swaps into a shorter-song queue.",
            "Geofences drive location-boost ads — advertisers reach listeners within 500 m of their storefront.",
            "Foot-traffic linkage attributes scan-to-pay conversions to the ad impression within a 60-min window.",
            "Admin location-intel dashboard exposes it all: heatmaps, regions rank, geofence effectiveness.",
        ],
        image=s("18_admin_location_intel.png"), image_layout="right",
        caption="Admin location intelligence dashboard.")))

    # 15 · Section break — Advertiser Module
    plan.append((add_section_break_slide, dict(
        section_number="Section · Advertiser Module",
        title="One dashboard.\nEleven ad products.",
        subtitle="Stripe test-mode Connect · prepaid wallet · advertiser ships live in under 10 minutes.")))

    # 16 · Advertiser · Command Center
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser · Command Center",
        subtitle="One dashboard.  11 ad products.  Stripe test-mode Connect.  Ships live in <10 minutes.",
        image=s("09_adver_dashboard.png"),
        caption="/advertiser/dashboard — overview view.", tint=PURPLE)))

    # 17 · Advertiser · Setup + Stripe Connect
    plan.append((add_dual_shot_with_bullets, dict(
        title="Business Setup + Stripe Connect",
        subtitle="Advertiser signup → advertisers_v2 record → Stripe onboarding — one flow, three steps.",
        image=s("25_adver_apply.png"),
        caption="/advertiser/apply — new-business intake form.",
        bullets=[
            "Signup captures business name, category, geo, GST/VAT ID.",
            "Auto-creates an advertisers_v2 record; owner_user_id links back to the auth user.",
            "Stripe Connect Express hand-off — test-mode by default, live-mode toggle after admin approval.",
            "Same flow lets an owner add staff members with per-permission roles.",
            "Approval < 24 h for spends < $500; instant self-serve for CPA coupons < $50 wallet.",
        ])))

    # 18 · Advertiser · Wallet Prepay
    plan.append((add_dual_shot_with_bullets, dict(
        title="Wallet-Based Prepay Model",
        subtitle="One wallet · every campaign draws from it · no per-campaign checkout friction.",
        image=s("09_adver_dashboard.png"),
        caption="Wallet widget lives on /advertiser/dashboard.",
        bullets=[
            "Advertiser tops up once (Stripe test-mode Connect) → wallet holds a prepaid balance.",
            "Every campaign — coupon CPA, takeover, banner, location-boost — draws from the same wallet.",
            "Budget cascade across active campaigns; per-campaign daily caps enforced.",
            "Auto-pause when wallet < 20% of daily burn — email + notification alert.",
            "Refunds land back in the wallet within one billing cycle (Stripe reversal + admin note).",
        ])))

    # 19 · Advertiser · Campaign Wizard
    plan.append((add_dual_shot_with_bullets, dict(
        title="Campaign Creation Wizard",
        subtitle="One 3-step pattern used across all 11 ad products: metadata → creative → budget.",
        image=s("14_adver_coupons.png"),
        caption="Coupon Campaign wizard — CPS / CPA / Hybrid pricing.",
        bullets=[
            "Step 1 · Metadata: name, geo, category, days-active window.",
            "Step 2 · Creative: audio spot upload (or generate via Sora 2), banner image, CTA text.",
            "Step 3 · Budget: $ amount, daily cap, kill-switch threshold.",
            "Preview + reach estimate + expected redemption count before you commit.",
            "Same wizard shape for location-boost, retargeting, takeover — no relearning per product.",
        ])))

    # 20 · Advertiser · Approval + Moderation
    plan.append((add_dual_shot_with_bullets, dict(
        title="Approval + Moderation Queue",
        subtitle="LLM ad-copy moderation (ADMOD.1) + admin gate at $500+ ensures brand safety.",
        image=s("28_admin_ad_review.png"),
        caption="/admin/ad-review — moderation queue with LLM flags surfaced.",
        bullets=[
            "Every ad creative auto-runs through the LLM moderator (Phase ADMOD.1): profanity, brand claims, risky verticals.",
            "Flagged copy sits in the admin ad-review queue with the LLM's rationale + suggested rewrites.",
            "Spends ≥ $500 → mandatory admin gate; smaller spends auto-approve.",
            "Admin decisions logged to audit_log; advertiser sees status + reason in-dashboard.",
            "Rejected creatives get one-tap 'edit + resubmit' — no full-wizard restart.",
        ])))

    # 21 · Advertiser · Analytics + Auction Transparency
    plan.append((add_dual_shot_with_bullets, dict(
        title="Live Analytics + Auction Transparency",
        subtitle="Real-time impressions · saves · redemptions · budget burn — plus 'why did I win/lose' per auction.",
        image=s("35_adver_analytics.png"),
        caption="/advertiser/dashboard/analytics — per-campaign metrics.",
        bullets=[
            "Impressions, saves, redemptions refresh every 30 s.",
            "Budget-burn indicator: current burn rate + hours until wallet-empty at that pace.",
            "Auction transparency: for every flagship-boost bid you lost, see the min winning bid + slot fill %.",
            "CPM / CPA / CPS derived metrics computed server-side — no client math bugs.",
            "Export CSV of every impression + attribution event within retention window.",
        ])))

    # 22 · Advertiser · Dispute / Refund
    plan.append((add_dual_shot_with_bullets, dict(
        title="Dispute + Refund Path",
        subtitle="Fraud-flagged redemptions auto-refund. Advertiser can dispute any charge in-dashboard.",
        image=s("29_admin_refunds.png"),
        caption="/admin/refunds — pending refund + dispute queue.",
        bullets=[
            "Every CPA redemption is scored for fraud (velocity, IP, device fingerprint, geo mismatch).",
            "Auto-refund fires for suspicious rows; advertiser sees the refund entry with reason code.",
            "Advertiser can raise a dispute on any charge — routed to admin refund queue.",
            "Admin reviews with the full event trail (impression → save → redemption timestamps).",
            "Reliability guarantee: broken creatives auto-skip → NOT billed (yesterday's Phase 42-B-redux.2 fix).",
        ])))

    # 23 · Why Advertiser-Native
    plan.append((add_content_slide, dict(
        title="Why It's Advertiser-Native",
        subtitle="Every design decision is made from the advertiser's side of the table.",
        bullets=[
            "Self-serve first: campaign live in < 10 minutes for spends < $500.",
            "Prepaid wallet: no invoice cycles, no net-30 politics for small merchants.",
            "No minimums per phase — start with a $50 CPA coupon, pay only per redemption.",
            "Test-mode-first onboarding: build + preview every campaign against test-mode Stripe before flipping to live.",
            "Admin transparency: every auto-refund, every LLM flag, every auction loss is visible in-dashboard.",
        ])))

    # 24 · Monetization Stack table
    plan.append((add_table_slide, dict(
        title="The Monetization Stack",
        subtitle="11 ad products in one platform · one payment rail · one analytics view.",
        headers=["Product",                             "One-line pitch",                                                                            "Pricing model"],
        col_widths=[3, 6, 2.2],
        rows=[
            ("Flagship Boosts",                    "Direct-bid auction for time-boxed slots on flagship stations.",         "CPA (bid) + Stripe"),
            ("Sponsored AI RJ Reads",       "Advertisers sponsor the AI host's bridge between songs.",                    "CPM · pack"),
            ("Location-Boost Ads",              "Geofenced audio + banner ads reaching listeners within 500 m.",     "CPM · geofence"),
            ("Marketplace Featured Slots", "Boosted deal placement above the marketplace grid.",                            "Flat · slot"),
            ("Radio Takeover Hour",            "Own an entire hour: branded overlay + 4 sponsor reads + bonus.",   "$100 – $1000 / hr"),
            ("Retargeting Audiences",       "Re-engage listeners who saved but didn't redeem.  11 signals.",           "CPM · audience"),
            ("Coupon Campaigns (CPA/CPS/Hybrid)", "Pay only when a real customer redeems your coupon.",                "$2 / redemption avg"),
            ("Podcast Completion Rewards", "Sponsor a podcast episode + bonus points to finishers.",                        "CPM + reward"),
            ("Trivia Sponsorships",              "Sponsor a trivia round with branded prize + logo.",                                    "Flat · round"),
            ("Banner Ads",                              "Persistent skyscraper + billboard slots across web.",                              "CPM · placement"),
            ("Notification Campaigns",       "Push a targeted deal / promo to segmented users.",                                    "CPA · send"),
        ])))

    # 25 · Section break — Merchant Lead-Gen Flywheel
    plan.append((add_section_break_slide, dict(
        section_number="Section · Merchant Lead-Gen Flywheel",
        title="A separate revenue stream:\nMerchant-sponsored lead-gen.",
        subtitle="0% commission on prediction volume · merchants pay for LEAD DELIVERY.  A category-defining shape.",
        tint=PINK)))

    # 26 · Predict & Win intro
    plan.append((add_dual_shot_with_bullets, dict(
        title="Introducing Predict & Win",
        subtitle="Kalshi-style prediction markets, native to the radio listening surface.",
        image=s("31_predict_win.png"),
        caption="/predict-win — customer-facing prediction market lobby.",
        bullets=[
            "Users bet on outcomes (sports, weather, entertainment, news) using BigCoin.",
            "Live markets settle against real-world events; participants earn or lose BigCoin.",
            "Built on Polymarket via Predexon proxy — same prediction infrastructure as Kalshi + Polymarket.",
            "Audio-native surface: listeners hear an AI RJ tease → tap in-player → participate without leaving the station.",
            "Radio-first, hyperlocal — no one else is doing this shape.",
        ], tint=PINK)))

    # 27 · Merchant Lead-Gen Model
    plan.append((add_content_slide, dict(
        title="Merchant Lead-Gen Model — 0% Commission",
        subtitle="BigFM does NOT take a cut of prediction volume.  This is not a monetization ad product — it's a lead-gen channel.",
        bullets=[
            "BigFM takes 0% commission on prediction market transactions.",
            "Merchants sponsor Predict & Win campaigns to acquire high-intent users.",
            "Each participant is a warm lead — geo-matched, engagement-verified, wallet-active.",
            "Merchants pay for LEAD DELIVERY (per opt-in + qualifying action) — not for prediction volume.",
            "Cleanly separated from ad-product revenue in the P&L: (a) ad campaigns and (b) lead-gen sponsorships.",
        ])))

    # 28 · Merchant Lead-Gen Flywheel
    plan.append((add_dual_shot_with_bullets, dict(
        title="The Merchant Lead-Gen Flywheel",
        subtitle="Predict & Win + Live Trivia + Sponsored Games — one funnel category, three surfaces.",
        image=s("34_adver_games.png"),
        caption="/advertiser/games — sponsored games marketplace for merchants.",
        bullets=[
            "Predict & Win (Phase PW-M): merchants sponsor markets tied to their category.",
            "Live Trivia Sponsorships (Phase H): merchants own a themed trivia round with logo + prize.",
            "Sponsored Games (Phase AD.2): merchant-branded games on the radio surface (Spin, Scratch, Trivia).",
            "All three flow into the same lead ledger — merchants see cost-per-lead + qualifying-action metrics.",
            "Distinct from ad impressions: users EARN something (BigCoin, points, prizes) in exchange for their engagement.",
        ], tint=PINK)))

    # 29 · Category-defining
    plan.append((add_content_slide, dict(
        title="Radio + Prediction Markets — A New Category",
        subtitle="No competitor is doing this shape today.",
        bullets=[
            "Kalshi: desktop-focused prediction markets, no radio integration, no local surface.",
            "Polymarket: crypto-native, high-friction on-ramp, US-restricted for many markets.",
            "BigFM: audio-first · hyperlocal · merchant-embedded · Predexon-brokered · no crypto UX friction.",
            "The wedge: predictions become a NATIVE part of the radio listening moment, not a separate app.",
            "The moat: merchants get lead-gen from a fully-attributed audio audience they can't reach elsewhere.",
        ])))

    # 30-31 · SPLIT R1 — Admin Ops → 2 slides (Home + QA)
    plan.append((add_hero_shot_slide, dict(
        title="Admin Ops · Command Center",
        subtitle="Phase T — Admin Home dashboard · system status ribbon + KPIs + real-time revenue.",
        image=s("16_admin_home.png"),
        caption="/admin — unified admin dashboard (Phase T).")))
    plan.append((add_hero_shot_slide, dict(
        title="Admin Ops · Quality + Location Intel",
        subtitle="QA dashboard (Phase Q) + geospatial analytics (Phase S) — same design system.",
        image=s("17_admin_qa.png"),
        caption="/admin/qa — 30 s auto-refresh, cache-transparent.")))

    # 32 · Dual Platform (2-shot, native aspect)
    plan.append((add_dual_shot_slide, dict(
        title="Dual Platform — Web + Mobile",
        subtitle="Same backend.  Same 24 admin routes.  Same 11 ad products.  Native Expo mobile app.",
        images=[(s("01_home_radiolife.png"), "Web · RadioLife theme"),
                        (s("21_mobile_home.png"), "Mobile · Expo native app")])))

    # 33 · Traction
    plan.append((add_content_slide, dict(
        title="Traction Highlights",
        subtitle="Engineering velocity translates directly to product surface.",
        bullets=[
            "58,557 imported radio stations · fully searchable · dual-scheme (HTTP-proxy + HTTPS).",
            "818 podcast channels · 3,935 episodes · progressive completion rewards.",
            "23 notification recipes wired · segmented by geo + role + behavior.",
            "21+ shipped phases (P → T) · dual-design system (Legacy dark + RadioLife light).",
            "Complete admin ops surface: QA dashboard, location intel, revenue-live, ad-review queue.",
            "Web + Expo mobile mirror sharing 100% of the same backend + ad pipeline.",
        ])))

    # 34 · Business Model
    plan.append((add_content_slide, dict(
        title="Business Model — Two Revenue Streams",
        subtitle="Ad-product revenue + Merchant lead-gen revenue — cleanly separated in the P&L.",
        bullets=[
            "Ad revenue: 20–40% platform take on ad prepayments across 11 products (highest on takeover + coupon CPA).",
            "Lead-gen revenue: merchant sponsorship fees for Predict & Win, Trivia, Sponsored Games (0% prediction-volume take).",
            "Stripe app-fee on every scan-to-pay txn: 2.5–5% depending on merchant tier.",
            "Premium listener tier (Q1 roadmap): $2.99 / mo — skip-limit removal, ad-free, HD stream.",
            "Rev-share with claimed stations: 70/30 direct-sold, 50/50 programmatic backfill (Q3 roadmap).",
        ])))

    # 35 · Roadmap
    plan.append((add_table_slide, dict(
        title="Roadmap · Next 4 Quarters",
        subtitle="Growth + platform depth + partner integrations.",
        headers=["Quarter", "Focus",                                                                                                      "Outcome"],
        col_widths=[1.2, 4.5, 4],
        rows=[
            ("Q1", "Mobile Tier 2 · user_location_pings real persistence · premium subs", "Push adoption + new revenue tier"),
            ("Q2", "Retargeting hooks across remaining 6 ad types · ML slot recommendation",  "+25% campaign ROI"),
            ("Q3", "OpenRTB adapter · partner POS APIs · station claim wizard v2",         "Programmatic backfill · POS attribution"),
            ("Q4", "Expansion markets (SG, IN) · creator marketplace · social passport",  "Multi-market SaaS + creator economy"),
        ])))

    # 36 · The Ask
    def ask(_prs, num, total):
        slide = _prs.slides.add_slide(_prs.slide_layouts[6])
        add_bg(slide, NAVY)
        gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
        add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                            "The Ask", size=32, bold=True, color=WHITE)
        add_text(slide, Inches(1.0), Inches(2.4), Inches(11), Inches(1.2),
                            "[ Placeholder ]", size=36, bold=True, color=AMBER,
                            align=PP_ALIGN.CENTER)
        add_text(slide, Inches(1.0), Inches(3.6), Inches(11), Inches(0.7),
                            "$X to accelerate to Y outcome.", size=22, color=WHITE,
                            align=PP_ALIGN.CENTER)
        add_bullet_list(slide, Inches(2.5), Inches(4.6), Inches(9), Inches(2), [
            "Use of funds: engineering (mobile Tier 2 + OpenRTB), sales ramp, expansion markets, creator marketplace pilot.",
            "Milestones: 3 expansion markets live, 100+ paying advertisers, $X ARR, premium subs revenue mix, merchant-lead-gen revenue mix.",
            "Contact: [ your contact block here — email, phone, calendar link ].",
        ], size=13, line_spacing=1.35)
        add_footer_and_number(slide, num, total)
    plan.append((ask, {}))

    total = len(plan)
    for i, (fn, kwargs) in enumerate(plan, start=1):
        if fn is add_title_slide:
            fn(prs, **kwargs)
        else:
            fn(prs, i, total, **kwargs)
    out = OUT_DIR / "BigFM_Investor_Deck_v2.pptx"
    prs.save(str(out))
    return out, total


# ══════════ SALES DECK v2 ══════════
def build_sales_v2():
    prs = new_deck()
    plan = []

    # 1 · Cover
    plan.append((add_title_slide, dict(
        eyebrow="Sales Playbook · v2",
        title="BigFM Sales Playbook",
        subtitle="How to sell BigFM — to advertisers AND radio stations.",
        images=[s("09_adver_dashboard.png"),
                        s("31_predict_win.png"),
                        s("16_admin_home.png")],
        footer_note=f"{datetime.now().strftime('%B %Y')}  ·  BigFM · Confidential · Internal")))

    # 2 · What Is BigFM
    plan.append((add_content_slide, dict(
        title="What Is BigFM  ·  60-second Pitch", subtitle=None,
        bullets=[
            "BigFM is a personalized live radio + local commerce + rewards platform.",
            "Listeners get an AI-curated stream with real AI radio hosts (ElevenLabs voices).",
            "Every action — listen, save a coupon, visit a merchant — earns points redeemable in-app.",
            "Advertisers self-serve 11 ad products via one dashboard (Stripe Connect, prepaid).",
            "Radio station owners monetize their digital stream through BigFM's ad demand + 70/30 rev share.",
        ], image=s("21_mobile_home.png"), image_layout="right",
        caption="Mobile home · listener view (Expo app).")))

    # 3 · Who We Sell To
    def who_we_sell(_prs, num, total):
        slide = _prs.slides.add_slide(_prs.slide_layouts[6])
        add_bg(slide)
        gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
        add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                            "Who We Sell To", size=32, bold=True, color=WHITE)
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            "Two very distinct personas — pitch each with the same product but different lenses.",
                            size=14, color=SUBTLE)
        # Left
        left = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(2.2), Inches(6.1), Inches(4.6))
        left.fill.solid(); left.fill.fore_color.rgb = NAVY2
        left.line.color.rgb = PURPLE; left.line.width = Pt(1.2)
        tf = left.text_frame; tf.margin_left = tf.margin_right = Emu(200000); tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
        p = tf.paragraphs[0]; r = p.add_run(); r.text = "LOCAL BUSINESSES"
        r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = PURPLE
        p = tf.add_paragraph(); r = p.add_run(); r.text = "Restaurants · retail · events · clinics"
        r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = SUBTLE
        p = tf.add_paragraph(); p.line_spacing = 1.6; r = p.add_run()
        r.text = "\nPain:\n\"I can't reach commuters at lunchtime. Facebook ads no longer convert. Radio ads are too expensive for a 3-store chain.\""
        r.font.name = "Calibri"; r.font.size = Pt(13); r.font.color.rgb = WHITE
        p = tf.add_paragraph(); r = p.add_run()
        r.text = "\nSell: coupons (CPA), location-boost, sponsored RJ reads, Predict & Win lead-gen sponsorships.\nEntry point: $50 first campaign, pay-per-redemption."
        r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = AMBER
        # Right
        right = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.2), Inches(6.1), Inches(4.6))
        right.fill.solid(); right.fill.fore_color.rgb = NAVY2
        right.line.color.rgb = PINK; right.line.width = Pt(1.2)
        tf = right.text_frame; tf.margin_left = tf.margin_right = Emu(200000); tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
        p = tf.paragraphs[0]; r = p.add_run(); r.text = "RADIO STATION OWNERS"
        r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = PINK
        p = tf.add_paragraph(); r = p.add_run(); r.text = "Community · flagship · religious · niche"
        r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = SUBTLE
        p = tf.add_paragraph(); p.line_spacing = 1.6; r = p.add_run()
        r.text = "\nPain:\n\"Traditional ad-slot revenue is capped. My digital stream serves listeners but nobody pays for it. Salespeople for programmatic ads never call back.\""
        r.font.name = "Calibri"; r.font.size = Pt(13); r.font.color.rgb = WHITE
        p = tf.add_paragraph(); r = p.add_run()
        r.text = "\nSell: partnership · 70/30 rev share · zero-cost onboarding.\nEntry point: free claim + owner dashboard."
        r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = AMBER
        add_footer_and_number(slide, num, total)
    plan.append((who_we_sell, {}))

    # 4 · Why Now
    plan.append((add_content_slide, dict(
        title="Why Now  ·  Why BigFM",
        subtitle="Three category shifts converging in 2026.",
        bullets=[
            "Personalized audio adoption: 70%+ of drive-time listeners now stream (not FM antenna).",
            "Hyperlocal ad spend shifting from Facebook / Meta back to native audio + geo — attribution finally works.",
            "AI voice branding: ElevenLabs-grade voices at $0.05/min make sponsored RJ reads cost-competitive with pre-recorded spots.",
            "Radio station owners have LOTS of digital reach but zero programmatic revenue — a supply-side gap begging for demand.",
        ])))

    # 5 · Section A · Diagram
    plan.append((add_diagram_solution_slide, dict(
        title="Section A · The BigFM Product",
        subtitle="One player · four value layers · one wallet across all of them.",
        rings=[
            ("Live radio · podcasts · news · trivia",  "Engagement surface"),
            ("Marketplace · wallet · rewards",              "Commerce loop"),
            ("11 ad products",                                          "Monetization engine"),
            ("Admin console · analytics · ops",              "Governance + insights"),
        ])))

    # 6 · Section A.5 break — Advertiser Module
    plan.append((add_section_break_slide, dict(
        section_number="Section A.5 · Advertiser Module",
        title="The Advertiser Command Center.",
        subtitle="One dashboard · 11 ad products · Stripe test-mode Connect.  Ships live in <10 min.")))

    # 7 · Advertiser · Command Center
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser · Command Center",
        subtitle="One dashboard.  11 ad products.  Stripe test-mode Connect.  Ships live in <10 minutes.",
        image=s("09_adver_dashboard.png"),
        caption="/advertiser/dashboard — overview view.")))

    # 8 · Setup + Stripe Connect
    plan.append((add_dual_shot_with_bullets, dict(
        title="Business Setup + Stripe Connect",
        subtitle="Advertiser signup → advertisers_v2 record → Stripe onboarding.",
        image=s("25_adver_apply.png"),
        caption="/advertiser/apply — new-business intake.",
        bullets=[
            "Signup captures business name, category, geo, GST/VAT ID.",
            "Auto-creates advertisers_v2 record; owner_user_id links back to auth user.",
            "Stripe Connect Express hand-off — test-mode by default.",
            "Approval < 24 h for spends < $500; instant self-serve for CPA < $50.",
            "Multi-user: owner can add staff via /advertiser/staff/invite.",
        ])))

    # 9 · Wallet
    plan.append((add_dual_shot_with_bullets, dict(
        title="Wallet-Based Prepay Model",
        subtitle="One wallet · every campaign draws from it · zero per-campaign checkout friction.",
        image=s("09_adver_dashboard.png"),
        caption="Wallet widget on /advertiser/dashboard.",
        bullets=[
            "Advertiser tops up once → wallet holds a prepaid balance.",
            "Every campaign draws from the same wallet — no re-authorization.",
            "Budget cascade across active campaigns; per-campaign daily caps.",
            "Auto-pause at wallet < 20% of daily burn — email + notification alert.",
            "Refunds land back in the wallet within one billing cycle.",
        ])))

    # 10 · Campaign Wizard
    plan.append((add_dual_shot_with_bullets, dict(
        title="Campaign Creation Wizard",
        subtitle="One 3-step pattern used across all 11 ad products.",
        image=s("14_adver_coupons.png"),
        caption="Coupon Campaign wizard (CPS / CPA / Hybrid).",
        bullets=[
            "Step 1 · Metadata: name, geo, category, days-active.",
            "Step 2 · Creative: audio spot (or Sora 2 generate), banner, CTA.",
            "Step 3 · Budget: $ amount, daily cap, kill-switch threshold.",
            "Preview + reach estimate before you commit.",
            "Same shape for location-boost, retargeting, takeover — no relearning.",
        ])))

    # 11 · Approval + Moderation
    plan.append((add_dual_shot_with_bullets, dict(
        title="Approval + Moderation Queue",
        subtitle="LLM ad-copy moderation + admin gate at $500+.",
        image=s("28_admin_ad_review.png"),
        caption="/admin/ad-review — LLM flags + admin decisions.",
        bullets=[
            "LLM moderator flags profanity, brand claims, risky verticals.",
            "Flagged copy sits with LLM rationale + suggested rewrites.",
            "$500+ spends → mandatory admin gate; smaller = auto-approve.",
            "Admin decisions logged to audit_log; advertiser sees status inline.",
            "Rejected creatives: one-tap 'edit + resubmit' — no full-wizard restart.",
        ])))

    # 12 · Analytics
    plan.append((add_dual_shot_with_bullets, dict(
        title="Live Analytics + Auction Transparency",
        subtitle="Real-time impressions · saves · redemptions · budget burn.",
        image=s("35_adver_analytics.png"),
        caption="/advertiser/dashboard/analytics — per-campaign.",
        bullets=[
            "Metrics refresh every 30 s.",
            "Budget-burn indicator with wallet-empty ETA.",
            "Auction transparency: min winning bid + slot fill % per loss.",
            "Derived metrics computed server-side (no client math bugs).",
            "CSV export of every impression + attribution event.",
        ])))

    # 13 · Dispute / Refund
    plan.append((add_dual_shot_with_bullets, dict(
        title="Dispute + Refund Path",
        subtitle="Fraud-flagged redemptions auto-refund.  Advertiser disputes in-dashboard.",
        image=s("29_admin_refunds.png"),
        caption="/admin/refunds — pending refund + dispute queue.",
        bullets=[
            "CPA redemptions scored for fraud (velocity, IP, device, geo).",
            "Auto-refund fires; advertiser sees entry with reason code.",
            "In-dashboard dispute button routes to admin queue.",
            "Admin reviews with full event trail.",
            "Broken creatives auto-skip → NOT billed (Phase 42-B-redux.2).",
        ])))

    # 14 · Section B · 11 Products at a Glance
    plan.append((add_grid_tiles_slide, dict(
        title="Section B · 11 Ad Products at a Glance",
        subtitle="Every product ships with real-time analytics + a Stripe test-mode entry.",
        tiles=[
            {"name":"Flagship Boost","pitch":"Direct-bid auction, hour-length flagship slot.","price":"Bid $50+","best_for":"Big brands, launches"},
            {"name":"Sponsored RJ Read","pitch":"AI host bridges songs with your brand.","price":"CPM $8-15","best_for":"Personal-voice brands"},
            {"name":"Location Boost","pitch":"Geofence within 500 m of your storefront.","price":"$0.10-0.50 / imp","best_for":"QSR, dine-in"},
            {"name":"Marketplace Featured","pitch":"Above-the-fold placement in the deals grid.","price":"$5-25 / day","best_for":"Any merchant"},
            {"name":"Takeover Hour","pitch":"Own the entire hour: overlay + 4 reads.","price":"$100-$1000 / hr","best_for":"Movies, festivals"},
            {"name":"Retargeting","pitch":"Re-engage listeners who saved but never redeemed.","price":"CPM $12","best_for":"Chains, services"},
            {"name":"Coupon (CPA / CPS)","pitch":"Pay only per redemption or per sale.","price":"$2 / redemption","best_for":"Restaurants, retail"},
            {"name":"Podcast Reward","pitch":"Bonus points to listeners who finish your episode.","price":"CPM + bonus","best_for":"Media, brand storytelling"},
            {"name":"Trivia Sponsor","pitch":"Sponsor a trivia round with logo + prize.","price":"$25-$150 / round","best_for":"Toys, snacks, brands"},
            {"name":"Banner Ads","pitch":"Persistent skyscraper + billboard slots.","price":"CPM $5-10","best_for":"Awareness campaigns"},
            {"name":"Notification Campaign","pitch":"Push a segmented offer to your ideal user.","price":"CPA $0.20-1.50","best_for":"Retention, promos"},
        ], cols=3, rows=4)))

    # 15-18 · Deep-dives (unchanged from v1, but re-numbered)
    plan.append((add_content_slide, dict(
        title="Deep-dive · Coupon Campaigns (CPS / CPA / Hybrid)",
        subtitle="Only pay when a real customer redeems.  Fraud-refund built in.",
        bullets=[
            "Advertiser sets: $ per redemption, cap per day, geo, category.",
            "Every redemption verified merchant-side (scan-to-pay or manual code).",
            "Fraud detection: velocity + IP + device fingerprint → auto-refund.",
            "Real-time dashboard: impressions → saves → redemptions.",
            "Price: $2 / redemption typical.  Ideal for: restaurants, retail.",
        ], image=s("14_adver_coupons.png"), image_layout="right")))
    plan.append((add_content_slide, dict(
        title="Deep-dive · Location-Boost Ads",
        subtitle="Geofence your storefront.  Reach listeners within 500 m at lunch / dinner.",
        bullets=[
            "Draw a fence on the map — up to 5 zones per campaign.",
            "Density preview shows estimated reach + competing campaigns.",
            "Ad plays as a mid-stream audio spot + companion banner on mobile.",
            "Scan-to-pay within 60 min → automatically attributed to the impression.",
            "Price: $0.10-$0.50 / impression.  Ideal for: QSR, dine-in.",
        ], image=s("13_adver_location_boosts.png"), image_layout="right")))
    plan.append((add_content_slide, dict(
        title="Deep-dive · Radio Takeover Hour",
        subtitle="Own an entire hour on a flagship station.",
        bullets=[
            "One brand · one flagship · one hour · saturated presence.",
            "4 AI-RJ sponsor reads, banner takeover, hero deal, listener bonus.",
            "Live analytics: unique reach, avg time-on-station, deal saves.",
            "Price: $100 – $1,000 / hour by tier and daypart.",
            "Ideal for: movie launches, festivals, product releases.",
        ], image=s("12_adver_takeover_hours.png"), image_layout="right")))
    plan.append((add_content_slide, dict(
        title="Deep-dive · Retargeting Audiences",
        subtitle="Re-engage people who saved your coupon but haven't redeemed.",
        bullets=[
            "11 behavioral signals: saved-not-redeemed, viewed-not-saved, scanned-once, geo-frequent, hour-consistent, and 6 more.",
            "Drag+drop audience builder → run any ad product against it.",
            "Attribution: each redemption tagged with the audience it fired from.",
            "Ideal for: mid-size chains + service businesses with a nurture cycle.",
        ], image=s("11_adver_retargeting.png"), image_layout="right")))

    # 19-22 · SPLIT R1 — Advertiser Onboarding Comic → 4 slides
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser Onboarding · Step 1",
        subtitle="Sign up + top up (Stripe test-mode Connect).",
        image=s("25_adver_apply.png"),
        caption="Step 1 · /advertiser/apply — business intake.")))
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser Onboarding · Step 2",
        subtitle="Pick a product from the command center.",
        image=s("09_adver_dashboard.png"),
        caption="Step 2 · /advertiser/dashboard — pick from 11 products.")))
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser Onboarding · Step 3",
        subtitle="Configure creative + budget in the wizard.",
        image=s("14_adver_coupons.png"),
        caption="Step 3 · Coupon Campaign wizard.")))
    plan.append((add_hero_shot_slide, dict(
        title="Advertiser Onboarding · Step 4",
        subtitle="Ship it — live analytics in 60 s.",
        image=s("35_adver_analytics.png"),
        caption="Step 4 · /advertiser/dashboard/analytics.")))

    # 23 · Objection Handling
    plan.append((add_table_slide, dict(
        title="Objection Handling · Rehearsed Responses",
        subtitle="Six common objections + tight rebuttals.  Practice these.",
        headers=["Objection", "Response"],
        col_widths=[3.5, 6.5],
        rows=[
            ("\"Too small for radio.\"", "Start with $50 CPA coupon — pay only per redemption.  No minimum."),
            ("\"How do I know it works?\"", "Every campaign shows real-time impressions + saves + redemptions in the advertiser dashboard.  Refreshes every 30 s."),
            ("\"I already use Facebook.\"", "Retargeting hooks let you upload your Facebook Custom Audience and re-engage on audio.  Complementary."),
            ("\"Radio is dead.\"", "58,557 stations streaming, 70%+ commute audio via streaming.  Radio moved online — you missed it."),
            ("\"How is this different from Spotify Ads?\"", "Spotify sells CPM against global impressions.  We sell CPA against locally-attributed conversions."),
            ("\"What if you go down?\"", "Same-day fixes.  Broken creatives auto-skip in 2 s.  See Reliability slide."),
        ])))

    # 24 · Case Study
    plan.append((add_content_slide, dict(
        title="Case Study · Karak Cafe",
        subtitle="End-to-end flow demonstrated in test mode.",
        bullets=[
            "Karak Cafe · Karama location · lat/lng geofenced 500 m.",
            "Ran a $2/redemption coupon + a location-boost during lunch (11:30–14:00).",
            "3 nearby-user pings within the geofence · 2 unique users · 1 scan-to-pay conversion tied to the impression.",
            "QA dashboard shows the flow live under Location Intel + Recent Activity.",
            "Real Stripe test-mode charge captured on the merchant side.",
        ], image=s("18_admin_location_intel.png"), image_layout="right",
        caption="Location intel · Karak proximity view.")))

    # 25 · Section B.5 break — Merchant Lead-Gen bridge
    plan.append((add_section_break_slide, dict(
        section_number="Section B.5 · Merchant Lead-Gen Flywheel",
        title="A distinct product category:\nMerchant-sponsored lead-gen.",
        subtitle="0% commission on prediction volume · merchants pay for LEAD DELIVERY.  This is NOT an ad product.",
        tint=PINK)))

    # 26 · Predict & Win intro
    plan.append((add_dual_shot_with_bullets, dict(
        title="Introducing Predict & Win",
        subtitle="Kalshi-style prediction markets, native to radio listening.",
        image=s("31_predict_win.png"),
        caption="/predict-win — customer-facing prediction market lobby.",
        bullets=[
            "Users bet on outcomes (sports, weather, entertainment, news) using BigCoin.",
            "Live markets settle against real-world events; participants earn or lose BigCoin.",
            "Built on Polymarket via Predexon proxy — the same infra as Kalshi + Polymarket.",
            "Audio-native surface: AI RJ tease → tap in-player → participate without leaving.",
            "Radio-first, hyperlocal — no one else is doing this shape.",
        ], tint=PINK)))

    # 27 · Merchant Lead-Gen Model
    plan.append((add_content_slide, dict(
        title="Merchant Lead-Gen Model — 0% Commission",
        subtitle="BigFM does NOT take a cut of prediction volume.  Merchants pay for LEAD DELIVERY.",
        bullets=[
            "BigFM takes 0% commission on prediction market transactions.",
            "Merchants sponsor Predict & Win campaigns to acquire high-intent users.",
            "Each participant is a warm lead — geo-matched, engagement-verified, wallet-active.",
            "Merchants pay for LEAD DELIVERY (per opt-in + qualifying action) — not for prediction volume.",
            "Different budget line from ad campaigns — cleanly separated in the invoice.",
        ])))

    # 28 · Flywheel
    plan.append((add_dual_shot_with_bullets, dict(
        title="The Merchant Lead-Gen Flywheel",
        subtitle="Predict & Win + Live Trivia + Sponsored Games — one funnel, three surfaces.",
        image=s("34_adver_games.png"),
        caption="/advertiser/games — sponsored games marketplace.",
        bullets=[
            "Predict & Win (Phase PW-M): merchants sponsor category-tied markets.",
            "Live Trivia Sponsorships (Phase H): themed round with logo + prize.",
            "Sponsored Games (Phase AD.2): merchant-branded Spin, Scratch, Trivia.",
            "All three flow into the same lead ledger — cost-per-lead + qualifying-action metrics.",
            "Distinct from ad impressions: users EARN something in exchange for engagement.",
        ], tint=PINK)))

    # 29 · Category
    plan.append((add_content_slide, dict(
        title="Radio + Prediction Markets — A New Category",
        subtitle="No competitor is doing this shape today.",
        bullets=[
            "Kalshi: desktop-focused prediction markets, no radio integration.",
            "Polymarket: crypto-native, high-friction on-ramp, US-restricted.",
            "BigFM: audio-first · hyperlocal · merchant-embedded · Predexon-brokered · no crypto UX friction.",
            "The wedge: predictions become NATIVE to the radio listening moment.",
            "The moat: merchants get lead-gen from a fully-attributed audio audience.",
        ])))

    # 30 · Section C · Station Partnership
    plan.append((add_section_break_slide, dict(
        section_number="Section C · Station Partnership",
        title="Bring us your station.\nWe bring you demand.",
        subtitle="Free claim · 70/30 rev share direct-sold · 50/50 programmatic backfill (Q3).")))

    # 31 · Station Value Prop
    plan.append((add_content_slide, dict(
        title="Station Partnership · Value Prop",
        subtitle="Three reasons every station owner should claim their listing today.",
        bullets=[
            "Add BigFM's stream proxy to your player — instantly monetize your digital audience.",
            "Access BigFM's advertiser network — we bring you demand, you keep 70% direct-sold.",
            "Owner dashboard: real listener count + geo + revenue by product + pre-roll fill rate.",
            "Free HTTPS stream proxy fixes mixed-content bugs killing your browser audience.",
        ], image=s("02_radio_browse_legacy.png"), image_layout="right")))

    # 32 · Onboarding
    plan.append((add_content_slide, dict(
        title="Station Onboarding · 4 Steps",
        subtitle="Free.  Under 15 minutes.  Revenue starts on next month's payout cycle.",
        bullets=[
            "1 · Claim your station in the BigFM catalog (search + click).",
            "2 · Verify ownership (broadcast email match OR admin manual review).",
            "3 · Enable pre-roll + AI RJ personas (per-station toggles).",
            "4 · Revenue starts on next month's cycle (Stripe Connect).",
        ], image=s("08_station_detail.png"), image_layout="right",
        caption="Big FM 106.2 · station detail with claim CTA.")))

    # 33 · Rev Share
    plan.append((add_table_slide, dict(
        title="Revenue Share Model",
        subtitle="Configurable per station in the admin panel · numbers are our default proposal.",
        headers=["Revenue source", "Station", "BigFM", "Notes"],
        col_widths=[4.5, 1.5, 1.5, 3.0],
        rows=[
            ("Direct-sold ad plays on your station", "70%", "30%", "Advertiser-picked stations only"),
            ("Sponsored AI RJ reads",                                     "60%", "40%", "BigFM handles voice + LLM cost"),
            ("Programmatic backfill",                                      "50%", "50%", "OpenRTB adapter (Q3 roadmap)"),
            ("Takeover Hour hosted on your station", "80%", "20%", "Station carries the whole hour"),
            ("Marketplace featured slot conversions", "0%",  "100%","Merchant-side ad"),
            ("Coupon redemptions (CPA)",                          "0%",  "100%","Merchant-side conversion"),
            ("Predict & Win / Games lead-gen",              "20%", "0%",  "Merchant pays for leads (0% commission)"),
        ])))

    # 34 · Station Owner Dashboard (one full-width shot — R1)
    plan.append((add_hero_shot_slide, dict(
        title="Station Owner Dashboard",
        subtitle="Every claimed station gets its own analytics + revenue view.  Same admin design system.",
        image=s("16_admin_home.png"),
        caption="Admin Home reference (station-owner view is a scoped subset).")))

    # 35 · What Stations Get For Free
    plan.append((add_content_slide, dict(
        title="What Stations Get For Free",
        subtitle="Five tools included on Day 1, no strings, no upfront cost.",
        bullets=[
            "Auto-import of RSS news feeds — instant news bulletins on your station.",
            "AI RJ persona voice branding — 10 personas, or bring your own via ElevenLabs sample.",
            "HTTPS stream proxy — fixes the mixed-content block that silently kills your browser audience.",
            "Pre-roll ad marketplace — 70% direct-sold, 50% programmatic (Q3+).",
            "Geo-flagship routing — first-shelf placement to boost discoverability.",
        ])))

    # 36 · Reliability slide (kept from v1)
    def reliability(_prs, num, total):
        slide = _prs.slides.add_slide(_prs.slide_layouts[6])
        add_bg(slide)
        gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
        add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                            "Reliability & Ad Ops Rigor", size=32, bold=True, color=WHITE)
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            "Ad creative rot is auto-remediated — broken creative URLs auto-skip in 2 s + fire analytics events so ops can rotate them.  Your campaign never gets stranded.",
                            size=14, color=SUBTLE)
        left_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(2.4), Inches(6.0), Inches(4.5))
        left_card.fill.solid(); left_card.fill.fore_color.rgb = NAVY2
        left_card.line.color.rgb = GREEN; left_card.line.width = Pt(1.2)
        tf = left_card.text_frame; tf.margin_left = tf.margin_right = Emu(200000); tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
        p = tf.paragraphs[0]; r = p.add_run(); r.text = "The Advertiser Promise"
        r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = GREEN
        for line in ["",
            "▸ Your campaign will never sit stuck on a broken creative.",
            "▸ If our ad-serving layer can't decode the audio, the player auto-skips in 2 seconds — the listener never gets stranded.",
            "▸ Every auto-skip fires a `skip` impression with reason=audio_load_error → ops sees it, rotates the creative, and refunds the wasted impression.",
            "▸ You are not billed for auto-skipped impressions.",
        ]:
            p = tf.add_paragraph(); p.line_spacing = 1.4
            r = p.add_run(); r.text = line
            r.font.name = "Calibri"; r.font.size = Pt(12); r.font.color.rgb = WHITE
        right_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.4), Inches(6.1), Inches(4.5))
        right_card.fill.solid(); right_card.fill.fore_color.rgb = NAVY2
        right_card.line.color.rgb = PURPLE; right_card.line.width = Pt(1.2)
        tf = right_card.text_frame; tf.margin_left = tf.margin_right = Emu(200000); tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
        p = tf.paragraphs[0]; r = p.add_run(); r.text = "Case in point · Jul 31 2026"
        r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = PURPLE
        p = tf.add_paragraph(); r = p.add_run()
        r.text = "\nAn upstream demo ad's audio URL rotted (HTML instead of MP3).  Detected + fixed in one dev cycle:"
        r.font.name = "Calibri"; r.font.size = Pt(12); r.font.color.rgb = WHITE
        for line in ["",
            "• Root cause: 3 seed preroll ads' external audio URLs (kozco.com / pixabay) started returning text/html + 403.",
            "• Fix — code: 1-file, 6-line change to PrerollOverlay.onError → auto-skip after 2 s + fire `skip` impression event.",
            "• Fix — data: repointed the 3 rows to a backend-hosted asset.",
            "• Non-regression: AI radio stations kept playing throughout.",
            "• Advertiser billing impact: zero — auto-skips are free.",
        ]:
            p = tf.add_paragraph(); p.line_spacing = 1.3
            r = p.add_run(); r.text = line
            r.font.name = "Calibri"; r.font.size = Pt(10); r.font.color.rgb = CREAM
        add_footer_and_number(slide, num, total)
    plan.append((reliability, {}))

    # 37 · Next Steps + FAQ
    def next_steps(_prs, num, total):
        slide = _prs.slides.add_slide(_prs.slide_layouts[6])
        add_bg(slide)
        gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
        add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                            "Next Steps + FAQ", size=32, bold=True, color=WHITE)
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                            "How to close · what a first-month customer actually gets.",
                            size=14, color=SUBTLE)
        add_text(slide, Inches(0.5), Inches(2.3), Inches(6), Inches(0.4),
                            "How to Close", size=16, bold=True, color=PURPLE)
        add_bullet_list(slide, Inches(0.5), Inches(2.85), Inches(6), Inches(4.5), [
            "Schedule a 30-min demo · in-person if possible.",
            "Offer $100 credit for the first-month campaigns (any product).",
            "Set up a joint QBR calendar (monthly for the first quarter).",
            "Send a follow-up email with the advertiser onboarding link.",
            "Track in Salesforce under 'BigFM · first campaign' pipeline stage.",
        ], size=13, line_spacing=1.4)
        add_text(slide, Inches(7.0), Inches(2.3), Inches(6), Inches(0.4),
                            "Mini-FAQ", size=16, bold=True, color=PINK)
        add_bullet_list(slide, Inches(7.0), Inches(2.85), Inches(6), Inches(4.5), [
            "Payment terms: prepaid wallet (Stripe Connect).  Net-15 for chains > $2 k / mo.",
            "Minimum spend: none for coupon CPA.  $50 minimum wallet top-up.",
            "Cancellation: pause anytime; unused budget refundable within 30 days.",
            "Refunds: full refund on fraud + auto-skipped impressions.",
            "Predict & Win: 0% commission, merchant sponsorship priced per lead.",
        ], size=12, line_spacing=1.35)
        add_footer_and_number(slide, num, total)
    plan.append((next_steps, {}))

    total = len(plan)
    for i, (fn, kwargs) in enumerate(plan, start=1):
        if fn is add_title_slide:
            fn(prs, **kwargs)
        else:
            fn(prs, i, total, **kwargs)
    out = OUT_DIR / "BigFM_Sales_Deck_v2.pptx"
    prs.save(str(out))
    return out, total


def main():
    inv_path, inv_n = build_investor_v2()
    print(f"Investor v2: {inv_path}  slides={inv_n}  {inv_path.stat().st_size // 1024} kB")
    sales_path, sales_n = build_sales_v2()
    print(f"Sales    v2: {sales_path}  slides={sales_n}  {sales_path.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
