"""Registry of image-generation prompts keyed by static-asset slug.

Purpose (Phase STATIC.BOOT, 2026-07-31): every static image the app
references via `/api/static/{category}/{slug}.{ext}` should be
regenerable from a stable, checked-in prompt.  The registry is
consulted by `static_assets_bootstrap.ensure_static_assets_bootstrap()`
at server start — any file listed here that is missing from local disk
gets regenerated via nano_banana (Gemini) using the stored prompt.

Add a new entry whenever you introduce a new static image asset that
lives on backend/static/**/*.  Prompts should be terse, aesthetic,
and safe — they run through Gemini which enforces content policies.

Shape of each registry entry:
    slug: (
        category: str,           # subfolder under backend/static/
        prompt:    str,               # nano_banana prompt
        extension: str,           # "webp" | "png"
        db_hint:  dict | None,   # optional {collection, filter, url_field}
                                                # to stamp the image_url back on the DB
                                                # doc that references this asset.
    )

Slug MUST equal the filename without extension.
"""
from __future__ import annotations
from typing import Dict, Tuple, Optional

# Style tokens shared across FUUSIC branding — plug into prompts so the
# generated art keeps a consistent look.
_PALETTE = "cyan · magenta · UV purple · deep navy"
_STYLE   = ("high-contrast movie-poster collage · dramatic light · "
                     "cinematic bokeh · square composition · no text")


ImagePromptSpec = Tuple[str, str, str, Optional[Dict[str, str]]]

# ── channel_thumbnails ─────────────────────────────────
# NOTE — the canonical channel prompt list lives in
# `services/channel_thumbnails.THUMBNAIL_PROMPTS`.  We MIRROR it here
# only for the two channels historically missing an entry:
# `party_dubai` (had a prompt but missing file) + `news_radio`
# (missing entirely).  The bootstrap will delegate to the channel
# service when the slug exists there; this file is the safety net.
CHANNEL_THUMBNAILS: Dict[str, ImagePromptSpec] = {
    "news_radio": (
        "channel_thumbnails",
        ("Global news broadcast studio: anchor desk silhouette, world map "
          "hologram, glowing 24/7 ticker, deep navy + red + magenta, "
          + _STYLE),
        "webp",
        {"collection": "channels", "filter_key": "_id",
          "url_field": "thumbnail_url",
          "value_template": "/api/static/channel_thumbnails/news_radio.webp"},
    ),
    # party_dubai is already in channel_thumbnails.py — kept here as
    # a mirror so the bootstrap re-heals it on any future prod deploy
    # that ships without the file.
    "party_dubai": (
        "channel_thumbnails",
        ("EDM party movie-poster collage: laser beams, confetti, raised "
          "hands silhouette, glowing DJ booth, " + _PALETTE + ", " + _STYLE),
        "webp",
        {"collection": "channels", "filter_key": "_id",
          "url_field": "thumbnail_url",
          "value_template": "/api/static/channel_thumbnails/party_dubai.webp"},
    ),
}


# ── landing_images (FUUSIC marketing splash) ──────
# All 18 currently shipped landing PNGs are already git-tracked, but we
# register their prompts here so any future prod deploy that ships
# WITHOUT them can self-heal in one boot cycle.
_LANDING_PALETTE = "cyan + magenta + UV purple + soft cream highlights"
_LANDING_STYLE   = ("editorial minimalist illustration · thick outlines · "
                                     "flat colour blocks · square composition · no text")

