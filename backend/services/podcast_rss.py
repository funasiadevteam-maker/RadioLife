"""Phase 36a — RSS 2.0 + iTunes-compatible feed generation.

Uses `feedgen` to build, `feedparser` to validate. The feed reflects the
channel + all published episodes. Output is cached per-channel in
`podcast_feeds.cached_xml` for 5 minutes; invalidate on publish/edit.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
from feedgen.feed import FeedGenerator

logger = logging.getLogger("bigfm.podcast_rss")

VAST_BASE_URL = os.environ.get("PODCAST_PUBLIC_BASE_URL",
                                                          "https://mobile-games-v2.preview.emergentagent.com")
FEED_CACHE_TTL_SEC = 300

# Apple's required iTunes tags for valid podcast feeds.
APPLE_REQUIRED_CHANNEL_TAGS = [
    "title", "description", "language", "link",
    "itunes_author", "itunes_category", "itunes_explicit",
    "itunes_owner",
]
SPOTIFY_REQUIRED_CHANNEL_TAGS = [
    "title", "description", "language", "link",
    "itunes_category", "itunes_explicit",
]
APPLE_REQUIRED_ITEM_TAGS = [
    "title", "guid", "enclosures", "published",
]


def _absolute_url(maybe_rel: Optional[str]) -> str:
    if not maybe_rel:
        return ""
    if maybe_rel.startswith("http://") or maybe_rel.startswith("https://"):
        return maybe_rel
    base = VAST_BASE_URL.rstrip("/")
    return f"{base}{maybe_rel if maybe_rel.startswith('/') else '/' + maybe_rel}"


def _duration_hms(seconds: Optional[float]) -> str:
    s = int(round(seconds or 0))
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def build_feed_xml(channel: dict, episodes: list, *,
                              creator: Optional[dict] = None,
                              completed_transcript_ep_ids: Optional[set] = None) -> str:
    completed_transcript_ep_ids = completed_transcript_ep_ids or set()
    fg = FeedGenerator()
    fg.load_extension("podcast")
    title  = channel.get("title") or "FUUSIC Podcast"
    desc   = channel.get("description") or ""
    lang  = (channel.get("language") or "en")[:8]
    slug   = channel.get("slug") or channel.get("id")
    link   = _absolute_url(f"/podcasts/{slug}")
    feed_link = _absolute_url(f"/podcasts/{slug}/rss.xml")

    fg.id(feed_link)
    fg.title(title)
    fg.description(desc or title)
    fg.language(lang)
    fg.link(href=link, rel="alternate")
    fg.link(href=feed_link, rel="self")
    fg.copyright(f"© {datetime.now(timezone.utc).year} FUUSIC")
    # Cover image.
    cover = _absolute_url(channel.get("cover_image_url") or
                                          "/static/bigfm-default-cover.png")
    fg.image(url=cover, title=title, link=link)
    fg.logo(cover)
    # iTunes channel-level tags.
    pod = fg.podcast
    pod.itunes_category(_category_apple(channel.get("category")))
    pod.itunes_explicit("yes" if channel.get("explicit_flag") else "no")
    pod.itunes_author((creator or {}).get("display_name") or "FUUSIC Creator")
    pod.itunes_owner(name=(creator or {}).get("display_name") or "FUUSIC Creator",
                                email=(creator or {}).get("contact_email")
                                              or "podcasts@bigfm.dubai")
    pod.itunes_image(cover)
    pod.itunes_summary(desc or title)
    # Optional: new-feed-url for migrations.
    redirect = channel.get("new_feed_url")
    if redirect:
        pod.itunes_new_feed_url(redirect)

    # Episodes (newest first per RSS convention).
    for ep in sorted(episodes,
                              key=lambda e: e.get("published_at") or datetime(1970,1,1, tzinfo=timezone.utc),
                              reverse=True):
        fe = fg.add_entry()
        fe.id(ep.get("guid") or f"bigfm-ep-{ep['id']}")
        fe.title(ep.get("title") or "Untitled")
        fe.description(ep.get("description") or "")
        # Permalink + enclosure (audio file).
        audio = (ep.get("audio_url_external")
                      or _absolute_url(ep.get("audio_url")
                                                or f"/api/podcasts/episodes/{ep['id']}/audio.mp3"))
        fe.enclosure(audio, str(ep.get("file_size_bytes") or 0),
                              "audio/mpeg")
        pubd = ep.get("published_at") or ep.get("created_at") or datetime.now(timezone.utc)
        if pubd.tzinfo is None:
            pubd = pubd.replace(tzinfo=timezone.utc)
        fe.pubDate(pubd)
        fe.link(href=_absolute_url(f"/podcasts/{slug}/{ep['id']}"))
        epod = fe.podcast
        epod.itunes_duration(_duration_hms(ep.get("duration_seconds")))
        epod.itunes_season(int(ep.get("season") or 1))
        if ep.get("episode_number"):
            epod.itunes_episode(int(ep["episode_number"]))
        epod.itunes_episode_type(ep.get("episode_type") or "full")
        epod.itunes_explicit("yes" if ep.get("explicit_flag") else "no")
        if ep.get("cover_image_url"):
            epod.itunes_image(_absolute_url(ep["cover_image_url"]))

    return _inject_podcasting20_tags(fg.rss_str(pretty=True).decode("utf-8"),
                                                                episodes=episodes,
                                                                completed_transcript_ep_ids=completed_transcript_ep_ids,
                                                                channel=channel)


def _build_value_block(value_config: dict, indent: str = "    ") -> str:
    """Phase 36d Lightning splits — render a single <podcast:value> block."""
    if not value_config or not value_config.get("enabled"): return ""
    splits = value_config.get("splits") or value_config.get("default_splits") or []
    if not splits: return ""
    method = value_config.get("method", "keysend")
    suggested = value_config.get("suggested")
    s_attr = f' suggested="{suggested}"' if suggested is not None else ""
    out = [
        f'{indent}<podcast:value type="lightning" method="{method}"{s_attr}>'
    ]
    for r in splits:
        nm = (r.get("name") or "").replace('"', "'")
        addr = (r.get("address") or "").replace('"', "'")
        typ = r.get("type") or "node"
        sp = int(r.get("split") or 0)
        fee_attr = ' fee="true"' if r.get("fee") else ""
        out.append(
            f'{indent}    <podcast:valueRecipient name="{nm}" '
            f'type="{typ}" address="{addr}" split="{sp}"{fee_attr}/>')
    out.append(f'{indent}</podcast:value>')
    return "\n".join(out)


def _inject_podcasting20_tags(xml: str, *, episodes: list,
                                                          completed_transcript_ep_ids: set,
                                                          channel: Optional[dict] = None) -> str:
    """Phase 36b — Inject `xmlns:podcast` namespace and per-item
    `<podcast:chapters>` + `<podcast:transcript>` tags. feedgen 0.9 has
    no built-in podcasting-2.0 extension, so we do this as a careful
    string post-process. Idempotent."""
    NS = ' xmlns:podcast="https://podcastindex.org/namespace/1.0"'
    if NS not in xml:
        # First `<rss ...>` opening tag — splice the namespace in.
        xml = xml.replace("<rss ", "<rss" + NS + " ", 1)
    base = VAST_BASE_URL.rstrip("/")
    # Build {ep_id: extra_xml} map.
    extras: dict = {}
    for ep in episodes:
        eid = ep.get("id") or ""
        if not eid: continue
        extra: list = []
        if ep.get("chapters"):
            extra.append(
                f'    <podcast:chapters url="{base}/api/podcasts/episodes/'
                f'{eid}/chapters.json" type="application/json+chapters"/>'
            )
        if eid in completed_transcript_ep_ids:
            extra.append(
                f'    <podcast:transcript url="{base}/api/podcasts/episodes/'
                f'{eid}/transcript.srt" type="application/srt" language="en"/>'
            )
        # Phase 36c Stage 3 — supplemental video enclosure for episodes
        # that finalized with a video grid mix. Apple Podcasts 2.0 spec.
        if ep.get("video_url"):
            # Phase 36c Stage 4 — `length` must be the REAL byte size for
            # download-progress estimates. Stored on the episode at
            # finalize time as `file_size_bytes_video`; backfilled to
            # Tigris HEAD when missing.
            video_size = int(ep.get("file_size_bytes_video") or 0)
            if video_size == 0:
                try:
                    from services import object_storage as _obs
                    sid = ep.get("recording_session_id")
                    key = (ep.get("storage_key_video") or
                                (_obs.key_recording_mixed_video(sid) if sid else None))
                    if key:
                        h = _obs.get_storage().head(key=key)
                        if h: video_size = int(h.get("size") or 0)
                except Exception: pass
            extra.append(
                f'    <podcast:alternateEnclosure type="video/mp4" '
                f'length="{video_size}" default="false" title="Video">\n'
                f'      <podcast:source uri="{base}/api/podcasts/episodes/'
                f'{eid}/video.mp4" contentType="video/mp4"/>\n'
                f'    </podcast:alternateEnclosure>'
            )
        # Phase 36d Lightning splits — episode-level <podcast:value> override.
        ep_value = ep.get("value_config")
        if ep_value and ep_value.get("enabled"):
            v_block = _build_value_block(ep_value, indent="    ")
            if v_block: extra.append(v_block)
        if extra:
            extras[eid] = "\n".join(extra)
    if not extras:
        out_xml = xml
    else:
        # Anchor: each `<item>...</item>` block contains the episode's guid.
        # Insert the new tags just before `</item>` of the matching block.
        import re as _re
        def _patch(m):
            block = m.group(0)
            for eid, extra in extras.items():
                if f"bigfm-ep-{eid}" in block or f">{eid}<" in block:
                    return block.replace("</item>", extra + "\n</item>", 1)
            return block
        out_xml = _re.sub(r"<item>[\s\S]*?</item>", _patch, xml)
    # Phase 36d Lightning splits — channel-level <podcast:value> block.
    if channel and channel.get("value_config", {}).get("enabled"):
        ch_block = _build_value_block(channel["value_config"], indent="    ")
        if ch_block and "<podcast:value " not in out_xml.split("<item>", 1)[0]:
            # Insert right before the first <item> (channel scope).
            out_xml = out_xml.replace("<item>", ch_block + "\n    <item>", 1)
    return out_xml


_APPLE_CAT = {
    "business":              "Business",
    "food_local":          "Leisure",
    "movies_culture":  "TV & Film",
    "real_estate":          "Business",
    "health_wellness": "Health & Fitness",
    "legal_finance":     "Business",
    "events_community": "Society & Culture",
    "news_commentary": "News",
    "comedy":                "Comedy",
    "true_crime":          "True Crime",
    "devotional":          "Religion & Spirituality",
    "sports":                  "Sports",
    "tech":                      "Technology",
    "education":            "Education",
    "other":                    "Society & Culture",
}


def _category_apple(cat: Optional[str]) -> str:
    return _APPLE_CAT.get((cat or "other"), "Society & Culture")


def validate_feed(xml_str: str) -> dict:
    """Parses with feedparser, checks Apple+Spotify required-tag checklists.
    For iTunes-namespaced tags whose feedparser normalization varies across
    versions, we additionally inspect the raw XML for the canonical
    `itunes:<tag>` substring.

    Returns {valid, apple_compliant, spotify_compliant, errors, warnings,
    item_count}."""
    errors:    list = []
    warnings: list = []
    parsed = feedparser.parse(xml_str)
    if parsed.bozo and parsed.bozo_exception:
        errors.append({"tag": "_parse",
                            "message": str(parsed.bozo_exception)})
    feed = parsed.feed or {}
    entries = parsed.entries or []
    raw = xml_str or ""

    def has(d: dict, key: str) -> bool:
        # iTunes-namespaced channel tags: use the raw XML as the
        # authoritative source — feedparser keys differ across versions.
        if key.startswith("itunes_"):
            tag = key.replace("itunes_", "")
            return f"itunes:{tag}" in raw
        return bool(d.get(key))

    apple_missing = [t for t in APPLE_REQUIRED_CHANNEL_TAGS if not has(feed, t)]
    spotify_missing = [t for t in SPOTIFY_REQUIRED_CHANNEL_TAGS if not has(feed, t)]
    for t in apple_missing:
        errors.append({"tag": t, "message": f"Apple-required tag missing: {t}"})
    if not entries:
        errors.append({"tag": "items", "message": "Feed has zero episodes"})

    for i, e in enumerate(entries, start=1):
        for t in APPLE_REQUIRED_ITEM_TAGS:
            if t == "enclosures":
                if not e.get("enclosures"):
                    errors.append({"tag": f"item[{i}].enclosure",
                                          "message": "missing audio enclosure"})
                continue
            if not e.get(t):
                errors.append({"tag": f"item[{i}].{t}",
                                      "message": f"item missing {t}"})

    return {
        "valid":                       len(errors) == 0,
        "apple_compliant":     len(apple_missing) == 0 and bool(entries),
        "spotify_compliant": len(spotify_missing) == 0 and bool(entries),
        "errors":                    errors,
        "warnings":              warnings,
        "item_count":           len(entries),
    }


async def get_or_build_xml(db, *, channel_id: str) -> str:
    """Returns the cached XML for a channel, rebuilding it if stale."""
    cached = await db.podcast_feeds.find_one({"channel_id": channel_id})
    now = datetime.now(timezone.utc)
    if cached and cached.get("cached_xml") and cached.get("last_built_at"):
        built = cached["last_built_at"]
        if built.tzinfo is None: built = built.replace(tzinfo=timezone.utc)
        if (now - built).total_seconds() < FEED_CACHE_TTL_SEC:
            return cached["cached_xml"]

    channel = await db.podcast_channels.find_one({"id": channel_id})
    if not channel:
        return _empty_feed_xml()
    creator = await db.podcast_creators.find_one({"id": channel["creator_id"]}) \
        if channel.get("creator_id") else None
    eps = await db.podcast_episodes.find(
        {"channel_id": channel_id, "publish_status": "published"},
        {"_id": 0}).to_list(500)
    # Phase 36d Turn 3 — overlay Lightning splits from the dedicated
    # `podcast_lightning_splits` collection onto channel + episodes.
    # Idempotent and safe when no rows exist.
    try:
        from services import podcast_lightning as _pl  # local import to avoid cycles
        await _pl.overlay_rss_value_configs(db, channel=channel, episodes=eps)
    except Exception as _e:
        logger.warning(f"lightning splits overlay skipped: {_e}")
    # Phase 36b — pull which episodes have completed transcripts so the
    # RSS picks up <podcast:transcript>.
    completed_tx_ids: set = set()
    async for r in db.podcast_transcripts.find(
            {"channel_id": channel_id, "status": "completed"},
            {"episode_id": 1, "_id": 0}):
        completed_tx_ids.add(r["episode_id"])
    xml = build_feed_xml(channel, eps, creator=creator,
                                          completed_transcript_ep_ids=completed_tx_ids)
    await db.podcast_feeds.update_one(
        {"channel_id": channel_id},
        {"$set": {"cached_xml": xml, "last_built_at": now,
                      "channel_id": channel_id}},
        upsert=True)
    return xml


def _empty_feed_xml() -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<rss version="2.0"><channel><title>FUUSIC</title>'
              '<description>not found</description><link>'
              + VAST_BASE_URL + '</link></channel></rss>')
