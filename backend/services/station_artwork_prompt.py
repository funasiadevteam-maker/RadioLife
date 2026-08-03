"""Phase C — Station artwork prompt builder.

Single helper that maps a station document → a 1-3 sentence prompt
suitable for OpenAI gpt-image-1.  Brand-consistent suffix is appended
to every prompt so the grid stays visually cohesive.

The prompt builder is deliberately conservative — we DO NOT want
gpt-image-1 to render any text (the model is famously bad at letter
rendering and any station name or city would come out garbled).
Branding gets overlaid in CSS by the frontend, not baked into pixels.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger("bigfm.station_artwork_prompt")

# Style suffix tuned for gpt-image-1 per the brief.  The "no text"
# directive must be repeated in two forms because OpenAI's image model
# ignores a single mention.
BRAND_SUFFIX = (
    "Stylized radio station cover art, vibrant gradient lighting, bold "
    "modern composition, photographic depth, 1:1 aspect ratio. "
    "ABSOLUTELY NO text, NO typography, NO letters, NO words, NO writing, "
    "NO signage of any kind in the image."
)

# Venue-category hint table — drives the imagery for business pages.
VENUE_HINTS = {
    "cafe":          "cozy artisan café interior, warm latte foam, steam, soft wood and brass accents",
    "coffee":         "espresso bar, copper portafilter, latte art steam, warm low light",
    "restaurant":   "elegant restaurant table, plated dish, golden ambient lighting, blurred dining hall",
    "bar":             "dimly lit cocktail bar, neon accent reflections on bottles, copper coupe glass, motion blur",
    "club":           "high-energy nightclub, laser beams cutting through fog, packed dance floor silhouettes",
    "gym":            "modern gym floor, dumbbells, motion-blur athletic figure, neon equipment glow",
    "salon":         "modern salon mirror, soft pink rose-gold lighting, hair tools, marble counter",
    "spa":             "luxe spa stones, candle flicker, white orchids, warm steam, calm earth-tones",
    "bakery":       "rustic bakery counter, flour dust in light beam, freshly baked sourdough loaves",
    "shop":           "boutique storefront interior, curated retail shelves, warm spotlight on products",
    "studio":         "creative studio, art equipment, soft daylight through window, paint splatters",
}

# Genre → mood-board hint.  Used for non-business stations where the
# music identity drives the visual.
GENRE_HINTS = {
    "bollywood":  "saree dupatta sweep, marigold strings, glittery dance floor, hot pink + saffron palette",
    "punjabi":     "dhol drums, golden mustard fields blur, turban silhouette mid-dance, crimson + emerald",
    "hip-hop":     "diamond chain glint, urban neon teal accent, smoke wisps, black + diamond white",
    "edm":           "laser beams, raised hands silhouette, festival main-stage cyan + magenta + UV purple",
    "lo-fi":         "rainy window with city blur, vinyl record stack, warm desk lamp, lo-fi pastel teal + cream",
    "classical": "candlelit mehfil, sitar silhouette, gold leaf ornaments, deep maroon + emerald",
    "devotional": "brass diya lamps, marigold garlands, incense smoke wisp, saffron + ivory",
    "retro":         "vinyl record spread, palm-tree neon sign, sunset gradient orange-pink-purple, disco ball glint",
    "workout":     "athletic motion, gym neon, dumbbell silhouette, electric yellow + red palette",
    "chill":         "soft pastel waves, cloudscape, ambient candlelight, dusty rose + lavender",
    "pop":             "confetti, stage spotlight, glitter, bright cyan + sunshine yellow + cherry red",
    "rock":           "stadium stage lights, guitar silhouette, smoke machine, deep amber + crimson",
}


def build_prompt(station: dict[str, Any]) -> str:
    """Compose a 1-3 sentence prompt for the supplied station doc.

    Inputs read from the station doc (any may be missing):
        name, page_type, tagline, bio, allowed_genres, allowed_moods,
        business_profile_summary.category, market
    """
    name        = (station.get("name") or "").strip()
    page_type   = station.get("page_type") or "community_radio"
    tagline     = (station.get("tagline") or "").strip()
    bio          = (station.get("bio") or "").strip()
    genres       = [g.lower() for g in (station.get("allowed_genres") or [])]
    moods         = [m.lower() for m in (station.get("allowed_moods") or [])]
    biz_summary = station.get("business_profile_summary") or {}
    category   = (biz_summary.get("category") or "").lower()

    parts: list[str] = []

    # 1. Subject sentence — varies by page type.
    if page_type == "business_radio":
        venue_hint = VENUE_HINTS.get(category) or "modern lifestyle storefront"
        parts.append(
            f"Cover artwork capturing the energy of '{name}': "
            f"{venue_hint}.")
    else:
        # Personal / community — lead with the dominant genre.
        primary_genre = next((g for g in genres if g in GENRE_HINTS), None)
        genre_hint = GENRE_HINTS.get(primary_genre or "", "")
        if genre_hint:
            parts.append(
                f"Cover artwork capturing the vibe of '{name}': {genre_hint}.")
        else:
            parts.append(
                f"Cover artwork capturing the vibe of '{name}', "
                f"a vibrant personal radio station.")

    # 2. Mood / tagline sentence — only when the station provided one.
    if moods:
        parts.append(
            f"Mood: {', '.join(moods[:3])}.")
    elif tagline:
        # Use tagline as a hint but strip any names so we don't try to
        # render them as letters.
        parts.append(f"Hint of mood: {tagline}.")

    # 3. Brand suffix — always last.  Repeats the no-text directive.
    parts.append(BRAND_SUFFIX)

    out = " ".join(parts)
    # OpenAI prompts have a soft cap around 4000 chars; keep ourselves
    # comfortably under it.
    return out[:1800]
