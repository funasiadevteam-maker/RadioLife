"""Phase 36d Turn 3 — Lightning splits (PLACEHOLDER SCHEMA).

This module stores per-channel and per-episode Lightning value-split
configurations and translates them into the `<podcast:value>` shape the
RSS layer already understands (services/podcast_rss._build_value_block).

NO REAL LIGHTNING PAYMENT PROCESSING happens here. We do not call
LNbits/Alby/BTCPay/LND. We do not validate pubkeys on-chain. We do not
resolve lnaddress endpoints. This is a metadata-only contract so
listeners using Podcasting 2.0 apps (Fountain, Podverse, etc.) can
stream sats to creator-supplied recipients directly via the RSS feed.

Collection: `podcast_lightning_splits`
    {
        id:            "lns_<hex>",
        episode_id: None | "pep_xxx",   # None = channel default row
        channel_id: "pch_xxx",
        recipients: [{name, type, address, split_pct, fee_pct,
                                  custom_key?, custom_value?}],
        created_at: datetime,
        updated_at: datetime,
    }

Indexes (built on first call):
    - unique (channel_id, episode_id)   — at most one row per pair
    - (channel_id, episode_id, updated_at desc)
"""
from __future__ import annotations
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger("bigfm.podcast_lightning")

PLATFORM_LIGHTNING_ADDRESS = os.environ.get("PLATFORM_LIGHTNING_ADDRESS", "").strip()

_RE_LNADDRESS = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_RE_HEX66       = re.compile(r"^[0-9a-fA-F]{66}$")


# ─── Validation ──────────────────────────────────────────────────
def _validate_recipient(r: dict, idx: int) -> dict:
    name = (r.get("name") or "").strip()[:120]
    typ      = (r.get("type") or "").strip().lower()
    addr   = (r.get("address") or "").strip()
    if not name:
        raise HTTPException(400, f"recipient[{idx}]: name required")
    if typ not in ("node", "lnaddress"):
        raise HTTPException(400, f"recipient[{idx}]: type must be 'node' or 'lnaddress'")
    if not addr:
        raise HTTPException(400, f"recipient[{idx}]: address required")
    if typ == "node" and not _RE_HEX66.match(addr):
        raise HTTPException(400, f"recipient[{idx}]: node address must be 66-char hex pubkey")
    if typ == "lnaddress" and not _RE_LNADDRESS.match(addr):
        raise HTTPException(400, f"recipient[{idx}]: lnaddress must be in user@domain.tld form")
    try:
        split_pct = float(r.get("split_pct") or 0)
    except Exception:
        raise HTTPException(400, f"recipient[{idx}]: split_pct must be numeric")
    if split_pct < 0 or split_pct > 100:
        raise HTTPException(400, f"recipient[{idx}]: split_pct must be in [0, 100]")
    try:
        fee_pct = float(r.get("fee_pct") or 0)
    except Exception:
        raise HTTPException(400, f"recipient[{idx}]: fee_pct must be numeric")
    if fee_pct < 0 or fee_pct > 10:
        raise HTTPException(400, f"recipient[{idx}]: fee_pct must be in [0, 10]")
    out = {"name": name, "type": typ, "address": addr,
                "split_pct": split_pct, "fee_pct": fee_pct}
    ck = r.get("custom_key")
    cv = r.get("custom_value")
    if ck is not None:
        try: out["custom_key"] = int(ck)
        except Exception:
            raise HTTPException(400, f"recipient[{idx}]: custom_key must be int")
    if cv is not None:
        out["custom_value"] = str(cv)[:200]
    return out


def validate_recipients(recipients: list) -> list:
    if not isinstance(recipients, list):
        raise HTTPException(400, "recipients must be a list")
    if not (1 <= len(recipients) <= 20):
        raise HTTPException(400, "recipients must contain between 1 and 20 entries")
    cleaned = [_validate_recipient(r, i) for i, r in enumerate(recipients)]
    total = sum(r["split_pct"] for r in cleaned)
    if abs(total - 100.0) > 0.5:
        raise HTTPException(
            400, f"split_pct sum must equal 100 (got {total:.2f})")
    return cleaned


