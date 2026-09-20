"""Phase AD.12 bundle — Advertiser Weekly Performance Digest.

Every Monday 09:00 UTC (staggered), sends a per-advertiser summary
email covering the trailing 7 days across ALL ad types:
    - AD.1 advertiser_campaigns
    - AD.4 coupon_campaigns
    - AD.11 banner_campaigns
    - AD.12 notification_campaigns
    - PG.1 sponsored games (via ad_campaigns_v2 type='sponsored_game')

Includes:
    - Total spend
    - Total impressions + CTR (best-effort — impressions collated
      across payment_transactions_v2.flow types)
    - Per-ad-type spend split
    - Top 3 performing creatives by CTR
    - Recommendations (rule-based hints)

Delivery via existing `services.mailgun_client.send_email`.  Opt-out
by setting `advertisers_v2.email_opt_out_digest = true`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from services.mailgun_client import send_email, is_live as mailgun_is_live

logger = logging.getLogger("bigfm.advertiser_digest")


DIGEST_TEMPLATE_PATH = "/app/backend/templates/advertiser_weekly_digest.html"
DIGEST_SCHEDULE_UTC_HOUR = 9   # Monday 09:00 UTC


# ─── Aggregation helpers ────────────────────────────────────────
async def _spend_by_flow(db, advertiser_id: str,
                                                since: datetime, until: datetime
                                                ) -> Dict[str, int]:
    """Sum spend cents by flow.  Uses payment_transactions_v2 (AD.2 pipe)."""
    cursor = db.payment_transactions_v2.aggregate([
        {"$match": {"advertiser_id": advertiser_id,
                                "created_at": {"$gte": since, "$lt": until},
                                "status": "posted"}},
        {"$group": {"_id": "$flow",
                                "spend": {"$sum": "$amount_cents"}}},
    ])
    out: Dict[str, int] = {}
    async for row in cursor:
        out[row["_id"] or "unknown"] = int(row.get("spend") or 0)
    return out


async def _impressions_by_flow(db, advertiser_id: str,
                                                            since: datetime, until: datetime
                                                            ) -> Dict[str, int]:
    """Best-effort counts by ad type."""
    out: Dict[str, int] = {}
    # AD.11 banner
    out["banner"] = await db.banner_impressions.count_documents(
        {"advertiser_id": advertiser_id,
          "created_at": {"$gte": since, "$lt": until}})
    # AD.12 notification deliveries
    out["notification"] = await db.notification_deliveries.count_documents(
        {"advertiser_id": advertiser_id,
          "delivered_at": {"$gte": since, "$lt": until}})
    # AD.4 coupon saves
    out["coupon"] = await db.coupon_saves.count_documents(
        {"advertiser_id": advertiser_id,
          "created_at": {"$gte": since, "$lt": until}}
    ) if "coupon_saves" in await db.list_collection_names() else 0
    return out


async def _clicks_by_flow(db, advertiser_id: str,
                                                    since: datetime, until: datetime
                                                    ) -> Dict[str, int]:
    out: Dict[str, int] = {}
    out["banner"] = await db.banner_clicks.count_documents(
        {"advertiser_id": advertiser_id,
          "created_at": {"$gte": since, "$lt": until}})
    out["notification"] = await db.notification_deliveries.count_documents(
        {"advertiser_id": advertiser_id,
          "clicked_at": {"$gte": since, "$lt": until}})
    return out


async def _top_creatives(db, advertiser_id: str, limit: int = 3
                                                ) -> List[Dict[str, Any]]:
    """Rank campaigns across banner + notification by CTR (clicks/impressions)."""
    results: List[Dict[str, Any]] = []
    async for c in db.banner_campaigns.find(
                {"advertiser_id": advertiser_id,
                  "impressions_count": {"$gt": 0}}):
        imps = int(c.get("impressions_count") or 0)
        cks    = int(c.get("clicks_count") or 0)
        if not imps:
            continue
        results.append({
            "type":  "banner",
            "title": c.get("title") or "(untitled banner)",
            "impressions": imps,
            "clicks":            cks,
            "ctr_percent": round(cks / imps * 100, 3),
        })
    async for c in db.notification_campaigns.find(
                {"advertiser_id": advertiser_id,
                  "delivered_count": {"$gt": 0}}):
        d = int(c.get("delivered_count") or 0)
        ck = int(c.get("clicked_count") or 0)
        if not d:
            continue
        results.append({
            "type":  "notification",
            "title": c.get("title") or "(untitled notification)",
            "impressions": d,
            "clicks":            ck,
            "ctr_percent": round(ck / d * 100, 3),
        })
    results.sort(key=lambda x: x["ctr_percent"], reverse=True)
    return results[:limit]


async def _zone_performance(db, advertiser_id: str,
                                                        since: datetime, until: datetime
                                                        ) -> List[Dict[str, Any]]:
    """Per-zone banner impressions + clicks for the trailing window."""
    cursor = db.banner_impressions.aggregate([
        {"$match": {"advertiser_id": advertiser_id,
                                "created_at": {"$gte": since, "$lt": until}}},
        {"$group": {"_id": "$zone",
                                "impressions": {"$sum": 1},
                                "spend":              {"$sum": "$cost_cents"}}},
        {"$sort": {"impressions": -1}},
    ])
    out: List[Dict[str, Any]] = []
    async for r in cursor:
        out.append({"zone":  r["_id"] or "unknown",
                              "impressions": int(r.get("impressions") or 0),
                              "spend_cents": int(r.get("spend") or 0)})
    return out


def _recommendations(*, spend_by_flow, imps_by_flow, clicks_by_flow,
                                          top: List[Dict[str, Any]]) -> List[str]:
    tips: List[str] = []
    # Compare CTR of top creative to platform benchmark (0.6% for
    # banner, 3% for notification — chosen conservatively).
    for t in top[:1]:
        bench = 3.0 if t["type"] == "notification" else 0.6
        if t["ctr_percent"] >= bench * 1.2:
            tips.append(
                f"'{t['title']}' ({t['type']}) is beating the platform "
                f"CTR benchmark by {int(t['ctr_percent'] / bench * 100)}%. "
                f"Consider increasing its budget.")
    # Highlight underperforming spend concentrations.
    total_spend = sum(spend_by_flow.values())
    if total_spend > 0:
        for flow, v in spend_by_flow.items():
            share = v / total_spend
            if share > 0.7:
                tips.append(
                    f"{int(share*100)}% of your spend is concentrated in "
                    f"{flow}. Consider diversifying into other ad types.")
    # Notification CTR healthy check
    d = imps_by_flow.get("notification") or 0
    c = clicks_by_flow.get("notification") or 0
    if d >= 100 and (c / d) < 0.01:
        tips.append(
            "Notification CTR is below 1%. Try shortening the copy and "
            "using a stronger CTA verb.")
    return tips[:3]


def _fmt_cents(v: int) -> str:
    return f"${v/100:,.2f}"


# ─── Digest orchestration ──────────────────────────────────────
async def build_digest_payload(db, *, advertiser_id: str,
                                                                days: int = 7
                                                                ) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    adv = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id})
    if not adv:
        raise ValueError("advertiser_not_found")
    spend_by = await _spend_by_flow(db, advertiser_id, since, now)
    imps_by  = await _impressions_by_flow(db, advertiser_id, since, now)
    clks_by  = await _clicks_by_flow(db, advertiser_id, since, now)
    top          = await _top_creatives(db, advertiser_id, limit=3)
    zones      = await _zone_performance(db, advertiser_id, since, now)
    total_spend = sum(spend_by.values())
    total_imps  = sum(imps_by.values())
    total_clks  = sum(clks_by.values())
    ctr = round((total_clks / total_imps * 100), 3) if total_imps else 0.0
    tips = _recommendations(
        spend_by_flow=spend_by, imps_by_flow=imps_by,
        clicks_by_flow=clks_by, top=top)
    return {
        "advertiser_id":          advertiser_id,
        "advertiser_name":      adv.get("name") or "Advertiser",
        "window_start":            since.isoformat(),
        "window_end":                now.isoformat(),
        "days":                            days,
        "total_spend_cents":  total_spend,
        "total_spend_display": _fmt_cents(total_spend),
        "total_impressions": total_imps,
        "total_clicks":          total_clks,
        "ctr_percent":            ctr,
        "spend_by_type":        [
            {"type": k, "spend_cents": v,
              "spend_display": _fmt_cents(v)}
            for k, v in spend_by.items()
        ],
        "impressions_by_type": [
            {"type": k, "count": v}
            for k, v in imps_by.items()
        ],
        "top_creatives":        [
            {**t, "ctr_display": f"{t['ctr_percent']:.2f}%"}
            for t in top
        ],
        "zones":                        zones,
        "recommendations":  tips,
        "opt_out_url":            f"/advertiser/dashboard/profile#digest",
    }


def _render_template(payload: Dict[str, Any]) -> str:
    try:
        with open(DIGEST_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            tpl = f.read()
    except Exception as e:
        logger.warning("[digest] template read failed: %s", e)
        return f"<pre>{payload}</pre>"
    # Very lightweight replacement (no jinja dependency).
    replacements = {
        "{{advertiser_name}}":            payload["advertiser_name"],
        "{{window_start}}":                  payload["window_start"][:10],
        "{{window_end}}":                      payload["window_end"][:10],
        "{{total_spend}}":                    payload["total_spend_display"],
        "{{total_impressions}}":        f"{payload['total_impressions']:,}",
        "{{total_clicks}}":                  f"{payload['total_clicks']:,}",
        "{{ctr_percent}}":                    f"{payload['ctr_percent']:.2f}",
    }
    for k, v in replacements.items():
        tpl = tpl.replace(k, str(v))
    # Spend split
    split_rows = "".join(
        f"<tr><td style='padding:6px 12px'>{s['type']}</td>"
        f"<td style='padding:6px 12px;text-align:right'>{s['spend_display']}</td></tr>"
        for s in payload["spend_by_type"] if s["spend_cents"] > 0)
    if not split_rows:
        split_rows = "<tr><td colspan='2' style='padding:6px 12px;color:#94a3b8'>No spend in this window.</td></tr>"
    tpl = tpl.replace("{{spend_split_rows}}", split_rows)
    # Top creatives
    tc_rows = "".join(
        f"<tr><td style='padding:6px 12px'>{t['title']}</td>"
        f"<td style='padding:6px 12px'>{t['type']}</td>"
        f"<td style='padding:6px 12px;text-align:right'>{t['ctr_display']}</td></tr>"
        for t in payload["top_creatives"])
    if not tc_rows:
        tc_rows = "<tr><td colspan='3' style='padding:6px 12px;color:#94a3b8'>Not enough traffic to rank creatives yet.</td></tr>"
    tpl = tpl.replace("{{top_creatives_rows}}", tc_rows)
    # Recommendations
    tips = payload["recommendations"]
    if tips:
        tips_html = "".join(f"<li style='margin-bottom:6px'>{t}</li>"
                                                  for t in tips)
    else:
        tips_html = "<li style='color:#94a3b8'>Keep the same mix — your campaigns are performing on-benchmark.</li>"
    tpl = tpl.replace("{{recommendations_list}}", tips_html)
    return tpl


async def send_digest_for_advertiser(db, *, advertiser_id: str,
                                                                                days: int = 7,
                                                                                force: bool = False) -> Dict[str, Any]:
    """Build + send digest for one advertiser.  Records send status.
    Opt-out semantics: `email_weekly_digest` is ON by default when the
    field is missing.  Advertisers explicitly set the field to `false`
    to opt out."""
    adv = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id})
    if not adv:
        return {"ok": False, "reason": "advertiser_not_found"}
    # Default: True.  Explicit False = opted out.
    digest_on = adv.get("email_weekly_digest")
    if digest_on is None:
        digest_on = True
    if not force and not digest_on:
        return {"ok": False, "reason": "opted_out"}
    owner_uid = adv.get("owner_user_id")
    owner = await db.users.find_one({"user_id": owner_uid}) if owner_uid else None
    email = (owner or {}).get("email")
    if not email:
        return {"ok": False, "reason": "no_email"}
    payload = await build_digest_payload(
        db, advertiser_id=advertiser_id, days=days)
    html = _render_template(payload)
    subject = (f"[FUUSIC Ads] Weekly digest — {payload['advertiser_name']} "
                          f"({payload['total_spend_display']} spend last "
                          f"{days}d)")
    if not mailgun_is_live():
        # Dev mode — persist a preview row so admins can inspect the
        # rendered HTML without having Mailgun configured.
        await db.advertiser_digest_previews.insert_one({
            "advertiser_id":  advertiser_id,
            "sent_at":              datetime.now(timezone.utc),
            "html":                  html,
            "payload":            payload,
            "dev_only":          True,
        })
        return {"ok": True, "dev_only": True,
                      "preview_saved": True,
                      "subject": subject,
                      "payload": payload}
    result = send_email(email, subject, html,
                                              from_name="FUUSIC Ads",
                                              tags=["advertiser_weekly_digest"],
                                              template_vars={
                                                  "advertiser_id": advertiser_id,
                                                  "days":                    days,
                                              })
    # Record breadcrumb.
    await db.advertiser_digest_sends.insert_one({
        "advertiser_id":  advertiser_id,
        "sent_at":              datetime.now(timezone.utc),
        "email":                  email,
        "subject":            subject,
        "ok":                      result.get("ok"),
        "message_id":      result.get("message_id"),
        "error":                result.get("error"),
        "payload":            payload,
    })
    return {"ok": bool(result.get("ok")),
                  "email": email,
                  "message_id": result.get("message_id"),
                  "error": result.get("error"),
                  "payload": payload}


async def run_weekly_batch(db) -> Dict[str, Any]:
    """Iterate over active advertisers and send digests.  Opt-out is
    checked inside send_digest_for_advertiser using the
    `email_weekly_digest` field (default True)."""
    sent = failed = opted_out = 0
    async for adv in db.advertisers_v2.find(
                {"status": "active"},
                {"advertiser_id": 1, "email_weekly_digest": 1}):
        aid = adv.get("advertiser_id")
        if not aid:
            continue
        r = await send_digest_for_advertiser(db, advertiser_id=aid)
        if r.get("ok"):
            sent += 1
        elif r.get("reason") == "opted_out":
            opted_out += 1
        else:
            failed += 1
    return {"sent": sent, "opted_out": opted_out, "failed": failed}


# ─── Scheduler ──────────────────────────────────────────────────
def start_scheduler(app, db, *, poll_interval_sec: int = 3600) -> None:
    """Sleeps until the next Monday 09:00 UTC and fires `run_weekly_batch`.
    Idempotent — records `advertiser_digest_batch_runs` so we don't
    double-fire on backend restart within the same hour."""

    async def _next_monday_9_utc(now: datetime) -> float:
        # weekday(): Monday=0 .. Sunday=6
        target = now.replace(hour=DIGEST_SCHEDULE_UTC_HOUR,
                                                  minute=0, second=0, microsecond=0)
        days_ahead = (0 - now.weekday()) % 7
        if days_ahead == 0 and now.hour >= DIGEST_SCHEDULE_UTC_HOUR:
            days_ahead = 7
        target = target + timedelta(days=days_ahead)
        return max(30.0, (target - now).total_seconds())

    async def _loop():
        await asyncio.sleep(60)   # let boot cranks settle
        while True:
            try:
                now = datetime.now(timezone.utc)
                # Only fire if we haven't fired for THIS calendar week.
                since = now - timedelta(days=7)
                last = await db.advertiser_digest_batch_runs.find_one(
                    {"fired_at": {"$gte": since}})
                if (not last and now.weekday() == 0
                                and now.hour >= DIGEST_SCHEDULE_UTC_HOUR):
                    stats = await run_weekly_batch(db)
                    await db.advertiser_digest_batch_runs.insert_one({
                        "fired_at": now, "stats": stats})
                    logger.info("[digest] weekly batch fired: %s", stats)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[digest] scheduler tick failed: %s", e)
            await asyncio.sleep(poll_interval_sec)

    existing = getattr(app.state, "advertiser_digest_task", None)
    if existing and not existing.done():
        existing.cancel()
    app.state.advertiser_digest_task = asyncio.create_task(_loop())
    logger.info("[digest] scheduler started (poll=%ds)",
                              poll_interval_sec)


__all__ = [
    "build_digest_payload",
    "send_digest_for_advertiser",
    "run_weekly_batch",
    "start_scheduler",
]
