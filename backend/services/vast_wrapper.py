"""Phase 18d — VAST 4.0 XML wrapper for stored ad creatives.

Build IAB-compliant VAST 4.0 for any row in `ad_creatives`.  The wrapper
points its `<Impression>` tracking URL at our own
`/api/ads/tracking/impression?serve_id=<id>` endpoint so we close the
attribution loop when external players (e.g. 3rd-party podcasts, podcatchers,
Auto OEMs) consume our creatives via VAST.
"""
from __future__ import annotations
import os
from xml.sax.saxutils import escape as _xesc

VAST_VERSION = "4.0"


def _resolve_base_url(request_base_url: str = "") -> str:
    """Prefer VAST_BASE_URL env, fall back to FastAPI's request base, then
    a sensible preview default."""
    return (os.environ.get("VAST_BASE_URL")
                or (request_base_url.rstrip("/") if request_base_url else "")
                or "https://mobile-games-v2.preview.emergentagent.com")


def _hms(seconds: float) -> str:
    s = max(0, int(round(seconds or 0)))
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def build_vast_xml(creative: dict, *,
                              base_url: str = "",
                              serve_id: str = "",
                              advertiser_name: str = "BigFM Advertiser") -> str:
    """Render VAST 4.0 for a creative doc.  Audio + a transparent `VideoClicks`
    block (IAB still requires VideoClicks for audio ads when ClickThrough is
    available).

    Required creative fields: id (or creative_id), audio_url, duration_sec.
    Optional: title, click_url, transcript.
    """
    cid       = creative.get("id") or creative.get("creative_id") or "unknown"
    title    = creative.get("title") or "BigFM ad"
    audio   = creative.get("audio_url") or ""
    click   = creative.get("click_url") or ""
    dur      = float(creative.get("duration_sec") or 15)
    transc = (creative.get("transcript") or "")[:300]

    base = _resolve_base_url(base_url)
    audio_abs = audio if audio.startswith("http") else f"{base}{audio}"
    if not audio_abs.endswith(".mp3") and "audio" not in audio_abs:
        audio_abs = audio_abs   # leave as-is — caller may pass any container

    # Attribution loop: every Impression / Tracking event hits our endpoint.
    track = lambda evt: (f"{base}/api/ads/tracking/impression"
                                  f"?serve_id={_xesc(serve_id or cid)}&event={evt}")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<VAST version="{VAST_VERSION}">\n'
        f'  <Ad id="{_xesc(cid)}">\n'
        f'    <InLine>\n'
        f'      <AdSystem version="1.0">BigFM</AdSystem>\n'
        f'      <AdTitle><![CDATA[{title}]]></AdTitle>\n'
        f'      <Description><![CDATA[{transc}]]></Description>\n'
        f'      <Advertiser><![CDATA[{advertiser_name}]]></Advertiser>\n'
        f'      <Impression id="bigfm-imp">'
        f'<![CDATA[{track("impression")}]]></Impression>\n'
        f'      <Creatives>\n'
        f'        <Creative id="{_xesc(cid)}-c1" sequence="1">\n'
        f'          <Linear>\n'
        f'            <Duration>{_hms(dur)}</Duration>\n'
        f'            <TrackingEvents>\n'
        f'              <Tracking event="start"><![CDATA[{track("start")}]]></Tracking>\n'
        f'              <Tracking event="firstQuartile"><![CDATA[{track("firstQuartile")}]]></Tracking>\n'
        f'              <Tracking event="midpoint"><![CDATA[{track("midpoint")}]]></Tracking>\n'
        f'              <Tracking event="thirdQuartile"><![CDATA[{track("thirdQuartile")}]]></Tracking>\n'
        f'              <Tracking event="complete"><![CDATA[{track("complete")}]]></Tracking>\n'
        f'              <Tracking event="mute"><![CDATA[{track("mute")}]]></Tracking>\n'
        f'            </TrackingEvents>\n'
        f'            <VideoClicks>\n'
        f'              <ClickThrough id="bigfm-click"><![CDATA[{click or base}]]></ClickThrough>\n'
        f'            </VideoClicks>\n'
        f'            <MediaFiles>\n'
        f'              <MediaFile delivery="progressive" type="audio/mpeg" bitrate="192" width="0" height="0">\n'
        f'                <![CDATA[{audio_abs}]]>\n'
        f'              </MediaFile>\n'
        f'            </MediaFiles>\n'
        f'          </Linear>\n'
        f'        </Creative>\n'
        f'      </Creatives>\n'
        f'    </InLine>\n'
        f'  </Ad>\n'
        f'</VAST>\n'
    )
