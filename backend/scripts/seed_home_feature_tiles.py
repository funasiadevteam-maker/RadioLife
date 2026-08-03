"""Phase 42-E2.1 — Home Feature Tile config + image-gen seed.

One row per home-page feature tile, persisted in `feature_tiles_config`:

    {
      tile_id:        str,    # "predict_win", "games", "news_radio", …
      title:          str,    # "Predict & Win"
      tagline:        str,    # one-line description
      route:          str,    # frontend path the CTA jumps to
      cta_text:      str,
      lucide_icon: str,    # icon name for the front-end's accessibility tag
      accent:        str,    # "magenta" | "cyan" | "gold" | "lime" | "indigo" | "rose"
      sort_order: int,
      image_url:  str|null, # populated by the seed script.  When null,
                                          # the front-end falls back to a gradient block.
      image_source: str,    # "openai_gpt-image-1" once generated.
      image_prompt: str,    # the prompt used (kept for re-gen audits).
      image_generated_at: ISO,
    }

Idempotent: `seed_home_feature_tiles --force` will re-generate every
image; default behaviour skips rows whose `image_url` already exists.
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

log = logging.getLogger("bigfm.home_feature_tiles")

TILE_DIR = Path("/app/backend/storage/feature_tile_images")
TILE_DIR.mkdir(parents=True, exist_ok=True)

# Six tiles per the E2.1 spec.  Prompts are deliberately cinematic +
# dark + neon so the resulting board feels like a single visual system
# instead of six clip-art panels.
TILES: list[dict] = [
    {
        "tile_id":    "predict_win",
        "title":      "Predict & Win",
        "tagline":  "Call it. Cash it.",
        "route":      "/predict-win",
        "cta_text": "Play today's prediction",
        "lucide_icon": "Trophy",
        "accent":      "magenta",
        "sort_order": 1,
        "image_prompt": (
            "Cinematic dark editorial photograph of a futuristic glowing "
            "neon-magenta crystal ball floating above a polished black "
            "marble surface, soft cyan rim light, volumetric haze, deep "
            "shadows, ultra-detailed reflections, 4k, professional studio "
            "lighting, no text, no watermark."
        ),
    },
    {
        "tile_id":    "games",
        "title":      "Games & Trivia",
        "tagline":  "Spin. Scratch. Win.",
        "route":      "/play-and-win",
        "cta_text": "Play now",
        "lucide_icon": "Gamepad2",
        "accent":      "lime",
        "sort_order": 2,
        "image_prompt": (
            "Cinematic dark photograph of an arcade gameplay table at "
            "night, a glowing lime-green spin wheel slowly turning, "
            "neon-yellow scratch ticket and golden coin shower in mid-air, "
            "deep black background, sharp rim light, 4k, no text, no logos."
        ),
    },
    {
        "tile_id":    "news_radio",
        "title":      "News Radio",
        "tagline":  "Your headlines, in your voice.",
        "route":      "/radio/news",
        "cta_text": "Tune in",
        "lucide_icon": "Radio",
        "accent":      "cyan",
        "sort_order": 3,
        "image_prompt": (
            "Cinematic dark photograph of a vintage chrome studio "
            "microphone bathed in cool cyan and electric blue light, soft "
            "audio waveform glow ribbon arcing behind it, dust particles "
            "in the beam, deep black background, ultra detailed, 4k, no "
            "text, no logos."
        ),
    },
    {
        "tile_id":    "earn_points",
        "title":      "Earn Points",
        "tagline":  "Listen more. Earn more.",
        "route":      "/wallet",
        "cta_text": "Open wallet",
        "lucide_icon": "Coins",
        "accent":      "gold",
        "sort_order": 4,
        "image_prompt": (
            "Cinematic dark photograph of a tall stack of glowing golden "
            "coins on black velvet, soft warm rim light and faint cyan "
            "accent light from above, motion-blurred coin falling, "
            "ultra-detailed embossed coin faces, no text, no logos, 4k."
        ),
    },
    {
        "tile_id":    "commute",
        "title":      "Commute Mode",
        "tagline":  "Maps. Music. Deals.",
        "route":      "/commute",
        "cta_text": "Plan a route",
        "lucide_icon": "Map",
        "accent":      "indigo",
        "sort_order": 5,
        "image_prompt": (
            "Cinematic long-exposure photograph from a low angle of a "
            "highway at night, headlight + taillight streaks in indigo "
            "and warm amber, neon-magenta city skyline far in the "
            "distance, glossy wet asphalt reflections, 4k, no text, no "
            "logos, no people."
        ),
    },
    {
        "tile_id":    "social_passport",
        "title":      "Social Passport",
        "tagline":  "Collect cities. Earn stamps.",
        "route":      "/passport",
        "cta_text": "View passport",
        "lucide_icon": "BadgeCheck",
        "accent":      "rose",
        "sort_order": 6,
        "image_prompt": (
            "Cinematic close-up photograph of an open dark-leather "
            "passport on black velvet, several glowing neon-rose and "
            "gold ink stamps overlapping on the page, soft volumetric "
            "spotlight, embossed metallic crest visible, ultra detailed, "
            "4k, no real country names, no text, no logos."
        ),
    },
]


async def _ensure_collection_seeded(db) -> dict:
    """Insert rows for any new tile_id; refresh title/tagline/route/cta
    on each run so the locked spec values stay in sync (Phase 42-E2.1
    user-confirmed copy)."""
    inserted = 0
    for tile in TILES:
        # Locked spec fields — always overwrite so re-runs converge.
        spec = {k: tile[k] for k in
                        ("title", "tagline", "route", "cta_text",
                          "lucide_icon", "accent", "sort_order",
                          "image_prompt")}
        res = await db.feature_tiles_config.update_one(
            {"tile_id": tile["tile_id"]},
            {"$set": spec,
              "$setOnInsert": {"_id":          f"ftile_{tile['tile_id']}",
                                              "tile_id":      tile["tile_id"],
                                              "image_url":  None,
                                              "image_source": None,
                                              "image_generated_at": None,
                                              "created_at":          datetime.now(timezone.utc)}},
            upsert=True)
        if res.upserted_id is not None:
            inserted += 1
    return {"inserted": inserted, "total_tiles": len(TILES)}


async def seed_feature_tile_images(db, *, force: bool = False) -> dict:
    """Generate the missing tile hero images via gpt-image-1.  Returns
    `{generated, skipped, failed, details}`."""
    seed = await _ensure_collection_seeded(db)
    log.info("[home_feature_tiles] config seeded: %s", seed)

    from services.image_gen import generate as image_generate
    generated, skipped, failed = 0, 0, 0
    details: list[dict] = []
    async for tile in db.feature_tiles_config.find({}).sort("sort_order", 1):
        tile_id = tile["tile_id"]
        if not force and tile.get("image_url"):
            skipped += 1
            details.append({"tile_id": tile_id, "status": "skipped_exists"})
            continue
        prompt = tile.get("image_prompt") or ""
        if not prompt:
            failed += 1
            details.append({"tile_id": tile_id, "status": "no_prompt"})
            continue
        res = await image_generate(
            db, prompt=prompt, user_id="",
            station_slug=f"feature_tile_{tile_id}",
            tier="admin", bypass_rate_limit=True)
        if not res.get("ok"):
            failed += 1
            details.append({"tile_id": tile_id,
                                          "status":  f"gen_failed:{res.get('error')}",
                                          "source": res.get("source")})
            log.error("[home_feature_tiles] gen failed tile=%s err=%s",
                                    tile_id, res.get("error"))
            continue
        url = res["url"]
        await db.feature_tiles_config.update_one(
            {"tile_id": tile_id},
            {"$set": {"image_url":              url,
                            "image_source":      ("cached" if res.get("cached")
                                                                          else "openai_gpt-image-1"),
                            "image_cache_key":  res.get("key"),
                            "image_generated_at":
                                datetime.now(timezone.utc).isoformat()}})
        generated += 1
        details.append({"tile_id": tile_id, "status": "generated",
                                      "image_url": url,
                                      "cached":      res.get("cached")})
        log.info("[home_feature_tiles] generated tile=%s url=%s cached=%s",
                              tile_id, url, res.get("cached"))
    return {"generated": generated, "skipped": skipped,
                  "failed": failed, "total_tiles": len(TILES),
                  "details": details}


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                                          help="Re-generate every tile, ignoring existing image_url")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    res = await seed_feature_tile_images(db, force=args.force)
    print("[home_feature_tiles]",
                {k: v for k, v in res.items() if k != "details"})
    for d in res.get("details", []):
        print("    ", d)


if __name__ == "__main__":
    asyncio.run(_main())
