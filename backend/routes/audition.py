"""Phase 3.6 — Public audition route.

No auth required. Serves the 4 hand-picked sample segments + a landing
page so the user (or anyone) can audition Phase 3.6 voices without logging
in. Mirrors the `/api/r/<share_id>` SSR pattern for OG-friendly sharing.
"""
from __future__ import annotations

import logging
from html import escape as h
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from core.config import STORAGE_DIR
from core.ranges import range_response, public_base_url

logger = logging.getLogger("bigfm.audition")

audition_router = APIRouter(prefix="/api/audition", tags=["audition"])

# Public audition samples (no auth). Maps a stable, readable sample_key to a
# real segment_id under /app/backend/storage/segments/.
AUDITION_SAMPLES: Dict[str, dict] = {
    # ---------- Phase 3.8 v2 — Station Imaging Engine LIVE showcase (NEW) ----------
    # All three are produced via the FULL imaging pipeline: pre-roll station ID /
    # sweeper / sponsor + music bed under RJ + -14 LUFS loudness normalization.
    "phase38_morning_imaging": {
        "segment_id": "67a9ab2c-1af5-4d55-98c1-b179d11270fc",
        "title": "Morning Drive · Imaging LIVE",
        "voice_meta": "Phase 3.8 v2 · brand_id_short pre-roll + music bed under RJ + -14 LUFS",
        "channel": "bollywood_mehfil",
        "hosts": ["Aanya"],
        "format": "solo",
        "script_excerpt": "Morning Drive opener — 2.9s station ID pre-roll, bed_medium running under the RJ break, fully loudness-normalized.",
    },
    "phase38_nightlife_imaging": {
        "segment_id": "4d31e68b-2ae4-47ec-89d6-1397bee7ea52",
        "title": "DUO · Sponsor + sweeper + bed",
        "voice_meta": "Phase 3.8 v2 · DUO 2-stage rewrite + sponsor_bumper + sweeper + music bed",
        "channel": "bollywood_mehfil",
        "hosts": ["Charlie", "Aanya"],
        "format": "duo",
        "script_excerpt": "Full produced break — sponsor lead-in, sweeper transition, two-host banter over a music bed.",
    },
    "phase38_late_night_chill": {
        "segment_id": "ae3e5abb-1984-4855-a982-73e5a72ba89f",
        "title": "Late Night Chill · Bed-only LIVE",
        "voice_meta": "Phase 3.8 v2 · music bed under RJ, no pre-roll (in-cadence segment)",
        "channel": "bollywood_mehfil",
        "hosts": ["Veer"],
        "format": "solo",
        "script_excerpt": "Mid-cadence segment with bed running underneath — the polish you only notice when it's gone.",
    },
    # ---------- Phase 3.7 — Personality profile showcase ----------
    "phase37_morning_drive": {
        "segment_id": "df45af01-bbc3-42a6-9bfc-54aad96d94b5",
        "title": "Morning Drive · Aanya (Hindi-native)",
        "voice_meta": "ElevenLabs eleven_v3 · Aanya · profile=morning_drive · two-stage pipeline",
        "channel": "morning_masala",
        "hosts": ["Aanya"],
        "format": "solo",
        "script_excerpt": "Dubai, good morning! 4:00 AM ho chuki hai, aur morning ride ka scene set hai yahan Morning Masala, BigFM par! [smiles] Kaise ho guys? Weekend ka mood kaisa chal raha hai? Bahar thandi hawa hai, aur traffic jams bhi shuru hone wale hain! Toh chai, coffee ya jo bhi ho, uthao aur me…",
    },
    "phase37_lunch": {
        "segment_id": "c43ce653-e8ec-41b1-89a0-0beb8147c8cc",
        "title": "Lunch Rush · Veer (Hinglish smooth)",
        "voice_meta": "ElevenLabs eleven_v3 · Veer · profile=lunch · two-stage pipeline",
        "channel": "late_night_drive",
        "hosts": ["Veer"],
        "format": "solo",
        "script_excerpt": "[gently] Kya scene hai, doston! Aaj raat thoda chill karne ka time hai... jab chand chamakta hai aur khwabon ka safar shuru hota hai. [pause] Thodi der ke liye, hum iss kahani mein kho jaate hain — pyaar, yaadon ki khushboo, aur nayi umeed.",
    },
    "phase37_evening_drive": {
        "segment_id": "87c88189-2235-46a4-99f2-d22b817531ed",
        "title": "Evening Drive · Raghav (Hindi-native)",
        "voice_meta": "ElevenLabs eleven_v3 · Raghav · profile=evening_drive · two-stage pipeline",
        "channel": "bollywood_mehfil",
        "hosts": ["Raghav"],
        "format": "solo",
        "script_excerpt": "Kya haal hai dosto? [smiles] Raat ka 4 baje ka waqt hai, aur aaj thoda pyaar bhare lamhe churaane wale hain. [pause] Ab vibe ko thoda aur upar le jaate hain — ek khubsurat kahani aapko dil tak le jaayegi.",
    },
    "phase37_nightlife": {
        "segment_id": "4e6f3f46-38de-423c-a023-cd8198e12605",
        "title": "Nightlife · DJ Charlie (OpenAI ash)",
        "voice_meta": "OpenAI gpt-4o-mini-tts · 'ash' · profile=nightlife · two-stage pipeline",
        "channel": "party_dubai",
        "hosts": ["DJ Charlie"],
        "format": "solo",
        "script_excerpt": "Kya scene hai, Dubai! [smiles] Party Dubai ki vibe set hai. Samundar ki lehron ki tarah, raat ko thoda magical color chadhne wala hai! 4 baje ki subah hai, par party mood abhi bhi full on hai! [pause] Ab vibe ko thoda aur upar le jaate hain.",
    },
    "phase37_chill_late_night": {
        "segment_id": "525a0c12-eb5c-4097-b12e-280bae4b0f6b",
        "title": "Chill Late Night · Veer (Hinglish intimate)",
        "voice_meta": "ElevenLabs eleven_v3 · Veer · profile=chill_late_night · two-stage pipeline",
        "channel": "late_night_drive",
        "hosts": ["Veer"],
        "format": "solo",
        "script_excerpt": "[softly] Kya scene hai dosto! Late Night Drive pe aapka swagat hai BigFM par. [pause] Is suhani raat mein sab kuch thoda aur romantic hai. Aapki khushiyan aur khwab hi toh maayne rakhte hain. Toh relax ho jaao…",
    },
    "phase37_talk_news": {
        "segment_id": "ce1252ca-f641-48b3-aecb-d1fd5581cdb9",
        "title": "Talk / Retro · Kishore Da (broadcaster)",
        "voice_meta": "ElevenLabs eleven_v3 · Kishore Da · profile=talk_news · two-stage pipeline",
        "channel": "retro_lounge",
        "hosts": ["Kishore Da"],
        "format": "solo",
        "script_excerpt": "[warmly] Shubh raat, Dubai! Retro Lounge ka time hai... [pause] Raat thodi gehri ho rahi hai, aur thoda narmi zaroori hai. Aaj hum sunne wale hain ek khaas mehfil — pyaar aur yaadon se bhari.",
    },
    # ---------- Phase 3.6 — Multi-provider voice showcase ----------
    "party_charlie_solo_1": {
        "segment_id": "af247f8f-2236-4339-8501-432594ad7914",
        "title": "Party Dubai · DJ Charlie · solo open",
        "voice_meta": "OpenAI gpt-4o-mini-tts · voice 'ash' · American club DJ",
        "channel": "party_dubai",
        "hosts": ["DJ Charlie"],
        "format": "solo",
        "script_excerpt": "Yo, yo, yo! What's up, dosto?! It's your boy DJ Richard on BigFM's PARTY channel, and we're about to TURN IT UP tonight!! Whether you're cruising downtown or vibing at your favourite hangout, the PARTY is just getting started, yaar!!",
    },
    "party_charlie_solo_2": {
        "segment_id": "77e38d2d-1402-4098-a314-cdfe199af45c",
        "title": "Party Dubai · DJ Charlie · Karama after-party",
        "voice_meta": "OpenAI gpt-4o-mini-tts · voice 'ash' · American club DJ",
        "channel": "party_dubai",
        "hosts": ["DJ Charlie"],
        "format": "solo",
        "script_excerpt": "Yo, what's up, Dubai! It's your boy DJ Richard, bringing you that late-night PARTY energy! Are you READY to turn it UP?! Karama after-party is calling, and you're gonna want to bring the FIRE! Hands in the AIR — this next beat is gonna take you to the MAX!!",
    },
    "party_charlie_riya_duo": {
        "segment_id": "38a06040-c1ed-47a6-bb45-f31159680235",
        "title": "Party Dubai · Charlie × Riya · DUO rapid-fire",
        "voice_meta": "OpenAI gpt-4o-mini-tts · 'ash' + 'nova' · 6-turn Mirchi ping-pong",
        "channel": "party_dubai",
        "hosts": ["DJ Charlie", "DJ Riya"],
        "format": "duo",
        "script_excerpt": "[CHARLIE] Yaar, Riya, what a MAST night!! [RIYA] Absolutely, Charlie! Dance floor is BLAZING!! [CHARLIE] This crowd is just AMAZING, doston!! [RIYA] And the energy? It's through the ROOF!! [CHARLIE] Are you READY for the next DROP, boss?? [RIYA] Let's GOOO! BigFM mein NONSTOP!!",
    },
    "bollywood_raghav_aanya_duo": {
        "segment_id": "fbd238c4-c573-4646-9bc5-3fe88c869e0f",
        "title": "Bollywood Mehfil · Raghav × Aanya · pure Hindi duo",
        "voice_meta": "ElevenLabs eleven_v3 · native Hindi voices (Armaan + Tripti)",
        "channel": "bollywood_mehfil",
        "hosts": ["Raghav", "Aanya"],
        "format": "duo",
        "script_excerpt": "[RAGHAV] Kya scene hai, Aanya? Pichhle gaane ne toh dil jeet liya! [AANYA] Bilkul! Woh romantic vibe hai na, Dubai ki raat ko aur bhi khaas banata hai! [RAGHAV] Haan, aur yeh gaana bhi mast hone wala hai, dil ko chhoo lega! [AANYA] Sun lo yaar, pyaar ki baatein karte hue toh mazaa hi alag hai!",
    },
}


