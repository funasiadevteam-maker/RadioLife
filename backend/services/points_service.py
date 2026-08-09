"""Phase F-1 — Unified Points Engine.

Single source of truth for every earn / spend / reversal across RadioLife.
The legacy BigCoin system in `services/bigcoin.py` continues to write
its own balance + transactions for backwards-compat — Phase F-1 *only*
mirror-writes a parallel `points_ledger` so a unified ledger exists.
Phase F-2 will flip readers over and deprecate the legacy mirror.

Currency model: 1 BigCoin == 1 Point.  No conversion math.  Naming is
purely a UX choice — the spec refers to "points unification" because
the engine is meant to absorb every future earn site without each one
inventing its own balance field.

Public SDK
==========
- ``ensure_points_indexes(db)`` — idempotent at boot.
- ``seed_earn_rules(db)`` — idempotent default rule set.
- ``PointsService(db).award(...)`` / ``spend(...)`` / ``reverse(...)``
- ``PointsService(db).get_balance(user_id)``
- ``PointsService(db).get_history(...)`` / ``get_breakdown(...)``
- ``PointsService(db).reconcile(user_id)`` — admin recompute.

Concurrency: the ledger insert is single-document atomic; balance_after
is computed by snapshotting `users.bigcoin_balance` AFTER the legacy
$inc has landed (when called as a mirror).  For direct callers (no
legacy `$inc`), `PointsService.award` performs its own atomic $inc on
`users.bigcoin_balance` so the legacy field stays in lockstep with the
ledger.  This is the "dual-write" promise: both views always agree.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger("bigfm.points")


# ───────────────────────── Default rule set ────────────────────────
# The seed is idempotent — existing rule_ids are LEFT ALONE so an admin
# can tweak caps via PATCH without the next boot reverting them.  Only
# rows that don't exist yet get inserted.
DEFAULT_RULES: list[dict] = [
    {"rule_id": "listening_minute",    "label": "Listening minute",
     "base_points": 1,   "daily_cap_per_user": 60,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "predict_win_correct", "label": "Predict & Win — correct",
     "base_points": 50,  "daily_cap_per_user": None,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "predict_win_participate", "label": "Predict & Win — participate",
     "base_points": 5,   "daily_cap_per_user": 25,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "game_win",            "label": "Game win",
     "base_points": 10,  "daily_cap_per_user": 200,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "daily_login",          "label": "Daily login bonus",
     "base_points": 5,   "daily_cap_per_user": 5,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "social_share",         "label": "Social share",
     "base_points": 5,   "daily_cap_per_user": 25,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "venue_checkin",        "label": "Venue check-in",
     "base_points": 20,  "daily_cap_per_user": 100,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "referral_signup",      "label": "Referral signup",
     "base_points": 100, "daily_cap_per_user": None,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "voucher_bonus",        "label": "Voucher bonus",
     "base_points": 25,  "daily_cap_per_user": 100,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    {"rule_id": "admin_grant",          "label": "Admin grant",
     "base_points": 0,   "daily_cap_per_user": None,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
    # Phase K.6 — Social Passport v2 unlock rewards.
    {"rule_id": "city_stamp_unlock",    "label": "City stamp earned",
     "base_points": 25,  "daily_cap_per_user": None,
     "weekly_cap_per_user": None, "monthly_cap_per_user": None},
]


# ────────────────────── Bootstrap helpers ──────────────────────────
async def ensure_points_indexes(db) -> None:
    """Idempotent — safe to call on every boot."""
    coll = db.points_ledger
    await coll.create_index([("user_id", 1), ("created_at", -1)],
                                                  name="pl_user_time")
    await coll.create_index([("user_id", 1), ("source", 1), ("created_at", -1)],
                                                  name="pl_user_source_time")
    # Idempotency key is uniquely indexed ONLY when set (string).  Sparse
    # alone doesn't cover `null`-valued rows — Mongo treats `null` as a
    # real value across docs.  A partial filter expression scopes the
    # unique constraint to rows that explicitly set the key.
    await coll.create_index(
        "idempotency_key", unique=True,
        partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="pl_idempotency_uniq",
    )
    await coll.create_index("expires_at", sparse=True, name="pl_expires_at")
    await db.points_earn_rules.create_index("rule_id", unique=True,
                                                                  name="per_rule_uniq")
    log.info("[points] indexes ensured")


async def seed_earn_rules(db) -> dict:
    """Insert any missing default rules — existing rows untouched."""
    now = datetime.now(timezone.utc)
    created = 0
    for r in DEFAULT_RULES:
        doc = {**r, "enabled": True, "updated_at": now, "created_at": now}
        res = await db.points_earn_rules.update_one(
            {"rule_id": r["rule_id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if (res.upserted_id is not None) or (res.matched_count == 0):
            created += 1
    log.info("[points] earn rules seeded: created=%d total=%d",
                      created, len(DEFAULT_RULES))
    return {"created": created, "total": len(DEFAULT_RULES)}


# ────────────────────── Result dataclass ───────────────────────────
@dataclass
class AwardResult:
    ok: bool
    entry_id: Optional[str]
    delta: int
    balance_after: Optional[int]
    capped: bool
    reason: str
    idempotency_hit: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "entry_id": self.entry_id,
            "delta": self.delta,
            "balance_after": self.balance_after,
            "capped": self.capped,
            "reason": self.reason,
            "idempotency_hit": self.idempotency_hit,
        }


# ────────────────────── PointsService ──────────────────────────────
class PointsService:
    """Per-request service handle.  Pass the active Motor DB."""

    def __init__(self, db) -> None:
        self.db = db

    # ─── Internal helpers ─────────────────────────────────────────
    async def _get_rule(self, source: str) -> Optional[dict]:
        return await self.db.points_earn_rules.find_one({"rule_id": source})

    async def _sum_window(self, user_id: str, source: str,
                                                    since: datetime) -> int:
        pipe = [
            {"$match": {"user_id": user_id, "source": source,
                                  "created_at": {"$gte": since},
                                  "delta": {"$gt": 0}}},
            {"$group": {"_id": None, "total": {"$sum": "$delta"}}},
        ]
        cur = self.db.points_ledger.aggregate(pipe)
        async for d in cur:
            return int(d.get("total") or 0)
        return 0

    async def _check_caps(self, user_id: str, source: str,
                                                  delta: int, rule: Optional[dict]) -> tuple[bool, str]:
        """Returns (allowed, reason).  `delta` is the request size."""
        if not rule:
            return True, "no_rule"
        if not rule.get("enabled", True):
            return False, "rule_disabled"
        now = datetime.now(timezone.utc)
        for window_field, seconds_back, label in [
            ("daily_cap_per_user",     86400,    "daily_cap_reached"),
            ("weekly_cap_per_user",    7 * 86400,    "weekly_cap_reached"),
            ("monthly_cap_per_user", 30 * 86400, "monthly_cap_reached"),
        ]:
            cap = rule.get(window_field)
            if not cap:
                continue
            since = now - timedelta(seconds=seconds_back)
            spent = await self._sum_window(user_id, source, since)
            if spent + delta > cap:
                return False, label
        return True, "ok"

    # ─── Public SDK ──────────────────────────────────────────────
    async def award(self, *, user_id: str, source: str,
                                  source_id: Optional[str] = None,
                                  delta: Optional[int] = None,
                                  metadata: Optional[dict] = None,
                                  idempotency_key: Optional[str] = None,
                                  enforce_caps: bool = True,
                                  mirror_only: bool = False,
                                  balance_after_override: Optional[int] = None,
                                  expires_at: Optional[datetime] = None,
                                  created_at: Optional[datetime] = None) -> AwardResult:
        """Earn entry.  `delta` defaults to the rule's `base_points`.

        Parameters
        ----------
        mirror_only:
            When True, the service ONLY writes the ledger row.  It does
            NOT touch `users.bigcoin_balance` (the caller — usually
            `services.bigcoin.award/spend/adjust` — has already done
            the legacy `$inc`).  Caps are skipped in this mode because
            the legacy callsite already gated upstream.
        enforce_caps:
            When True (default for direct callers), the earn-rules caps
            are evaluated and the write is rejected if the cap would
            be exceeded.
        balance_after_override:
            For mirror_only callers who can supply the post-`$inc`
            balance straight from the legacy update.  Saves a roundtrip.
        """
        metadata = metadata or {}
        now = created_at or datetime.now(timezone.utc)

        # Idempotency check — short-circuit on hit.
        if idempotency_key:
            existing = await self.db.points_ledger.find_one(
                {"idempotency_key": idempotency_key})
            if existing:
                return AwardResult(
                    ok=True, entry_id=str(existing.get("_id")),
                    delta=int(existing.get("delta") or 0),
                    balance_after=int(existing.get("balance_after") or 0),
                    capped=False, reason="idempotent",
                    idempotency_hit=True,
                )

        rule = await self._get_rule(source)
        if delta is None:
            if not rule:
                return AwardResult(ok=False, entry_id=None, delta=0,
                                                      balance_after=None, capped=False,
                                                      reason="unknown_source_no_delta")
            delta = int(rule.get("base_points") or 0)

        if delta == 0:
            return AwardResult(ok=False, entry_id=None, delta=0,
                                                  balance_after=None, capped=False,
                                                  reason="zero_delta")

        # Caps only for direct callers.  Mirror writes already gated.
        if enforce_caps and not mirror_only and delta > 0:
            allowed, why = await self._check_caps(user_id, source, delta, rule)
            if not allowed:
                return AwardResult(ok=False, entry_id=None, delta=0,
                                                      balance_after=None, capped=True,
                                                      reason=why)

        # Phase F-2 — Ledger Reader Flip.  PointsService.award no longer
        # mirrors to the legacy `users.bigcoin_balance` field by default.
        # The reconcile script froze legacy at the correct ledger sum;
        # readers have all flipped to PointsService.get_balance().  The
        # `bc.award/spend` legacy-side path is left untouched for callers
        # that still depend on `bigcoin_transactions` rows + the legacy
        # `$inc`, but PointsService no longer back-calls it from here.
        #
        # Set `BIGCOIN_LEGACY_DUAL_WRITE=1` (env) to temporarily restore
        # the legacy mirror — kept as an emergency rollback escape hatch.
        import os as _os
        _dual_write_legacy = (_os.environ.get(
            "BIGCOIN_LEGACY_DUAL_WRITE", "0") == "1")
        balance_after: Optional[int] = balance_after_override
        if not mirror_only and _dual_write_legacy:
            from services import bigcoin as bc
            try:
                if delta > 0:
                    bc_res = await bc.award(
                        self.db, user_id, int(delta), source,
                        metadata={**metadata, "via": "points_service"},
                        note=metadata.get("note"),
                        skip_points_mirror=True)
                    balance_after = int(bc_res.get("balance_after") or 0)
                else:
                    bc_res = await bc.spend(
                        self.db, user_id, int(-delta), source,
                        metadata={**metadata, "via": "points_service"},
                        note=metadata.get("note"),
                        skip_points_mirror=True)
                    balance_after = int(bc_res.get("balance_after") or 0)
            except ValueError as e:
                return AwardResult(ok=False, entry_id=None, delta=0,
                                                      balance_after=None, capped=False,
                                                      reason=str(e))

        # If balance_after still unknown, snapshot from the ledger sum
        # (Phase F-2 source-of-truth) instead of the legacy field.
        if balance_after is None:
            cur_balance = await self.get_balance(user_id)
            balance_after = int(cur_balance or 0) + int(delta)

        entry_id = f"ple_{uuid.uuid4().hex[:18]}"
        doc = {
            "_id": entry_id,
            "user_id": user_id,
            "source": source,
            "source_id": source_id,
            "delta": int(delta),
            "balance_after": int(balance_after),
            "metadata": metadata,
            "idempotency_key": idempotency_key,
            "created_at": now,
            "expires_at": expires_at,
        }
        try:
            await self.db.points_ledger.insert_one(doc)
        except Exception as e:
            # Duplicate idempotency_key race — retry the lookup.
            if "idempotency_key" in str(e) and idempotency_key:
                existing = await self.db.points_ledger.find_one(
                    {"idempotency_key": idempotency_key})
                if existing:
                    return AwardResult(
                        ok=True, entry_id=str(existing.get("_id")),
                        delta=int(existing.get("delta") or 0),
                        balance_after=int(existing.get("balance_after") or 0),
                        capped=False, reason="idempotent",
                        idempotency_hit=True,
                    )
            log.warning("[points] insert failed: %s", e)
            raise
        return AwardResult(ok=True, entry_id=entry_id, delta=int(delta),
                                              balance_after=int(balance_after),
                                              capped=False, reason="written")

    async def spend(self, *, user_id: str, source: str,
                                  amount: int, **kwargs) -> AwardResult:
        """Spend wrapper — passes a negative delta through `award()`.
        `amount` MUST be positive."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        return await self.award(user_id=user_id, source=source,
                                                        delta=-amount, enforce_caps=False,
                                                        **kwargs)

    async def reverse(self, *, entry_id: str, reason: str,
                                      admin_user_id: Optional[str] = None) -> AwardResult:
        """Compensating ledger row referencing the original via metadata."""
        orig = await self.db.points_ledger.find_one({"_id": entry_id})
        if not orig:
            return AwardResult(ok=False, entry_id=None, delta=0,
                                                  balance_after=None, capped=False,
                                                  reason="not_found")
        # If already reversed, short-circuit.
        already = await self.db.points_ledger.find_one(
            {"metadata.reversal_of": entry_id})
        if already:
            return AwardResult(
                ok=True, entry_id=str(already.get("_id")),
                delta=int(already.get("delta") or 0),
                balance_after=int(already.get("balance_after") or 0),
                capped=False, reason="already_reversed",
                idempotency_hit=True,
            )
        return await self.award(
            user_id=orig["user_id"],
            source="reversal",
            source_id=entry_id,
            delta=-int(orig.get("delta") or 0),
            metadata={"reversal_of": entry_id, "reason": reason,
                              "admin_user_id": admin_user_id,
                              "original_source": orig.get("source")},
            idempotency_key=f"reversal:{entry_id}",
            enforce_caps=False,
        )

    async def get_balance(self, user_id: str) -> int:
        """Sum of ledger deltas for the user (fast, indexed)."""
        pipe = [{"$match": {"user_id": user_id}},
                          {"$group": {"_id": None, "total": {"$sum": "$delta"}}}]
        async for d in self.db.points_ledger.aggregate(pipe):
            return int(d.get("total") or 0)
        return 0

    async def get_history(self, user_id: str, *, limit: int = 50,
                                                cursor: Optional[str] = None,
                                                source: Optional[str] = None) -> dict:
        q: dict = {"user_id": user_id}
        if source:
            q["source"] = source
        if cursor:
            try:
                cur_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                q["created_at"] = {"$lt": cur_dt}
            except ValueError:
                pass
        rows: list[dict] = []
        async for r in self.db.points_ledger.find(q).sort(
                                  "created_at", -1).limit(limit + 1):
            rows.append(_serialize(r))
        next_cursor = None
        if len(rows) > limit:
            next_cursor = rows[limit - 1]["created_at"]
            rows = rows[:limit]
        return {"items": rows, "next_cursor": next_cursor, "count": len(rows)}

    async def get_breakdown(self, user_id: str, *,
                                                    period: str = "all") -> dict:
        now = datetime.now(timezone.utc)
        since = None
        if period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        match: dict = {"user_id": user_id, "delta": {"$gt": 0}}
        if since:
            match["created_at"] = {"$gte": since}
        pipe = [
            {"$match": match},
            {"$group": {"_id": "$source", "total": {"$sum": "$delta"},
                                  "count": {"$sum": 1}}},
            {"$sort": {"total": -1}},
        ]
        items: list[dict] = []
        async for d in self.db.points_ledger.aggregate(pipe):
            items.append({"source": d["_id"], "total": int(d["total"]),
                                          "count": int(d["count"])})
        return {"period": period, "since": since.isoformat() if since else None,
                          "items": items}

    async def reconcile(self, user_id: str) -> dict:
        """Recompute `users.bigcoin_balance` from the ledger.  Admin-only."""
        ledger_sum = await self.get_balance(user_id)
        u = await self.db.users.find_one({"user_id": user_id},
                                                                          {"bigcoin_balance": 1, "_id": 0})
        legacy = int((u or {}).get("bigcoin_balance") or 0)
        drift = ledger_sum - legacy
        return {"user_id": user_id, "ledger_sum": ledger_sum,
                          "legacy_balance": legacy, "drift": drift}


# ────────────────────── Serialization helper ───────────────────────
def _serialize(doc: dict) -> dict:
    """Mongo doc → JSON-safe shape (ISO timestamps, str ids)."""
    out = dict(doc)
    out["_id"] = str(out.get("_id"))
    out["entry_id"] = out["_id"]
    for k in ("created_at", "expires_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out
