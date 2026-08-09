"""
Phase 15d — idempotent migrations for the de-Dubai content scrub.

Runs once at server boot. Each migration sets a `_phase15d_renamed`
sentinel flag on touched documents so re-runs are no-ops.

Migrations:
  1. CHANNEL rename: drop the "Dubai" suffix from generic channel names.
  2. BADGE templating: add `display_name_template` carrying `{city}`.
  3. GAME templating: same `display_name_template` on `game_templates` +
      `game_campaigns`.

Seed anchors `biz_demo_karak`, `cpn_qa_*`, `ofr_qa_*` are NEVER touched —
they're QA fixtures Phase 12c relies on.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("bigfm.phase15d")


CHANNEL_RENAME_MAP = {
    "VIP Lounge Dubai":          "VIP Lounge",
    "Bollywood Dubai":            "Bollywood Mehfil",
    "Punjabi Dubai":              "Punjabi Beats",
    "Party Dubai":                  "Party Mix",
    "Late Night Drive Dubai":   "Late Night Drive",
}


async def run_channel_rename(db: Any) -> dict:
    """Idempotent + self-healing. If a channel still carries an old name
       even though `_phase15d_renamed=True` (e.g. a seeder re-overwrote it on
       a later boot), we re-apply the rename. Otherwise we skip."""
    before, renamed, skipped = 0, 0, 0
    cur = db.channels.find({"name": {"$in": list(CHANNEL_RENAME_MAP.keys())}})
    docs = await cur.to_list(length=200)
    before = len(docs)
    for d in docs:
        new_name = CHANNEL_RENAME_MAP[d["name"]]
        # Self-heal: if the doc still matches an old name, force the rename
        # regardless of any stale sentinel from a prior partial run.
        if d.get("_phase15d_renamed") and d["name"] == new_name:
            skipped += 1
            continue
        await db.channels.update_one(
            {"_id": d["_id"]},
            {"$set": {"name": new_name, "_phase15d_renamed": True,
                            "_phase15d_old_name": d["name"]}},
        )
        renamed += 1
    after_dubai = await db.channels.count_documents(
        {"name": {"$regex": r"Dubai$", "$options": "i"}})
    logger.info(
        "Phase 15d channel rename: before=%d renamed=%d already_done=%d "
        "channels_with_dubai_suffix_remaining=%d",
        before, renamed, skipped, after_dubai,
    )
    return {"before": before, "renamed": renamed, "already_done": skipped,
              "dubai_suffix_remaining": after_dubai}


async def run_badge_templating(db: Any) -> dict:
    """Add `display_name_template` to badges whose name contains a city
       token. The template uses `{city}` for runtime substitution.
       Only touches docs where it's safe to infer the template."""
    CITY_TOKENS = ["Dubai", "Dallas", "Frisco", "Mumbai", "New York",
                          "London", "Los Angeles"]
    pattern = "|".join(CITY_TOKENS)
    cur = db.badges.find({
        "display_name": {"$regex": pattern, "$options": "i"},
        "display_name_template": {"$exists": False},
    })
    docs = await cur.to_list(length=2000)
    updated = 0
    for d in docs:
        if d.get("_phase15d_renamed"):
            continue
        name = d.get("display_name") or ""
        template = name
        for token in CITY_TOKENS:
            # Replace the first occurrence only — preserves the rest of the
            # badge identity.
            if token in template:
                template = template.replace(token, "{city}", 1)
                break
        if template == name:
            continue
        await db.badges.update_one(
            {"_id": d["_id"]},
            {"$set": {"display_name_template": template,
                            "_phase15d_renamed": True}},
        )
        updated += 1
    logger.info("Phase 15d badge templating: updated=%d", updated)
    return {"updated": updated}


async def run_game_templating(db: Any) -> dict:
    """Same idea for `game_templates` + `game_campaigns`. QA seed names
       (anything starting with `biz_demo_` / `cpn_qa_` / `ofr_qa_`) are
       skipped explicitly."""
    QA_PREFIXES = ("biz_demo_", "cpn_qa_", "ofr_qa_")
    updated_total = 0
    for coll in ("game_templates", "game_campaigns"):
        try:
            cur = db[coll].find({
                "name": {"$regex": "Dubai", "$options": "i"},
                "display_name_template": {"$exists": False},
            })
            docs = await cur.to_list(length=500)
        except Exception:
            continue
        for d in docs:
            if any((d.get("id") or "").startswith(p) for p in QA_PREFIXES):
                continue
            name = d.get("name") or ""
            template = name.replace("Dubai", "{city}")
            if template == name:
                continue
            await db[coll].update_one(
                {"_id": d["_id"]},
                {"$set": {"display_name_template": template,
                                "_phase15d_renamed": True}},
            )
            updated_total += 1
    logger.info("Phase 15d game templating: updated=%d", updated_total)
    return {"updated": updated_total}


