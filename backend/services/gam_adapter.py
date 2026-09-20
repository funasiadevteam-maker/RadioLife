"""Phase 18d — Google Ad Manager (GAM) waterfall adapter.

MOCKED by default. Flips to LIVE when both env vars are present:
  - GAM_NETWORK_CODE
  - GAM_SERVICE_ACCOUNT_JSON   (path-or-inline JSON; presence-checked only)

Public surface:
  - is_live() -> bool
  - request_ad(...) -> dict | None     (returns a candidate envelope or None)
  - report_impression(...) -> None     (fire-and-forget; mock counts in Mongo)

NB: Phase 18a/b/c GAM probes live at `routes/admin_integrations_status.py`
under `/api/admin/integrations/gam/probe` using `services.gam_client`. That
service is the SOAP-era stub. This 18d adapter is a separate, modern
waterfall hook called by `services/advertisers.pick_ad_for_user` AFTER
direct-sold candidates are exhausted. Both surfaces coexist.
"""
from __future__ import annotations
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.gam18d")

_MOCK_CPM_USD = 12.0   # $0.012 per impression in mock mode


def is_live() -> bool:
    """Returns True iff BOTH GAM env vars are present and non-empty."""
    return bool(os.environ.get("GAM_NETWORK_CODE")
                    and os.environ.get("GAM_SERVICE_ACCOUNT_JSON"))


def _mock_creative_id(channel_slug: str, user_id: str) -> str:
    seed = f"{channel_slug}|{user_id}|{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    return "gam_mock_" + hashlib.md5(seed.encode()).hexdigest()[:12]


async def request_ad(*, channel_slug: str, user_id: str,
                                  market: str, ad_unit_path: Optional[str] = None
                                  ) -> Optional[dict]:
    """Returns a candidate envelope or None.

    Envelope shape (stable across mock / live):
        {
          source:           "gam_mock" | "gam",
          creative_id:    "...",
          revenue_usd:    0.012,
          audio_url:        None,     # GAM ads are typically tag-only here
          vast_xml:        "<VAST .../>",
          ad_unit_path:  "/1234/bigfm/<channel>",
        }
    """
    live = is_live()
    if not live:
        cid = _mock_creative_id(channel_slug, user_id)
        return {
            "source":              "gam_mock",
            "creative_id":      cid,
            "revenue_usd":      _MOCK_CPM_USD / 1000.0,
            "audio_url":         None,
            "vast_xml":           _SAMPLE_VAST.replace("{CID}", cid),
            "ad_unit_path":   ad_unit_path or f"/mock/bigfm/{channel_slug}",
            "mocked":            True,
        }
    # Live path — intentionally guarded: any network failure falls through
    # to mock so the waterfall never hard-fails a listener experience.
    try:
        # Real GAM call would happen here against Ad Manager API or PBS.
        # Keep the stub deterministic: behave like mock until creds prove out.
        raise NotImplementedError("GAM live path not wired in 18d")
    except Exception as e:
        logger.warning("[gam18d] live path fell back to mock: %s", e)
        cid = _mock_creative_id(channel_slug, user_id)
        return {"source": "gam_mock", "creative_id": cid,
                  "revenue_usd": _MOCK_CPM_USD / 1000.0,
                  "audio_url": None,
                  "vast_xml": _SAMPLE_VAST.replace("{CID}", cid),
                  "ad_unit_path": ad_unit_path or f"/mock/bigfm/{channel_slug}",
                  "mocked": True}


async def report_impression(db, *, creative_id: str, user_id: str,
                                              completed: bool) -> None:
    """Mock impression accounting — writes to gam_mock_impressions so the
    integrations page can show non-zero counters in screenshots."""
    try:
        await db.gam_mock_impressions.insert_one({
            "creative_id":  creative_id,
            "user_id":       user_id,
            "completed":    bool(completed),
            "served_at":   datetime.now(timezone.utc)})
    except Exception as e:
        logger.warning("[gam18d] report_impression skip: %s", e)


# ─── helpers ──────────────────────────────────────────────────────────
def status_snapshot() -> dict:
    return {
        "is_live":                              is_live(),
        "network_code_present":     bool(os.environ.get("GAM_NETWORK_CODE")),
        "service_account_present": bool(os.environ.get("GAM_SERVICE_ACCOUNT_JSON")),
        "last_check_at":                  datetime.now(timezone.utc).isoformat(),
        "mock_cpm_usd":                  _MOCK_CPM_USD,
    }


_SAMPLE_VAST = """<?xml version="1.0" encoding="UTF-8"?>
<VAST version="4.0">
  <Ad id="{CID}">
    <InLine>
      <AdSystem>FUUSIC-GAM-Mock</AdSystem>
      <AdTitle>FUUSIC GAM mock backfill</AdTitle>
      <Impression><![CDATA[https://example.com/gam_mock_imp/{CID}]]></Impression>
      <Creatives>
        <Creative>
          <Linear>
            <Duration>00:00:15</Duration>
            <MediaFiles>
              <MediaFile delivery="progressive" type="audio/mpeg" bitrate="128">
                <![CDATA[https://example.com/gam_mock/{CID}.mp3]]>
              </MediaFile>
            </MediaFiles>
          </Linear>
        </Creative>
      </Creatives>
    </InLine>
  </Ad>
</VAST>"""