LANDING_IMAGES: Dict[str, ImagePromptSpec] = {
    "mobile_hero": (
        "landing_images",
        ("Modern smartphone on a soft gradient background showing a music "
          "streaming app with playful cards; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "audio_ads": (
        "landing_images",
        ("Vintage retro radio microphone with sound wave rings emitting "
          "outward, small storefront cluster listening; "
          + _LANDING_PALETTE + "; " + _LANDING_STYLE),
        "png", None,
    ),
    "sponsored_games": (
        "landing_images",
        ("Playful mobile phone displaying a spin-the-wheel game with "
          "sponsor logo card floating above; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "route_based_ads": (
        "landing_images",
        ("City map with commuter route highlighted, pins for cafés + "
          "gas stations along the route, radio waves radiating; "
          + _LANDING_PALETTE + "; " + _LANDING_STYLE),
        "png", None,
    ),
    "live_reporting": (
        "landing_images",
        ("Real-time analytics dashboard on a laptop, sparklines + KPI "
          "tiles, coffee shop desk vibe; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "live_trivia": (
        "landing_images",
        ("Trivia game show on a mobile screen with a Q&A card, prize "
          "trophy, listener silhouettes cheering; "
          + _LANDING_PALETTE + "; " + _LANDING_STYLE),
        "png", None,
    ),
    "game_campaigns": (
        "landing_images",
        ("Sponsored game marketplace mockup — three game tiles (spin, "
          "scratch, trivia) with merchant branding; "
          + _LANDING_PALETTE + "; " + _LANDING_STYLE),
        "png", None,
    ),
    "coupon_wallet": (
        "landing_images",
        ("Digital wallet on a phone showing a stack of colourful coupon "
          "cards with QR codes; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    # Game default artwork — used when a game campaign lacks its own
    # branded cover.  Keep it neutral + on-brand.
    "game_default": (
        "landing_images",
        ("Abstract game controller silhouette on a gradient tile with "
          "confetti particles; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    # Individual game-tile cover art (fallback pool used by the games
    # engine when a campaign doesn't ship its own artwork).
    "game_lucky_draw": (
        "landing_images",
        ("Lucky-draw prize wheel with sparkling stars and a gift box, "
          "colourful confetti burst; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "game_lyric_hunt": (
        "landing_images",
        ("Song lyrics floating above a mic, headphones, and a magnifying "
          "glass, playful search motif; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "game_music_trivia": (
        "landing_images",
        ("Music quiz card with a big Q letter, musical notes flying out, "
          "vinyl record background; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "game_predict_win": (
        "landing_images",
        ("Crystal ball prediction motif with sports/entertainment icons "
          "orbiting, glowing win badge; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "game_scratch_card": (
        "landing_images",
        ("Scratch-off card with silver foil peeled to reveal a star, "
          "coin burst below; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "game_spin_wheel": (
        "landing_images",
        ("Colourful spin-the-wheel with slice segments (coins, coupon, "
          "star, gift), arrow pointer, motion lines; "
          + _LANDING_PALETTE + "; " + _LANDING_STYLE),
        "png", None,
    ),
    # Promo strip banners (16:6 landscape ratio used by PromoBannerCard).
    "promo_community_radio": (
        "landing_images",
        ("Diverse community huddle around a vintage radio, warm street "
          "scene, coffee cups, laughter; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "promo_trivia_rewards": (
        "landing_images",
        ("Trophy on a podium surrounded by trivia Q cards and a phone "
          "screen showing a leaderboard; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
    "promo_try_chat": (
        "landing_images",
        ("Chat bubble emerging from a smartphone with a friendly "
          "AI-robot mascot waving hello; " + _LANDING_PALETTE + "; "
          + _LANDING_STYLE),
        "png", None,
    ),
}


# ── placeholders — universal fallback images for 404 / null cases ─
# Shipped as physical bytes in git; served under `/api/static/
# placeholders/…`.  Frontend `<img onError>` handlers can point at
# these URLs OR the SafeImage component can render them behind the
# probe-fallback pattern.
_PLACEHOLDER_STYLE = ("minimalist branded placeholder illustration; "
                                              "premium quality; no text; deep space background")

PLACEHOLDER_IMAGES: Dict[str, ImagePromptSpec] = {
    "bigfm_logo": (
        "placeholders",
        ("Bold FUUSIC wordmark 'bigFM' with a stylized broadcast tower "
          "icon, glowing magenta-to-cyan gradient wordmark on deep-space "
          "black; iconic and readable at small sizes; " + _PLACEHOLDER_STYLE),
        "png", None,
    ),
    "station_default": (
        "placeholders",
        ("Stylized microphone silhouette centered inside a soft "
          "magenta-to-cyan gradient orb, subtle sound waves; universal "
          "radio-station placeholder feel; " + _PLACEHOLDER_STYLE),
        "webp", None,
    ),
    "merchant_default": (
        "placeholders",
        ("Friendly storefront awning icon on a warm cream + coffee-brown "
          "tile; universal generic business placeholder; "
          + _PLACEHOLDER_STYLE),
        "png", None,
    ),
    "ad_creative_default": (
        "placeholders",
        ("Minimal geometric 'AD' badge with a soft golden ring on a "
          "deep-navy tile; professional advertising-slot marker; "
          + _PLACEHOLDER_STYLE),
        "png", None,
    ),
}


REGISTRY: Dict[str, ImagePromptSpec] = {}
REGISTRY.update(CHANNEL_THUMBNAILS)
REGISTRY.update(LANDING_IMAGES)
REGISTRY.update(PLACEHOLDER_IMAGES)


__all__ = ["REGISTRY", "CHANNEL_THUMBNAILS", "LANDING_IMAGES",
                    "PLACEHOLDER_IMAGES", "ImagePromptSpec"]