# ─── Indexes ─────────────────────────────────────────────────────
_indexes_built = False


async def ensure_indexes(db) -> None:
    global _indexes_built
    if _indexes_built: return
    try:
        await db.podcast_lightning_splits.create_index(
            [("channel_id", ASCENDING), ("episode_id", ASCENDING)],
            unique=True, name="ch_ep_uniq")
        await db.podcast_lightning_splits.create_index(
            [("channel_id", ASCENDING), ("episode_id", ASCENDING),
              ("updated_at", DESCENDING)],
            name="ch_ep_recency")
    except Exception as e:
        logger.warning(f"lightning_splits index build skipped: {e}")
    _indexes_built = True


# ─── Doc helpers ─────────────────────────────────────────────────
def _new_id() -> str:
    return "lns_" + secrets.token_hex(8)


def _now():
    return datetime.now(timezone.utc)


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc: return None
    doc.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = doc.get(k)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── CRUD ────────────────────────────────────────────────────────
async def get_channel_default(db, channel_id: str) -> Optional[dict]:
    await ensure_indexes(db)
    doc = await db.podcast_lightning_splits.find_one(
        {"channel_id": channel_id, "episode_id": None})
    return _serialize(doc)


async def get_episode_override(db, episode_id: str) -> Optional[dict]:
    await ensure_indexes(db)
    doc = await db.podcast_lightning_splits.find_one(
        {"episode_id": episode_id})
    return _serialize(doc)


async def upsert_channel_default(db, *, channel_id: str,
                                                              recipients: list) -> dict:
    await ensure_indexes(db)
    cleaned = validate_recipients(recipients)
    now = _now()
    existing = await db.podcast_lightning_splits.find_one(
        {"channel_id": channel_id, "episode_id": None})
    if existing:
        await db.podcast_lightning_splits.update_one(
            {"id": existing["id"]},
            {"$set": {"recipients": cleaned, "updated_at": now}})
        return _serialize(await db.podcast_lightning_splits.find_one(
            {"id": existing["id"]}))
    doc = {"id": _new_id(), "channel_id": channel_id, "episode_id": None,
                "recipients": cleaned, "created_at": now, "updated_at": now}
    await db.podcast_lightning_splits.insert_one(doc)
    return _serialize(doc)


async def upsert_episode_override(db, *, channel_id: str,
                                                                episode_id: str,
                                                                recipients: list) -> dict:
    await ensure_indexes(db)
    cleaned = validate_recipients(recipients)
    now = _now()
    existing = await db.podcast_lightning_splits.find_one(
        {"episode_id": episode_id})
    if existing:
        await db.podcast_lightning_splits.update_one(
            {"id": existing["id"]},
            {"$set": {"recipients": cleaned, "updated_at": now,
                          "channel_id": channel_id}})
        return _serialize(await db.podcast_lightning_splits.find_one(
            {"id": existing["id"]}))
    doc = {"id": _new_id(), "channel_id": channel_id,
                "episode_id": episode_id, "recipients": cleaned,
                "created_at": now, "updated_at": now}
    await db.podcast_lightning_splits.insert_one(doc)
    return _serialize(doc)


async def delete_episode_override(db, *, episode_id: str) -> bool:
    await ensure_indexes(db)
    r = await db.podcast_lightning_splits.delete_one(
        {"episode_id": episode_id})
    return r.deleted_count > 0


# ─── Phase P2 Hygiene — Single source-of-truth helper ────────────
# Canonical write path used by BOTH `PATCH /channels/{cid}/value-config`
# (when `splits` field is provided) AND `PUT /channels/{cid}/lightning-splits`.
# Writes to `podcast_lightning_splits` first (SoT), then mirrors the cleaned
# recipient list into `channel.value_config.splits` as a read-only cache so
# legacy consumers that still read from the channel doc continue to work
# until they migrate.
async def write_channel_splits(db, *, channel_id: str,
                                                      recipients: list) -> dict:
    canonical = await upsert_channel_default(
        db, channel_id=channel_id, recipients=recipients)
    # Mirror into channel.value_config.splits (legacy read cache).
    await db.podcast_channels.update_one(
        {"id": channel_id},
        {"$set": {"value_config.splits": canonical["recipients"],
                          "value_config.updated_at": _now()}})
    return canonical