async def run_channel_market_globalisation(db: Any) -> dict:
    """Phase 15d.1 — channels are PROGRAMMING themes, not market-bound. The RJ
       wrapper takes the listener's resolved market, the music catalog filters
       by `markets_allowed`. Any channel still tagged `market: "dubai"` that
       isn't an explicit DFW/regional variant flips to `market: "global"`.
       Idempotent via `_phase15d_market_globalised` sentinel."""
    # Channels named *with* a market suffix (e.g. dfw_*) stay scoped to that
    # market. Everything else (the Dubai-era defaults) globalises.
    REGIONAL_PREFIXES = ("dfw_", "nyc_", "lon_", "mum_", "la_")
    docs = await db.channels.find({"market": {"$ne": "global"}}).to_list(length=500)
    flipped, skipped = 0, 0
    for d in docs:
        cid = d.get("_id", "")
        if any(cid.startswith(p) for p in REGIONAL_PREFIXES):
            skipped += 1
            continue
        if d.get("_phase15d_market_globalised") and d.get("market") == "global":
            skipped += 1
            continue
        await db.channels.update_one(
            {"_id": cid},
            {"$set": {
                "market": "global",
                "_phase15d_market_globalised": True,
                "_phase15d_old_market": d.get("market"),
            }},
        )
        flipped += 1
    logger.info("Phase 15d channel market globalisation: flipped=%d skipped=%d",
                       flipped, skipped)
    return {"flipped": flipped, "skipped": skipped}


_BANNED_DUBAI_REGEX = (
    r"\bDubai\b|\bKarak\b|\bKarama\b|\bJLT\b|\bUAE\b|\bBurj\b|\bLulu\b|"
    r"Marina Mall|Dubai Marina|\bJBR\b|Sheikh\s*Zayed|Global\s*Village|"
    r"Atlantis\s*Dubai|Bur\s*Dubai|\bRTA\b|\bSharjah\b|\bdil\s*se\b|\bdilse\b|"
    r"\byaar\b|\bdoston\b|\bdosto\b|RadioLife\s+DFW|RadioLife\s+NEW_YORK|"
    r"RadioLife\s+LONDON|RadioLife\s+MUMBAI|RadioLife\s+LOS_ANGELES"
)


async def run_rj_script_purge(db: Any) -> dict:
    """Phase 15d.1 v3 — CONTENT-DRIVEN purge across `segments` and
       `rj_audio_qa` (both `initial_script` + `rewritten_script` fields).
       Deletes ANY RJ record whose body matches the banned-Dubai/Hinglish
       regex AND whose resolved market is NOT 'dubai' AND NOT 'mumbai'
       (the two Hinglish markets where these tokens are legitimate).
       Idempotent via `phase15d_rj_purge_v3` flag — bumped from v2 so
       prior deploys re-run."""
    flag_doc = await db.migration_flags.find_one({"_id": "phase15d_rj_purge_v3"})
    if flag_doc and flag_doc.get("done"):
        return {"already_done": True, "deleted": 0,
                  "segments_deleted": 0, "qa_deleted": 0}

    NON_HINGLISH_MARKETS = {"$nin": ["dubai", "mumbai"]}

    # `segments` — single text field rj_script.
    seg_res = await db.segments.delete_many({
        "$or": [
            {"script_market": {"$exists": False}},
            {"script_market": NON_HINGLISH_MARKETS},
        ],
        "rj_script": {"$regex": _BANNED_DUBAI_REGEX, "$options": "i"},
    })

    # `rj_audio_qa` — two text fields, OR'd. Also catches docs missing market.
    qa_res = await db.rj_audio_qa.delete_many({
        "$or": [
            {"market": {"$exists": False}},
            {"market": NON_HINGLISH_MARKETS},
        ],
        "$and": [{"$or": [
            {"initial_script":   {"$regex": _BANNED_DUBAI_REGEX, "$options": "i"}},
            {"rewritten_script": {"$regex": _BANNED_DUBAI_REGEX, "$options": "i"}},
        ]}],
    })

    total = (seg_res.deleted_count or 0) + (qa_res.deleted_count or 0)
    await db.migration_flags.update_one(
        {"_id": "phase15d_rj_purge_v3"},
        {"$set": {"done": True, "deleted": total,
                        "segments_deleted": seg_res.deleted_count,
                        "qa_deleted":         qa_res.deleted_count}},
        upsert=True,
    )
    logger.info(
        "Phase 15d v3 RJ-script purge: segments=%d rj_audio_qa=%d total=%d",
        seg_res.deleted_count or 0, qa_res.deleted_count or 0, total,
    )
    return {"already_done": False, "deleted": total,
              "segments_deleted": seg_res.deleted_count,
              "qa_deleted":         qa_res.deleted_count}