def _segment_path(segment_id: str) -> Path:
    return STORAGE_DIR / "segments" / f"{segment_id}.mp3"


@audition_router.get("/{sample_key}/audio")
async def audition_audio(sample_key: str, request: Request):
    """Public, no-auth MP3 stream with HTTP Range support.

    Returns 206 Partial Content when a Range header is present; 200 with the
    full file otherwise. Cache-busted weakly to keep new samples fresh while
    still letting browsers buffer."""
    sample = AUDITION_SAMPLES.get(sample_key)
    if not sample:
        raise HTTPException(404, f"audition sample '{sample_key}' not found")
    path = _segment_path(sample["segment_id"])
    if not path.exists():
        logger.warning(f"audition: missing segment file {path}")
        raise HTTPException(503, "sample file missing on disk — ask the admin to regenerate")
    return range_response(path, request)


def _audition_html(request: Request) -> str:
    base = public_base_url(request)
    samples_html = []
    for key, s in AUDITION_SAMPLES.items():
        audio_url = f"{base}/api/audition/{key}/audio"
        hosts = " × ".join(s["hosts"])
        fmt_pill = '<span class="pill pill-duo">DUO</span>' if s["format"] == "duo" else '<span class="pill pill-solo">SOLO</span>'
        samples_html.append(f"""
        <section class="sample" id="{h(key)}">
          <header>
            <h2>{h(s['title'])}</h2>
            <div class="meta">
              <span class="pill pill-channel">{h(s['channel'])}</span>
              {fmt_pill}
              <span class="hosts">{h(hosts)}</span>
            </div>
            <div class="voice-meta">{h(s['voice_meta'])}</div>
          </header>
          <audio controls preload="none" data-testid="audition-audio-{h(key)}">
            <source src="{audio_url}" type="audio/mpeg" />
            Your browser doesn't support HTML5 audio.
          </audio>
          <details class="script">
            <summary>Script excerpt</summary>
            <p>{h(s['script_excerpt'])}</p>
          </details>
          <div class="actions">
            <a class="btn btn-secondary" href="{audio_url}" download="{h(key)}.mp3" data-testid="audition-download-{h(key)}">
              ↓ Download MP3
            </a>
            <a class="btn btn-link" href="{audio_url}" target="_blank" rel="noopener" data-testid="audition-open-{h(key)}">
              Open in new tab ↗
            </a>
          </div>
        </section>
        """)

    og_image = f"{base}/api/og_default.png"
    og_title = "BigFM — Phase 3.6 voice audition"
    og_desc = "Four fresh AI RJ samples: American DJ duo + native Hindi mehfil duo. No login required."
    page_url = f"{base}/audition"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{h(og_title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="{h(og_desc)}" />

  <meta property="og:type" content="website" />
  <meta property="og:title" content="{h(og_title)}" />
  <meta property="og:description" content="{h(og_desc)}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:url" content="{page_url}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{h(og_title)}" />
  <meta name="twitter:description" content="{h(og_desc)}" />
  <meta name="twitter:image" content="{og_image}" />

  <style>
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 32px 20px 64px;
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background:
        radial-gradient(circle at 12% -8%, rgba(255,45,149,.16) 0%, transparent 42%),
        radial-gradient(circle at 88% 110%, rgba(0,217,255,.10) 0%, transparent 48%),
        #0a0c18;
      color: #f0f1f5;
      min-height: 100vh;
    }}
    main {{ max-width: 880px; margin: 0 auto; }}
    .header {{
      border-bottom: 1px solid rgba(255,255,255,.08);
      padding-bottom: 20px; margin-bottom: 28px;
    }}
    .brand {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px; letter-spacing: .18em; color: #ff2d95;
      text-transform: uppercase;
    }}
    h1 {{
      font-size: clamp(28px, 5vw, 44px); margin: 8px 0 12px;
      font-weight: 800; letter-spacing: -.02em; line-height: 1.1;
    }}
    .accent {{
      background: linear-gradient(120deg, #ffd700, #ffaa00);
      -webkit-background-clip: text; background-clip: text; color: transparent;
    }}
    .lede {{ color: #aab1c8; max-width: 600px; margin: 0; font-size: 15px; line-height: 1.55; }}
    .sample {{
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 16px; padding: 22px;
      margin-bottom: 18px;
      transition: border-color .15s;
    }}
    .sample:hover {{ border-color: rgba(255,255,255,.16); }}
    .sample header h2 {{
      margin: 0 0 10px; font-size: 18px; font-weight: 700; letter-spacing: -.01em;
    }}
    .meta {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }}
    .pill {{
      padding: 3px 9px; border-radius: 999px;
      font-family: 'JetBrains Mono', monospace; font-size: 10px;
      letter-spacing: .1em; text-transform: uppercase; font-weight: 700;
    }}
    .pill-channel {{ background: rgba(0,217,255,.18); color: #00d9ff; }}
    .pill-duo     {{ background: rgba(255,215,0,.2);  color: #ffd700; }}
    .pill-solo    {{ background: rgba(255,45,149,.18); color: #ff2d95; }}
    .hosts        {{ color: #dde0ee; font-weight: 600; }}
    .voice-meta {{ color: #7e85a1; font-size: 11px; margin-bottom: 14px; }}
    audio {{
      width: 100%; margin: 6px 0 14px;
      filter: invert(.85) hue-rotate(180deg);
      border-radius: 10px;
    }}
    .script {{ margin: 8px 0 14px; }}
    .script summary {{
      cursor: pointer; color: #dde0ee; font-size: 12px;
      font-family: 'JetBrains Mono', monospace; letter-spacing: .14em;
      text-transform: uppercase; padding: 8px 12px;
      background: rgba(0,0,0,.3); border-radius: 8px; user-select: none;
    }}
    .script summary:hover {{ background: rgba(0,0,0,.45); }}
    .script p {{
      margin: 12px 4px 4px; color: #aab1c8; line-height: 1.6; font-size: 13px;
    }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .btn {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 9px 14px; border-radius: 10px;
      font-size: 11px; letter-spacing: .14em; text-transform: uppercase; font-weight: 700;
      text-decoration: none; cursor: pointer; transition: all .15s;
      font-family: 'JetBrains Mono', monospace;
    }}
    .btn-secondary {{
      background: rgba(255,255,255,.06); color: #dde0ee;
      border: 1px solid rgba(255,255,255,.1);
    }}
    .btn-secondary:hover {{ background: rgba(255,255,255,.1); color: #fff; }}
    .btn-link {{ color: #00d9ff; }}
    .btn-link:hover {{ color: #5ce7ff; }}
    .foot {{
      margin-top: 32px; padding-top: 20px;
      border-top: 1px solid rgba(255,255,255,.08);
      color: #7e85a1; font-size: 11px;
      font-family: 'JetBrains Mono', monospace; letter-spacing: .14em;
      text-transform: uppercase;
      display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px;
    }}
    .foot a {{ color: #ff2d95; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <header class="header" data-testid="audition-header">
      <div class="brand">BigFM · Voice Audition</div>
      <h1>Phase 3.6 — <span class="accent">multi-provider voices</span></h1>
      <p class="lede">
        Four fresh samples comparing OpenAI <code>gpt-4o-mini-tts</code> (American DJs) with
        ElevenLabs <code>eleven_v3</code> (native Hindi). Hit play — no login needed.
      </p>
    </header>

    {''.join(samples_html)}

    <footer class="foot">
      <span>BigFM · Phase 3.6</span>
      <span><a href="/">← Back to radio</a></span>
    </footer>
  </main>
</body>
</html>"""


@audition_router.get("/__landing", response_class=HTMLResponse)
async def audition_landing_under_api(request: Request):
    # Mounted under /api so it lives next to the audio routes — but the user-
    # friendly URL is /audition (rendered via a top-level route in server.py).
    return HTMLResponse(_audition_html(request))


# Public helper used by the top-level /audition route (no /api prefix).
def render_audition_page(request: Request) -> HTMLResponse:
    return HTMLResponse(_audition_html(request))
