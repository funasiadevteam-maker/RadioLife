"""Sub-Phase E5 — Predexon read-only client.

We use Predexon ONLY for read-only market data + resolution.  The trading
API is deliberately untouched.

Auth header: `x-api-key: <PREDEXON_API_KEY>`.

Every call is logged to the `prediction_api_logs` collection (truncated
to 2KB response, NEVER the api key).  5xx errors retry 3x with
backoff (1s/2s/4s).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("bigfm.predexon")

DEFAULT_BASE = "https://api.predexon.com"
REQUEST_TIMEOUT_SEC = 12.0
MAX_RETRIES = 3
RETRY_BACKOFF_SEQUENCE = (1.0, 2.0, 4.0)
LOG_RESPONSE_TRUNCATE_BYTES = 2 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key() -> str:
    return (os.environ.get("PREDEXON_API_KEY") or "").strip()


def _base() -> str:
    return (os.environ.get("PREDEXON_BASE_URL")
                  or DEFAULT_BASE).rstrip("/")


def key_loaded() -> bool:
    """Presence check.  Never returns the actual key."""
    return bool(_key())


# ──────────────────── api-log helper ────────────────────
async def _log_api_request(
        db, *,
        provider_id: str,
        endpoint: str,
        request_params: Dict[str, Any],
        status_code: Optional[int],
        response_summary: Any,
        error_message: Optional[str],
        response_time_ms: int) -> None:
    """Insert one row into `prediction_api_logs`.    Never persists the key."""
    try:
        # Truncate response.
        summary_repr = ""
        if response_summary is not None:
            try:
                summary_repr = (
                    response_summary
                    if isinstance(response_summary, str)
                    else __import__("json").dumps(response_summary,
                                                                                default=str))
            except Exception:
                summary_repr = repr(response_summary)
        truncated = summary_repr[:LOG_RESPONSE_TRUNCATE_BYTES]
        # Strip request_params of any secret-shaped field (defensive — no
        # secrets ever flow through request_params, but be paranoid).
        safe_params: Dict[str, Any] = {}
        for k, v in (request_params or {}).items():
            if "api_key" in str(k).lower() or "secret" in str(k).lower():
                continue
            safe_params[k] = v
        doc = {
            "_id": f"plog_{uuid.uuid4().hex[:14]}",
            "provider_id": provider_id,
            "provider_name": "predexon",
            "endpoint": endpoint,
            "request_params_json": safe_params,
            "status_code": status_code,
            "response_summary_json": {"truncated": truncated,
                                                                "length": len(summary_repr)},
            "error_message": error_message,
            "response_time_ms": response_time_ms,
            "called_at": _now(),
        }
        await db.prediction_api_logs.insert_one(doc)
    except Exception as e:
        log.warning("[predexon] failed to insert api log: %s", e)


async def ensure_predexon_log_ttl(db) -> None:
    """Idempotent — adds a 30-day TTL on `prediction_api_logs.called_at`."""
    try:
        await db.prediction_api_logs.create_index(
            "called_at", expireAfterSeconds=30 * 86400,
            name="ttl_called_at_30d")
    except Exception as e:
        log.debug("[predexon] TTL index ensure (idempotent skip): %s", e)


# ──────────────────── core fetch ────────────────────
async def _resolve_provider_id(db) -> str:
    row = await db.prediction_data_providers.find_one(
        {"provider_name": "predexon"})
    if row:
        return row.get("provider_id") or row.get("_id")
    return "pdp_predexon"   # default before the seed runs.


async def _request(db, method: str, path: str, *,
                                      params: Optional[Dict[str, Any]] = None,
                                      json: Any = None) -> Dict[str, Any]:
    """Returns `{ok, status_code, body, response_time_ms, error_message}`."""
    if not key_loaded():
        return {"ok": False, "status_code": None, "body": None,
                      "response_time_ms": 0,
                      "error_message": "PREDEXON_API_KEY not loaded"}
    url = f"{_base()}{path}"
    headers = {"x-api-key": _key(), "Accept": "application/json",
                          "User-Agent": "BigFM/1.0"}
    provider_id = await _resolve_provider_id(db)

    last_status: Optional[int] = None
    last_error: Optional[str] = None
    last_body: Any = None
    response_time_ms = 0
    for attempt in range(MAX_RETRIES):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC,
                                                                          follow_redirects=True) as cli:
                r = await cli.request(method, url,
                                                              headers=headers,
                                                              params=params,
                                                              json=json)
            response_time_ms = int((time.monotonic() - start) * 1000)
            last_status = r.status_code
            try:
                last_body = r.json()
            except Exception:
                last_body = r.text[:2048]
            if r.status_code < 500:
                # Done — success OR 4xx (don't retry client errors).
                break
            last_error = f"HTTP {r.status_code}"
        except Exception as e:
            response_time_ms = int((time.monotonic() - start) * 1000)
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            log.warning("[predexon] %s %s attempt %d failed: %s",
                                  method, path, attempt + 1, last_error)
        # Backoff before retry (unless this was the last attempt).
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_BACKOFF_SEQUENCE[attempt])

    ok = (last_status is not None and 200 <= last_status < 300)
    await _log_api_request(
        db,
        provider_id=provider_id,
        endpoint=f"{method} {path}",
        request_params=params or {},
        status_code=last_status,
        response_summary=last_body if ok else (last_body or last_error),
        error_message=None if ok else last_error,
        response_time_ms=response_time_ms,
    )
    return {"ok": ok, "status_code": last_status, "body": last_body,
                  "response_time_ms": response_time_ms,
                  "error_message": last_error}


# ──────────────────── public methods ────────────────────
async def list_open_markets(db, *, category: Optional[str] = None,
                                                              limit: int = 20,
                                                              offset: int = 0) -> Dict[str, Any]:
    params: Dict[str, Any] = {"status": "open",
                                                              "limit": int(limit),
                                                              "offset": int(offset)}
    if category:
        params["category"] = category
    return await _request(db, "GET", "/v2/polymarket/markets",
                                            params=params)


async def get_market(db, external_market_id: str) -> Dict[str, Any]:
    return await _request(db, "GET",
                                            f"/v2/polymarket/markets/{external_market_id}")


async def get_market_resolution(db, external_market_id: str) -> Dict[str, Any]:
    """Returns `{ok, status_code, body}`.    `body` is None when Predexon
    returns 404 (market not yet resolved)."""
    res = await _request(db, "GET",
                                            f"/v2/polymarket/markets/{external_market_id}/resolution")
    if res["status_code"] == 404:
        return {"ok": True, "status_code": 404, "body": None,
                      "response_time_ms": res["response_time_ms"],
                      "error_message": None}
    return res


# ──────────────────── outcome mapping ────────────────────
def normalize_outcomes(raw_outcomes: Any) -> List[Dict[str, Any]]:
    """Best-effort coerce Predexon market.outcomes → uniform list.

    Predexon variants we've seen / are tolerating:
        • [{id, label}, …]
        • [{outcome_id, label}, …]
        • [{outcome_id, name}, …]
        • ["YES", "NO"] (strings)
        • [{id, ticker, name}, …]
    """
    out: List[Dict[str, Any]] = []
    if not raw_outcomes:
        return out
    for i, o in enumerate(raw_outcomes):
        if isinstance(o, str):
            out.append({"external_outcome_id": f"opt_{i+1}",
                                  "label": o})
            continue
        if not isinstance(o, dict):
            continue
        eid = (o.get("outcome_id") or o.get("id") or o.get("ticker")
                      or f"opt_{i+1}")
        label = (o.get("label") or o.get("name") or o.get("title")
                        or str(eid))
        out.append({"external_outcome_id": str(eid),
                              "label": str(label)})
    return out


def map_resolution_to_option_id(*,
                                                                          resolution_body: Dict[str, Any],
                                                                          answer_options: List[Dict[str, Any]],
                                                                          ) -> Optional[str]:
    """Given a Predexon resolution payload + our campaign's answer_options,
    return the BigFM `option_id` that matches the winning outcome (or
    None when no match).  Match priority: external_outcome_id → label
    exact (case-insensitive) → None."""
    if not resolution_body:
        return None
    winning_outcome_id = (resolution_body.get("resolved_outcome_id")
                                              or resolution_body.get("winning_outcome_id")
                                              or resolution_body.get("outcome_id"))
    winning_label = (resolution_body.get("resolved_outcome")
                                or resolution_body.get("winning_outcome")
                                or resolution_body.get("outcome_label"))
    if isinstance(winning_label, dict):
        winning_label = (winning_label.get("label")
                                          or winning_label.get("name"))
    # ID-first match.
    if winning_outcome_id:
        for opt in answer_options:
            if str(opt.get("external_outcome_id") or "") == str(winning_outcome_id):
                return opt.get("option_id")
    # Label-fallback.
    if winning_label:
        wl = str(winning_label).strip().lower()
        for opt in answer_options:
            if (opt.get("label") or "").strip().lower() == wl:
                return opt.get("option_id")
    return None