async def run_track_market_audit(db: Any) -> dict:
    """Phase 15d.1 — scan the music catalog for tracks whose titles contain
       market-restrictive city tokens and lock them to that market via
       `markets_allowed`. Idempotent via `_phase15d_track_audited` per-doc."""
    # Token → market mapping. Order matters — first match wins.
    TOKEN_MAP = [
        (r"\bDubai\b|\bKarak\b|\bSharjah\b|\bAbu\s*Dhabi\b", "dubai"),
        (r"\bMumbai\b|\bBombay\b|\bBollywood\b\sMumbai|Marine\s*Drive", "mumbai"),
        (r"\bDelhi\b",         "mumbai"),
        (r"\bLondon\b",        "london"),
        (r"\bNew\s*York\b|\bManhattan\b|\bBrooklyn\b", "new_york"),
        (r"\bDallas\b|\bFort\s*Worth\b|\bDFW\b",       "dfw"),
        (r"\bLA\b|\bHollywood\b|\bVenice\sBeach\b",    "los_angeles"),
    ]
    import re as _re
    cur = db.tracks.find(
        {"_phase15d_track_audited": {"$ne": True}},
        {"_id": 1, "title": 1, "artist": 1, "markets_allowed": 1},
    )
    docs = await cur.to_list(length=2000)
    restricted, free = 0, 0
    locked: list[dict] = []
    for t in docs:
        title = (t.get("title") or "")
        match_market = None
        for pat, mkt in TOKEN_MAP:
            if _re.search(pat, title, _re.IGNORECASE):
                match_market = mkt
                break
        if match_market:
            await db.tracks.update_one(
                {"_id": t["_id"]},
                {"$set": {"markets_allowed": [match_market],
                                "_phase15d_track_audited": True,
                                "_phase15d_lock_reason": f"title matches {match_market}"}},
            )
            restricted += 1
            locked.append({"id": t["_id"], "title": title,
                                "artist": t.get("artist"), "markets_allowed": [match_market]})
        else:
            # No banned token — mark audited so we don't re-scan.
            await db.tracks.update_one(
                {"_id": t["_id"]},
                {"$set": {"_phase15d_track_audited": True}},
            )
            free += 1
    logger.info("Phase 15d track audit: restricted=%d free=%d total=%d",
                       restricted, free, restricted + free)
    return {"restricted": restricted, "free": free,
              "locked_examples": locked[:20]}


async def run_all(db: Any) -> dict:
    """Orchestrator called from server startup."""
    ch       = await run_channel_rename(db)
    badges   = await run_badge_templating(db)
    games    = await run_game_templating(db)
    ch_global = await run_channel_market_globalisation(db)
    rjp       = await run_rj_script_purge(db)
    tracks   = await run_track_market_audit(db)
    return {"channels": ch, "badges": badges, "games": games,
              "channel_globalisation": ch_global,
              "rj_script_purge": rjp, "track_audit": tracks}


# Display helpers — used at read time by the API surfaces that render
# badge / game names back to the client.

def render_with_city(template: str | None, fallback: str | None, market: str | None) -> str:
    """Substitute `{city}` in `template` with the human-readable city.
       Empty template → fallback verbatim."""
    if not template:
        return fallback or ""
    from services.market_lexicon import get_lexicon
    city = get_lexicon(market)["display_name"]
    return template.replace("{city}", city)