async def reconcile_all_channel_splits(db) -> dict:
    """One-shot backfill: walks every channel, picks
    `podcast_lightning_splits` as winner on conflict, mirrors back into
    `channel.value_config.splits`. Idempotent — running twice in a row
    produces `reconciled: 0` on the second call (only changed-on-disk
    rows count).
    """
    await ensure_indexes(db)
    walked = 0
    reconciled = 0
    conflicts: list[dict] = []
    cur = db.podcast_channels.find({}, {"id": 1, "value_config": 1, "_id": 0})
    async for ch in cur:
        walked += 1
        cid = ch.get("id")
        if not cid: continue
        sot = await db.podcast_lightning_splits.find_one(
            {"channel_id": cid, "episode_id": None},
            {"recipients": 1, "_id": 0})
        inline = ((ch.get("value_config") or {}).get("splits")) or []
        sot_recipients = (sot or {}).get("recipients") or []
        if sot_recipients:
            # SoT wins. Mirror only if channel doc is out of sync.
            if inline != sot_recipients:
                await db.podcast_channels.update_one(
                    {"id": cid},
                    {"$set": {"value_config.splits": sot_recipients,
                                      "value_config.updated_at": _now()}})
                reconciled += 1
                if inline:
                    conflicts.append({"channel_id": cid,
                                                  "reason": "sot_winner_overrode_inline"})
        elif inline:
            # No SoT row but channel doc has splits → backfill SoT.
            # Best-effort validate; skip channel if recipients are malformed
            # (the legacy inline doc was never schema-checked).
            try:
                await upsert_channel_default(
                    db, channel_id=cid, recipients=inline)
                reconciled += 1
            except HTTPException as e:
                conflicts.append({"channel_id": cid,
                                              "reason": f"inline_backfill_failed:{e.detail}"})
    return {"channels_walked": walked, "reconciled": reconciled,
                  "conflicts": conflicts}


async def get_episode_resolved(db, *, channel_id: str,
                                                          episode_id: str) -> Optional[dict]:
    """Return the episode override if present, else the channel default
    with `inherited_from_channel=True` stamped on the response. Returns
    None if neither exists."""
    override = await get_episode_override(db, episode_id)
    if override:
        override["inherited_from_channel"] = False
        return override
    default = await get_channel_default(db, channel_id)
    if not default: return None
    default["inherited_from_channel"] = True
    default["episode_id"] = episode_id  # surface caller's context
    return default


