"""Phase K.7 — Comprehensive image sweep for landing-page partner sections,
mobile-preview hero, and game-card thumbnails.

Generates 14 cinematic images via the dedicated `OPENAI_IMAGE_API_KEY`:

    Partner — FOR BUSINESS (3):
        live_trivia, game_campaigns, coupon_wallet
    Partner — FOR ADVERTISERS (3):
        audio_ads, sponsored_games, route_based_ads
    Marketing — MOBILE preview (1):
        mobile_hero
    Game thumbnails — distinct template types (6):
        spin_wheel, scratch_card, music_trivia, predict_win,
        lyric_hunt, lucky_draw

Persistence:
    • Files: /app/backend/static/landing_images/<key>.png
    • DB:      `marketing_assets` collection ({asset_id, key, image_url,
                                                              prompt, created_at, updated_at})
    • Game thumbnails also propagate onto the corresponding rows in
        `games` + `game_campaigns` (best-effort, template-keyed).

Idempotent — re-running skips already-generated files unless --force.

Usage:
    python3 backend/scripts/seed_landing_images.py
    python3 backend/scripts/seed_landing_images.py --force
    python3 backend/scripts/seed_landing_images.py --skip-images
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.seed_landing_images")

ART_DIR = BASE / "static" / "landing_images"
ART_DIR.mkdir(parents=True, exist_ok=True)


BRAND = ("Dark cinematic photography, deep purple and cyan and magenta neon "
              "accents, RadioLife brand palette, premium editorial composition, "
              "no text or logos visible. 1:1 square frame.")

ASSETS = [
    # ── FOR BUSINESS ────────────────────────────────────────────
    {"key": "live_trivia",
      "category": "for_business",
      "prompt": f"Bustling neon-lit bar at night with a large trivia screen "
                      f"on the wall, crowd cheering, glowing magenta and cyan "
                      f"lighting, depth-of-field bokeh on bar bottles. {BRAND}"},
    {"key": "game_campaigns",
      "category": "for_business",
      "prompt": f"A spin wheel mid-rotation next to a gold scratch ticket "
                      f"and floating neon prize confetti, magenta and cyan light, "
                      f"product-shot composition. {BRAND}"},
    {"key": "coupon_wallet",
      "category": "for_business",
      "prompt": f"A neon QR code being scanned by a smartphone camera in a "
                      f"restaurant booth, warm food-court lighting in the background, "
                      f"shallow depth of field. {BRAND}"},
    # ── FOR ADVERTISERS ─────────────────────────────────────────
    {"key": "audio_ads",
      "category": "for_advertisers",
      "prompt": f"A glowing studio microphone in a sound-treated recording "
                      f"booth, animated waveform light bars floating around it, "
                      f"deep purple back-light. {BRAND}"},
    {"key": "sponsored_games",
      "category": "for_advertisers",
      "prompt": f"A mobile phone held in hand showing a branded mobile game "
                      f"with a sponsor logo overlay, neon spin wheel on screen, "
                      f"dark futuristic backdrop. {BRAND}"},
    {"key": "route_based_ads",
      "category": "for_advertisers",
      "prompt": f"A highway at night seen from above with neon location pin "
                      f"markers floating above stores along the route, dramatic "
                      f"bokeh of car taillights. {BRAND}"},
    # ── MOBILE preview ─────────────────────────────────────────
    {"key": "mobile_hero",
      "category": "marketing",
      "prompt": f"A stylized smartphone in a hand at night with a neon city "
                      f"skyline blurred behind, the phone's screen glowing with "
                      f"a dark music app interface (no visible UI text), magenta "
                      f"and cyan reflections on the glass. {BRAND}"},
    # ── GAME thumbnails ─────────────────────────────────────────
    {"key": "game_spin_wheel",
      "category": "game",
      "template_match": ["spin_win", "spin_wheel", "spin", "house_spin"],
      "prompt": f"A neon spin wheel mid-rotation, electric blue and magenta "
                      f"segments, sparks flying outward, dark velvet backdrop, "
                      f"hero product shot. {BRAND}"},
    {"key": "game_scratch_card",
      "category": "game",
      "template_match": ["scratch", "scratch_card"],
      "prompt": f"A gold-foil scratch ticket being partially revealed, neon "
                      f"glow leaking from beneath the foil, dramatic close-up, "
                      f"shallow depth of field. {BRAND}"},
    {"key": "game_music_trivia",
      "category": "game",
      "template_match": ["trivia", "game_trivia", "house_trivia", "music_trivia"],
      "prompt": f"An electric guitar leaning against premium over-ear "
                      f"headphones, both glowing with cyan and magenta neon, "
                      f"vinyl record floating behind. {BRAND}"},
    {"key": "game_predict_win",
      "category": "game",
      "template_match": ["predict_win", "predict", "prediction"],
      "prompt": f"A glowing crystal ball on a marble pedestal with neon "
                      f"arrows curving around it, deep purple back-light, "
                      f"dramatic cinematic composition. {BRAND}"},
    {"key": "game_lyric_hunt",
      "category": "game",
      "template_match": ["lyric", "game_lyric", "house_lyric", "lyric_hunt"],
      "prompt": f"A spinning vinyl record on a turntable with floating song "
                      f"lyric snippets glowing around it (lyrics intentionally "
                      f"illegible / abstract), magenta and cyan neon. {BRAND}"},
    {"key": "game_lucky_draw",
      "category": "game",
      "template_match": ["lucky_draw", "draw", "raffle", "lottery"],
      "prompt": f"A single golden ticket caught in a single bright stage "
                      f"spotlight beam, dust particles glowing in the light, "
                      f"deep purple background. {BRAND}"},
    {"key": "game_default",
      "category": "game",
      "template_match": [],   # fallback
      "prompt": f"A glowing controller, dice, and dollar coin floating in "
                      f"space with neon magenta and cyan ribbons of light, "
                      f"futuristic premium prize composition. {BRAND}"},
    # ── Promo banner cards (Home hero strip) — wide landscape ───────
    {"key": "promo_try_chat",
      "category": "promo_banner",
      "prompt": f"A warm cozy lounge at night with a glowing chat bubble "
                      f"floating beside a vintage broadcast microphone, deep "
                      f"purple and magenta palette, soft cinematic depth of "
                      f"field, evocative editorial composition. {BRAND}"},
    {"key": "promo_community_radio",
      "category": "promo_banner",
      "prompt": f"A diverse mosaic grid of community radio DJs and station "
                      f"tiles lit up at night, cyan and magenta neon glows "
                      f"woven between the panels, futuristic broadcast "
                      f"control wall composition. {BRAND}"},
    {"key": "promo_trivia_rewards",
      "category": "promo_banner",
      "prompt": f"A neon trivia question card floating above a stack of "
                      f"golden coins next to a small spinning wheel, energetic "
                      f"prize-show composition, magenta and cyan stage lights. "
                      f"{BRAND}"},
]


async def _gen(key: str, prompt: str, *, skip: bool, force: bool) -> str | None:
    fname = f"{key}.png"
    disk  = ART_DIR / fname
    if disk.exists() and disk.stat().st_size > 1024 and not force:
        return f"/api/static/landing_images/{fname}"
    if skip:
        return None
    try:
        from services.openai_image_provider import generate_image
        raw = await generate_image(prompt, size="1024x1024",
                                                            quality="standard")
        disk.write_bytes(raw)
        log.info("[landing] generated %s (%d KB)", fname, len(raw) // 1024)
        return f"/api/static/landing_images/{fname}"
    except Exception as e:
        log.error("[landing] gen failed %s: %s", key, e)
        return None


def _match_template(template_match: list, candidate: str | None) -> bool:
    if not candidate or not template_match:
        return False
    cand = (candidate or "").lower()
    return any(tok in cand for tok in template_match)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                              help="Regenerate even if image already on disk.")
    ap.add_argument("--skip-images", action="store_true",
                              help="Persist asset rows without calling OpenAI.")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    generated = persisted = 0

    for a in ASSETS:
        url = await _gen(a["key"], a["prompt"],
                                        skip=args.skip_images, force=args.force)
        if url:
            generated += 1
        # Persist into marketing_assets (idempotent on `key`).
        await db.marketing_assets.update_one(
            {"key": a["key"]},
            {"$set": {"key": a["key"],
                          "category": a["category"],
                          "image_url": url,
                          "prompt": a["prompt"],
                          "updated_at": now},
              "$setOnInsert": {"_id": f"mkt_{a['key']}",
                                              "created_at": now}},
            upsert=True)
        persisted += 1
        # Fan-out: games that match this template get the thumbnail
        if a["category"] == "game" and url:
            matches = a.get("template_match") or []
            for tok in matches:
                # match against `games` collection (3 rows) by _id substring
                await db.games.update_many(
                    {"$or": [
                        {"_id": {"$regex": tok, "$options": "i"}},
                        {"template_type": {"$regex": tok, "$options": "i"}},
                    ]},
                    {"$set": {"thumbnail_url": url}})
                await db.game_campaigns.update_many(
                    {"$or": [
                        {"_id": {"$regex": tok, "$options": "i"}},
                        {"campaign_id": {"$regex": tok, "$options": "i"}},
                        {"template_id": {"$regex": tok, "$options": "i"}},
                    ],
                      "thumbnail_url": {"$in": [None, ""]}},
                    {"$set": {"thumbnail_url": url}})
        # Last entry (game_default) — backfill any remaining un-thumbnailed
        # game_campaigns so EVERY campaign has artwork.
        if a["key"] == "game_default" and url:
            await db.game_campaigns.update_many(
                {"$or": [{"thumbnail_url": {"$in": [None, ""]}},
                              {"thumbnail_url": {"$exists": False}}]},
                {"$set": {"thumbnail_url": url}})
            await db.games.update_many(
                {"$or": [{"thumbnail_url": {"$in": [None, ""]}},
                              {"thumbnail_url": {"$exists": False}}]},
                {"$set": {"thumbnail_url": url}})

    # Index for fast key lookup
    await db.marketing_assets.create_index([("key", 1)], unique=True)
    print(f"[landing] images_generated={generated} assets_persisted={persisted} "
                f"total={len(ASSETS)}")


if __name__ == "__main__":
    asyncio.run(main())
