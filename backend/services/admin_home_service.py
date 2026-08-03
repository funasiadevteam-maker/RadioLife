"""Phase T — Admin Home dashboard service.

Composes:
  • Phase Q QA compact snapshot.
  • Phase S location-intel compact snapshot.
  • Notification recipe count.
  • Latest 5 admin actions (best-effort from `advertiser_audit_log` +
    other queues).
  • Latest 5 `payment_transactions_v2` rows.
  • Latest 5 `advertisers_v2` signups.
  • Overall system status (green / amber / red).

Also owns the global admin search + per-admin nav pins.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.admin_home")

_HOME_CACHE: Dict[str, Any] = {"data": None, "ts": None}
_HOME_TTL_SEC = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes(db) -> None:
    try:
        await db.admin_nav_pins.create_index(
            [("user_id", 1), ("route", 1)], unique=True)
    except Exception as e:
        log.warning("admin_home index setup failed: %s", e)


# ─── home summary ──────────────────────────────────
async def home_summary(db, app_state=None,
                        force_refresh: bool = False) -> Dict[str, Any]:
    ts = _HOME_CACHE.get("ts")
    if not force_refresh and ts and \
            (_now() - ts).total_seconds() < _HOME_TTL_SEC:
        return {**_HOME_CACHE["data"], "cached": True}

    # Phase Q QA compact.
    qa_compact = {"open_alerts": 0, "uptime_seconds": 0,
                  "gross_30d_cents": 0, "active_campaigns": 0,
                  "bg_health": "unknown"}
    try:
        from services.qa_dashboard_service import build_summary as _qa
        qa = await _qa(db, app_state=app_state, force_refresh=False)
        qa_compact["open_alerts"]     = len(qa.get("open_alerts") or [])
        qa_compact["uptime_seconds"] = qa.get("system_health", {}).get("uptime_seconds", 0)
        qa_compact["gross_30d_cents"] = qa.get("revenue_summary", {}) \
                                              .get("last_30d", {}) \
                                              .get("gross_cents", 0)
        qa_compact["active_campaigns"] = sum(
            c.get("active", 0) for c in
            qa.get("data_quality", {}).get("per_collection", []))
        tasks = qa.get("system_health", {}).get("background_tasks_status", [])
        crashed = any(t.get("status") == "crashed" for t in tasks)
        stale   = any(t.get("status") in ("stale", "unknown") for t in tasks)
        qa_compact["bg_health"] = "red" if crashed else \
                                          ("amber" if stale else "green")
    except Exception as e:
        log.warning("qa compact failed: %s", e)

    # Phase S location intel compact.
    loc_compact = {"total_pings": 0, "unique_users": 0,
                    "top_city": None, "most_active_hour": None}
    try:
        from services.location_intel_service import admin_summary as _loc
        loc = await _loc(db, days=30, refresh=False)
        loc_compact["total_pings"]       = loc.get("total_pings", 0)
        loc_compact["unique_users"]      = loc.get("unique_users_pinged", 0)
        loc_compact["top_city"]          = loc.get("top_city")
        loc_compact["most_active_hour"] = loc.get("most_active_hour")
    except Exception as e:
        log.warning("loc-intel compact failed: %s", e)

    # Notification recipe count (23 baseline).
    recipe_count = 0
    try:
        from services.notification_trigger_dispatcher import RECIPES
        recipe_count = len(RECIPES)
    except Exception:
        pass

    # Latest 5 admin actions — union from moderation audit + advertiser
    # audit + station claim actions. Best-effort: pick the most-recent
    # events from `advertiser_audit_log`.
    recent_actions: List[Dict[str, Any]] = []
    try:
        async for r in db.advertiser_audit_log.find(
                {}, {"_id": 0, "advertiser_business_id": 1, "event": 1,
                      "created_at": 1, "actor_user_id": 1,
                      "detail": 1}
                ).sort("created_at", -1).limit(5):
            recent_actions.append({
                "kind":          "audit",
                "event":         r.get("event"),
                "target":        r.get("advertiser_business_id"),
                "actor":         r.get("actor_user_id"),
                "created_at":    r.get("created_at"),
                "detail":        r.get("detail"),
            })
    except Exception:
        pass

    # Latest 5 payments.
    latest_payments: List[Dict[str, Any]] = []
    try:
        async for p in db.payment_transactions_v2.find(
                {"status": "succeeded"},
                {"_id": 0, "transaction_id": 1, "flow": 1,
                  "amount_cents": 1, "application_fee_cents": 1,
                  "advertiser_id": 1, "merchant_id": 1,
                  "succeeded_at": 1}
                ).sort("succeeded_at", -1).limit(5):
            latest_payments.append({
                "transaction_id":   p.get("transaction_id"),
                "flow":             p.get("flow"),
                "amount_cents":     p.get("amount_cents"),
                "platform_cents":   p.get("application_fee_cents"),
                "advertiser_id":    p.get("advertiser_id"),
                "merchant_id":      p.get("merchant_id"),
                "succeeded_at":     p.get("succeeded_at"),
            })
    except Exception:
        pass

    # Latest 5 advertiser signups.
    latest_advertisers: List[Dict[str, Any]] = []
    try:
        async for a in db.advertisers_v2.find(
                {}, {"_id": 0, "advertiser_id": 1, "name": 1,
                      "status": 1, "created_at": 1, "market": 1}
                ).sort("created_at", -1).limit(5):
            latest_advertisers.append({
                "advertiser_id":  a.get("advertiser_id"),
                "name":           a.get("name"),
                "status":         a.get("status"),
                "market":         a.get("market"),
                "created_at":     a.get("created_at"),
            })
    except Exception:
        pass

    # System status derivation.
    system_status = "green"
    if qa_compact["open_alerts"] > 0:
        system_status = "amber"
    if qa_compact["bg_health"] == "red":
        system_status = "red"
    elif qa_compact["bg_health"] == "amber":
        system_status = "amber"

    payload = {
        "generated_at":         _now().isoformat(),
        "qa_compact":           qa_compact,
        "location_compact":     loc_compact,
        "notification_recipe_count": recipe_count,
        "recent_actions":       recent_actions,
        "latest_payments":      latest_payments,
        "latest_advertisers":  latest_advertisers,
        "system_status":        system_status,
        "cached":               False,
    }
    _HOME_CACHE["data"] = payload
    _HOME_CACHE["ts"]   = _now()
    return payload


def clear_cache() -> None:
    _HOME_CACHE["data"] = None
    _HOME_CACHE["ts"]   = None


# ─── global search ─────────────────────────────
_ESCAPE_RX = re.compile(r"([.^$*+?()\[\]{}|\\])")


def _q_regex(q: str) -> Dict[str, Any]:
    safe = _ESCAPE_RX.sub(r"\\\1", q)
    return {"$regex": safe, "$options": "i"}


async def global_search(db, q: str, limit: int = 20) -> Dict[str, Any]:
    q = (q or "").strip()
    if not q or len(q) < 2:
        return {"query": q, "users": [], "advertisers": [],
                "businesses": [], "stations": [], "campaigns": []}
    rx = _q_regex(q)
    per_bucket = min(max(limit // 5, 3), 10)

    users: List[Dict[str, Any]] = []
    async for u in db.users.find(
            {"$or": [{"name": rx}, {"email": rx}]},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1,
              "role": 1}).limit(per_bucket):
        users.append({
            "id":            u.get("user_id"),
            "type":          "user",
            "label":         u.get("name") or u.get("email") or u.get("user_id"),
            "subtitle":      u.get("email") or u.get("role") or "",
            "deep_link_path": f"/admin/users/{u.get('user_id')}",
        })

    advertisers: List[Dict[str, Any]] = []
    async for a in db.advertisers_v2.find(
            {"name": rx},
            {"_id": 0, "advertiser_id": 1, "name": 1,
              "contact_email": 1, "market": 1}).limit(per_bucket):
        advertisers.append({
            "id":            a.get("advertiser_id"),
            "type":          "advertiser",
            "label":         a.get("name"),
            "subtitle":      a.get("contact_email") or a.get("market") or "",
            "deep_link_path": f"/admin/advertisers",
        })

    # Legacy advertisers.
    async for a in db.advertisers.find(
            {"name": rx},
            {"_id": 0, "advertiser_id": 1, "name": 1,
              "contact_email": 1}).limit(per_bucket):
        aid = a.get("advertiser_id")
        if any(x["id"] == aid for x in advertisers):
            continue
        advertisers.append({
            "id":            aid,
            "type":          "advertiser",
            "label":         a.get("name"),
            "subtitle":      a.get("contact_email") or "",
            "deep_link_path": f"/admin/advertisers",
        })
        if len(advertisers) >= per_bucket:
            break

    businesses: List[Dict[str, Any]] = []
    async for b in db.businesses.find(
            {"$or": [{"name": rx}, {"business_name": rx}]},
            {"_id": 0, "business_id": 1, "name": 1, "business_name": 1,
              "city": 1, "market": 1}).limit(per_bucket):
        businesses.append({
            "id":            b.get("business_id"),
            "type":          "business",
            "label":         b.get("name") or b.get("business_name"),
            "subtitle":      f"{b.get('city') or ''} · {b.get('market') or ''}".strip(" ·"),
            "deep_link_path": f"/admin/merchants",
        })

    stations: List[Dict[str, Any]] = []
    async for s in db.imported_radio_stations.find(
            {"$or": [{"name": rx}, {"slug": rx}]},
            {"_id": 0, "id": 1, "name": 1, "slug": 1,
              "genre": 1, "market": 1}).limit(per_bucket):
        stations.append({
            "id":            s.get("id"),
            "type":          "station",
            "label":         s.get("name"),
            "subtitle":      f"{s.get('genre') or ''} · {s.get('market') or ''}".strip(" ·"),
            "deep_link_path": f"/admin/flagship-stations",
        })

    campaigns: List[Dict[str, Any]] = []
    for coll, path in (
            ("banner_campaigns",          "/admin/campaigns/queue"),
            ("coupon_campaigns",          "/admin/campaigns/queue"),
            ("notification_campaigns",   "/admin/campaigns/queue"),
            ("retargeting_campaigns",    "/admin/retargeting"),
            ("location_boost_campaigns", "/admin/location-boosts"),
            ("marketplace_featured_slots","/admin/marketplace-slots"),
            ("rj_sponsored_reads",        "/admin/rj-sponsored-reads"),
            ("takeover_hours",            "/admin/takeover-hours"),
            ("trivia_sponsorships",      "/admin/trivia-sponsorships"),
    ):
        try:
            async for c in db[coll].find(
                    {"$or": [{"display_name": rx}, {"name": rx},
                                {"title": rx}]},
                    {"_id": 0, "id": 1, "display_name": 1, "name": 1,
                      "title": 1, "status": 1,
                      "advertiser_business_id": 1,
                      "advertiser_id": 1}).limit(3):
                label = (c.get("display_name") or c.get("name")
                              or c.get("title") or c.get("id"))
                campaigns.append({
                    "id":            c.get("id"),
                    "type":          f"campaign:{coll}",
                    "label":         label,
                    "subtitle":      f"{coll} · {c.get('status') or ''} · "
                                          f"{c.get('advertiser_business_id') or c.get('advertiser_id') or ''}".strip(" ·"),
                    "deep_link_path": path,
                })
                if len(campaigns) >= per_bucket * 2:
                    break
        except Exception:
            continue
        if len(campaigns) >= per_bucket * 2:
            break

    return {
        "query":       q,
        "users":       users,
        "advertisers": advertisers,
        "businesses":  businesses,
        "stations":    stations,
        "campaigns":   campaigns,
        "total":       len(users) + len(advertisers) + len(businesses)
                        + len(stations) + len(campaigns),
    }


# ─── nav pins ─────────────────────────────────
async def list_pins(db, user_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    async for r in db.admin_nav_pins.find(
            {"user_id": user_id},
            {"_id": 0}).sort("pinned_at", 1).limit(20):
        rows.append(r)
    return rows


async def add_pin(db, *, user_id: str, route: str,
                   label: Optional[str] = None) -> Dict[str, Any]:
    if not route or not route.startswith("/admin"):
        raise ValueError("invalid_route")
    doc = {"user_id":   user_id,
            "route":     route,
            "label":     label or route.replace("/admin/", "")
                                              .replace("/", " · ").strip() or "Admin",
            "pinned_at": _now()}
    await db.admin_nav_pins.update_one(
        {"user_id": user_id, "route": route},
        {"$setOnInsert": doc}, upsert=True)
    return {"ok": True, "user_id": user_id, "route": route}


async def remove_pin(db, *, user_id: str, route: str) -> Dict[str, Any]:
    r = await db.admin_nav_pins.delete_one(
        {"user_id": user_id, "route": route})
    return {"ok": True, "deleted": int(r.deleted_count)}


__all__ = ["ensure_indexes", "home_summary", "clear_cache",
             "global_search", "list_pins", "add_pin", "remove_pin"]