# ─── Seed ────────────────────────────────────────────────────────
async def seed_channel_default_if_missing(db, *, channel_id: str,
                                                                              creator: dict) -> dict:
    """Idempotent seed used the first time a creator enables splits on
    a channel. If a row already exists, return it untouched."""
    existing = await get_channel_default(db, channel_id)
    if existing: return existing

    creator_pubkey = (creator.get("lightning_address") or "").strip()
    # Default seed: 70% creator (placeholder if blank), 20% guests (only
    # if last episode had guests), 10% platform — adjust to sum=100.
    last_ep = await db.podcast_episodes.find_one(
        {"channel_id": channel_id},
        sort=[("published_at", -1)])
    guests = []
    if last_ep:
        async for g in db.podcast_recording_participants.find(
                {"session_id": last_ep.get("recording_session_id"),
                  "role": {"$in": ["guest", "co_host"]}},
                {"display_name": 1, "lightning_address": 1, "_id": 0}):
            guests.append(g)

    creator_split = 70.0
    guest_split_total = 20.0 if guests else 0.0
    if not guests:
        creator_split += 20.0
    platform_split = 100.0 - creator_split - guest_split_total

    recipients = [{
        "name":          (creator.get("display_name") or "Creator"),
        "type":            "lnaddress" if _RE_LNADDRESS.match(creator_pubkey or "") else "node",
        "address":     creator_pubkey or ("00" * 33),  # placeholder — creator MUST fill in
        "split_pct": creator_split,
        "fee_pct":     0.0,
    }]
    if guests:
        per_guest = round(guest_split_total / len(guests), 2)
        # Distribute rounding remainder onto first guest.
        assigned = 0.0
        for i, g in enumerate(guests):
            this = per_guest if i < len(guests) - 1 else round(
                guest_split_total - assigned, 2)
            assigned += this
            g_addr = (g.get("lightning_address") or "").strip() or ("00" * 33)
            recipients.append({
                "name":          g.get("display_name") or f"Guest {i+1}",
                "type":            "lnaddress" if _RE_LNADDRESS.match(g_addr) else "node",
                "address":     g_addr,
                "split_pct": this,
                "fee_pct":     0.0,
            })
    if platform_split > 0:
        plat_addr = PLATFORM_LIGHTNING_ADDRESS or ("00" * 33)
        recipients.append({
            "name":          "FUUSIC platform",
            "type":            "lnaddress" if _RE_LNADDRESS.match(plat_addr) else "node",
            "address":     plat_addr,
            "split_pct": platform_split,
            "fee_pct":     0.0,
        })

    # Force exact 100 — push rounding drift onto creator.
    total = sum(r["split_pct"] for r in recipients)
    if abs(total - 100.0) > 0.0001:
        recipients[0]["split_pct"] = round(
            recipients[0]["split_pct"] + (100.0 - total), 2)

    return await upsert_channel_default(
        db, channel_id=channel_id, recipients=recipients)


# ─── RSS bridge ──────────────────────────────────────────────────
def as_value_config(splits_doc: Optional[dict]) -> Optional[dict]:
    """Translate a podcast_lightning_splits row into the legacy
    value_config shape expected by services.podcast_rss._build_value_block.
    Returns None if the doc is empty.
    """
    if not splits_doc or not splits_doc.get("recipients"):
        return None
    splits_out = []
    for r in splits_doc["recipients"]:
        item = {
            "name":          r.get("name"),
            "type":            r.get("type"),
            "address":     r.get("address"),
            # _build_value_block uses int(split); preserve precision.
            "split":         round(float(r.get("split_pct") or 0)),
            "fee":             float(r.get("fee_pct") or 0) > 0,
        }
        if r.get("custom_key") is not None:
            item["custom_key"] = r["custom_key"]
        if r.get("custom_value") is not None:
            item["custom_value"] = r["custom_value"]
        splits_out.append(item)
    return {"enabled": True, "method": "keysend",
                "suggested": "0.00000005000", "splits": splits_out}


async def overlay_rss_value_configs(db, *, channel: dict,
                                                                          episodes: list) -> None:
    """Mutates `channel` and each `episode` in `episodes` to overlay the
    `value_config` field from podcast_lightning_splits (NEW collection).
    Episode override wins; otherwise the channel default is inherited so
    each <item> in the RSS is self-contained per podcastindex.org spec."""
    await ensure_indexes(db)
    channel_id = channel.get("id")
    ch_default = await get_channel_default(db, channel_id) if channel_id else None
    ch_vc = as_value_config(ch_default)
    if ch_vc:
        channel["value_config"] = ch_vc

    if not episodes: return
    ep_ids = [e.get("id") for e in episodes if e.get("id")]
    overrides: dict = {}
    async for d in db.podcast_lightning_splits.find(
            {"episode_id": {"$in": ep_ids}}):
        overrides[d["episode_id"]] = _serialize(d)
    for ep in episodes:
        ov = overrides.get(ep.get("id"))
        vc = as_value_config(ov) if ov else ch_vc
        if vc:
            ep["value_config"] = vc
