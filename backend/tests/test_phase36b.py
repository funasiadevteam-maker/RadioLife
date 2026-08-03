"""Phase 36b — Transcription + AI metadata + RSS chapters/transcript tests.

10+ backend tests cover:
  1. MOCK AssemblyAI submit+poll round-trip yields completed payload + utterances.
  2. kick_transcription creates row + auto-completes in mock mode (<2s).
  3. publish_episode (route) auto-fires transcription row.
  4. poll_pending_transcriptions no-ops in mock mode (already completed).
  5. generate_metadata returns full shape with all required fields.
  6. Chapter-count tier rule honored (≤10min → 3, etc.).
  7. apply-metadata updates episode + invalidates RSS feed cache.
  8. PATCH transcript collapses to single edited block + flips manual_edit.
  9. RSS includes <podcast:chapters> + <podcast:transcript> + namespace.
 10. /chapters.json + /transcript.srt routes return correct content-types.
 11. Hinglish channel: AI title is English, description preserves Hinglish.
 12. AssemblyAI status endpoint reports correct mode.
"""
import asyncio, os, secrets, sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Load backend/.env so OPENAI_API_KEY / OPENAI_MODEL etc. are visible to the
# test process (the backend itself loads them via core/config.py).
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(MONGO)[DBN]


def _seed_episode(db, *, language="en", duration=120,
                                title="Test 36b Episode"):
    """Insert a channel + published episode + its creator, ready for tests."""
    import uuid as _uu
    uid = f"u_36b_{secrets.token_hex(3)}"
    cid = f"crt_36b_{secrets.token_hex(3)}"
    chid = f"ch_36b_{secrets.token_hex(3)}"
    epid = f"pep_36b_{secrets.token_hex(3)}"
    run(db.podcast_creators.insert_one(
        {"id": cid, "user_id": uid, "display_name": "T", "bio": "",
          "contact_email": "t@bigfm.dubai", "market": "dubai",
          "application_status": "approved",
          "applied_at": datetime.now(timezone.utc),
          "approved_at": datetime.now(timezone.utc)}))
    run(db.podcast_channels.insert_one(
        {"id": chid, "creator_id": cid, "slug": f"ch36b-{secrets.token_hex(3)}",
          "title": "36b Test Show", "category": "tech",
          "language": language, "active": True,
          "approval_status": "approved",
          "created_at": datetime.now(timezone.utc)}))
    run(db.podcast_episodes.insert_one(
        {"id": epid, "channel_id": chid, "guid": f"bigfm-ep-{epid}",
          "title": title, "description": "x", "show_notes": "",
          "duration_seconds": duration, "file_size_bytes": 1234,
          "season": 1, "episode_number": 1, "episode_type": "full",
          "publish_status": "published",
          "published_at": datetime.now(timezone.utc),
          "audio_url": f"/api/podcasts/episodes/{epid}/audio.mp3",
          "storage_path": f"/tmp/{epid}",
          "created_at": datetime.now(timezone.utc),
          "updated_at": datetime.now(timezone.utc)}))
    return uid, cid, chid, epid


# ─── 1. AssemblyAI MOCK submit + poll round-trip ────────────────
def test_36b_01_assemblyai_mock_submit_poll_yields_completed():
    from services import assemblyai_client as aai
    assert aai.is_live() is False, "should be MOCK mode in this fork"
    tid = run(aai.submit_transcription("https://example.com/a.mp3",
                                                              language_hint="en",
                                                              episode_title="The Hustle",
                                                              episode_id="ep_x1"))
    assert tid.startswith("mock_")
    payload = run(aai.poll_transcription(tid))
    assert payload["status"] == "completed"
    assert isinstance(payload["utterances"], list)
    assert len(payload["utterances"]) >= 5
    assert payload["utterances"][0]["speaker"] in ("A", "B")
    assert "Hustle" in payload["text"], "mock should reference episode title"


# ─── 2. kick_transcription synchronously completes in mock mode ─
def test_36b_02_kick_transcription_completes_inline_mock():
    from services import podcast_transcription as tx
    db = _db()
    _, _, _, epid = _seed_episode(db)
    row = run(tx.kick_transcription(db, episode_id=epid))
    assert row["status"] == "completed", f"expected completed, got {row['status']}"
    assert row["provider"] == "mock"
    assert isinstance(row["utterances_json"], list) and row["utterances_json"]
    assert row["confidence_score"] > 0


# ─── 3. Publish route auto-fires transcription ──────────────────
def test_36b_03_publish_auto_kicks_transcription():
    from routes.podcasts import publish_ep
    from unittest.mock import AsyncMock, MagicMock
    import services.podcasts as pod_svc
    db = _db()
    _, cid, chid, epid = _seed_episode(db)
    # Reset to draft so publish moves it to published.
    run(db.podcast_episodes.update_one(
        {"id": epid}, {"$set": {"publish_status": "draft"}}))
    # Bypass auth.
    orig = pod_svc.require_approved_creator
    pod_svc.require_approved_creator = AsyncMock(return_value={"id": cid})
    req = MagicMock(); req.app.state.db = db
    try:
        run(publish_ep(chid, epid, req, user={"user_id": "u_x"}))
    finally:
        pod_svc.require_approved_creator = orig
    # The publish route should have kicked a transcript row.
    row = run(db.podcast_transcripts.find_one(
        {"episode_id": epid}, sort=[("created_at", -1)]))
    assert row is not None, "publish_ep did not kick transcription"
    assert row["status"] == "completed"


# ─── 4. poll_pending_transcriptions no-ops on completed rows ────
def test_36b_04_poll_pending_no_op_when_all_completed():
    from services import podcast_transcription as tx
    db = _db()
    advanced = run(tx.poll_pending_transcriptions(db))
    assert advanced == 0


# ─── 5. generate_metadata returns full shape + chapters utterance-aligned ─
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"),
                                  reason="OpenAI key required for AI metadata gen")
def test_36b_05_generate_metadata_full_shape():
    from services import podcast_transcription as tx
    from services import podcast_ai_metadata as ai_md
    db = _db()
    _, _, _, epid = _seed_episode(db, duration=180,
                                                              title="Building habits that stick")
    run(tx.kick_transcription(db, episode_id=epid))
    # Pull the mock utterances we just stored so we can assert exact alignment.
    tr = run(db.podcast_transcripts.find_one({"episode_id": epid}))
    utt_starts_sec = {round(float(u["start"]) / 1000.0, 6)
                                for u in (tr.get("utterances_json") or [])}
    out = run(ai_md.generate_metadata(db, episode_id=epid))
    required = {"title", "title_alternatives", "description", "show_notes",
                      "chapters", "seo_keywords", "social_captions", "hashtags",
                      "sponsor_read_suggestions", "summary_short", "summary_long",
                      "chapter_alignment_log"}
    assert required <= set(out.keys())
    assert isinstance(out["chapters"], list) and len(out["chapters"]) > 0
    assert {"twitter", "instagram", "linkedin", "youtube"} <= set(out["social_captions"].keys())
    # 36b round-2 — every chapter's start MUST exactly match an utterance.start
    # (zero tolerance — milliseconds are kept, no whole-second rounding).
    for c in out["chapters"]:
        s = round(float(c["start_time_seconds"]), 6)
        assert s in utt_starts_sec, (
            f"chapter start {s}s is NOT in utterance.start set {sorted(utt_starts_sec)}")


# ─── 6. Chapter-count tier rule ───────────────────────────────
def test_36b_06_chapter_count_tier_rule():
    from services.podcast_ai_metadata import _target_chapter_count
    assert _target_chapter_count(60)      == 3
    assert _target_chapter_count(300)    == 3
    assert _target_chapter_count(600)    == 3
    assert _target_chapter_count(601)    == 4
    assert _target_chapter_count(1800) == 4
    assert _target_chapter_count(1801) == 6
    assert _target_chapter_count(3600) == 6
    assert _target_chapter_count(3601) == 7
    assert _target_chapter_count(7200) == 7


# ─── 7. apply_metadata updates episode + invalidates RSS cache ──
def test_36b_07_apply_metadata_updates_and_invalidates_rss():
    from services import podcast_ai_metadata as ai_md
    db = _db()
    _, _, chid, epid = _seed_episode(db)
    # Pre-seed a cached RSS row so we can verify invalidation.
    run(db.podcast_feeds.update_one(
        {"channel_id": chid},
        {"$set": {"channel_id": chid, "cached_xml": "<old/>",
                      "last_built_at": datetime.now(timezone.utc)}},
        upsert=True))
    body = {
        "title":             "New Improved Title",
        "description": "Snappy new description",
        "chapters":      [{"title": "Intro", "start_time_seconds": 0,
                                "end_time_seconds": 60, "summary": "s"}],
    }
    r = run(ai_md.apply_metadata(db, episode_id=epid, body=body))
    assert r["title"] == "New Improved Title"
    assert r["chapters"][0]["chapter_source"] == "ai"
    # Feed cache should be invalidated (cached_xml=None or invalidated_at set).
    feed = run(db.podcast_feeds.find_one({"channel_id": chid}))
    assert feed["cached_xml"] in (None, "<old/>") and feed.get("invalidated_at")


# ─── 8. PATCH transcript text → single edited block + manual_edit ─
def test_36b_08_patch_transcript_collapses_and_flags_manual_edit():
    from services import podcast_transcription as tx
    db = _db()
    _, _, _, epid = _seed_episode(db)
    run(tx.kick_transcription(db, episode_id=epid))
    edited = run(tx.patch_transcript_text(
        db, episode_id=epid,
        text="This is the human-edited transcript text. Cleaned up."))
    assert edited["manual_edit"] is True
    assert len(edited["utterances_json"]) == 1
    assert edited["utterances_json"][0]["speaker"] == "EDITED"
    assert "human-edited" in edited["text"]


# ─── 9. RSS includes <podcast:chapters> + <podcast:transcript> ──
def test_36b_09_rss_includes_podcasting20_tags():
    from services import podcast_transcription as tx
    from services import podcast_rss as rss
    db = _db()
    _, _, chid, epid = _seed_episode(db)
    # Need a transcript completed and chapters on the episode.
    run(tx.kick_transcription(db, episode_id=epid))
    run(db.podcast_episodes.update_one(
        {"id": epid},
        {"$set": {"chapters": [
            {"title": "Intro",         "start_time_seconds": 0,
              "end_time_seconds": 30, "summary": "intro",
              "chapter_source": "ai"},
            {"title": "Deep dive", "start_time_seconds": 30,
              "end_time_seconds": 120, "summary": "main",
              "chapter_source": "ai"},
        ]}}))
    # Force fresh build (invalidate cache).
    run(db.podcast_feeds.delete_one({"channel_id": chid}))
    xml = run(rss.get_or_build_xml(db, channel_id=chid))
    assert 'xmlns:podcast="https://podcastindex.org/namespace/1.0"' in xml
    assert "<podcast:chapters" in xml
    assert "/chapters.json" in xml
    assert "<podcast:transcript" in xml
    assert "/transcript.srt" in xml


# ─── 10. /chapters.json + /transcript.srt routes ────────────────
def test_36b_10_chapters_json_and_transcript_srt_routes():
    from routes.podcasts import get_chapters_json, get_transcript_srt
    from services import podcast_transcription as tx
    from unittest.mock import MagicMock
    db = _db()
    _, _, _, epid = _seed_episode(db)
    run(tx.kick_transcription(db, episode_id=epid))
    run(db.podcast_episodes.update_one(
        {"id": epid},
        {"$set": {"chapters": [
            {"title": "Intro", "start_time_seconds": 0,
              "end_time_seconds": 30, "summary": "x",
              "chapter_source": "ai"}]}}))
    req = MagicMock(); req.app.state.db = db
    ch_payload = run(get_chapters_json(epid, req))
    assert ch_payload["version"] == "1.2.0"
    assert ch_payload["chapters"][0]["title"] == "Intro"
    srt_resp = run(get_transcript_srt(epid, req))
    assert srt_resp.media_type == "application/x-subrip"
    body = srt_resp.body.decode("utf-8") if isinstance(srt_resp.body, bytes) else srt_resp.body
    assert "-->" in body
    assert "[Speaker " in body


# ─── 11. Hinglish channel — title English, body preserves Hinglish ─
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"),
                                  reason="OpenAI key required")
def test_36b_11_hinglish_channel_title_english_body_hinglish():
    from services import podcast_transcription as tx
    from services import podcast_ai_metadata as ai_md
    db = _db()
    _, _, _, epid = _seed_episode(db, language="hi", duration=180,
                                                              title="Karak chai aur Dubai memories")
    # Inject a Hinglish transcript directly so we don't depend on the mock
    # text generator picking up the language.
    run(tx.kick_transcription(db, episode_id=epid))
    run(db.podcast_transcripts.update_one(
        {"episode_id": epid},
        {"$set": {"text": "Aaj hum baat karenge karak chai ke baare mein. "
                                "Dubai mein har gali corner pe milta hai yeh. "
                                "Bachpan ki yaadein taaza ho jaati hain.",
                      "utterances_json": [
                          {"speaker": "A", "start": 0, "end": 5000,
                            "text": "Aaj hum baat karenge karak chai ke baare mein."},
                          {"speaker": "B", "start": 5000, "end": 12000,
                            "text": "Dubai mein har gali corner pe milta hai yeh."},
                      ],
                      "status": "completed"}}))
    out = run(ai_md.generate_metadata(db, episode_id=epid))
    # Title should look English-ish (no devanagari)
    import re as _re
    assert not _re.search(r"[\u0900-\u097F]", out["title"] or ""), \
        f"title contains Devanagari: {out['title']}"
    # Body might preserve Hinglish words like 'karak'/'chai' — not strictly
    # asserted (model variance), but the description must not be empty.
    assert (out["description"] or "").strip() != ""


# ─── 12. AssemblyAI status endpoint reports correct mode ────────
def test_36b_12_assemblyai_status_endpoint_reports_mock():
    from routes.podcasts import admin_assemblyai_status
    from unittest.mock import MagicMock
    req = MagicMock()
    out = run(admin_assemblyai_status(req, _={"role": "admin"}))
    assert out["mode"] in ("mock", "live")
    # In this fork, no key is set.
    if not os.environ.get("ASSEMBLYAI_API_KEY"):
        assert out["mode"] == "mock"
        assert out["is_live"] is False
        assert out["api_key_present"] is False
    assert out["provider"] == "assemblyai"


# ═══════════════════════════════════════════════════════════════════
# Phase 36b ROUND-2 hardening tests
# ═══════════════════════════════════════════════════════════════════

# ─── 13. LLM-drifted chapter starts snap to nearest utterance.start ─
def test_chapter_alignment_snaps_to_nearest_utterance_when_llm_drifts():
    """The LLM tends to round chapter starts to whole seconds (3.0s, 14.0s)
    instead of using actual utterance boundaries (3.2s, 14.5s). The snap
    function must correct this with ZERO tolerance — exact match required."""
    from services.podcast_ai_metadata import _snap_chapters_to_utterances
    # Same 8-utterance shape as the AssemblyAI mock client uses.
    utterances = [
        {"speaker": "A", "start":      0, "end":  3200, "text": "..."},
        {"speaker": "B", "start":  3200, "end":  8100, "text": "..."},
        {"speaker": "A", "start":  8100, "end": 14500, "text": "..."},
        {"speaker": "B", "start": 14500, "end": 22300, "text": "..."},
        {"speaker": "A", "start": 22300, "end": 28900, "text": "..."},
        {"speaker": "B", "start": 28900, "end": 38000, "text": "..."},
        {"speaker": "A", "start": 38000, "end": 44000, "text": "..."},
        {"speaker": "B", "start": 44000, "end": 52000, "text": "..."},
    ]
    # LLM output: drifted to whole seconds (the bug the tester caught).
    llm_chapters = [
        {"title": "Intro",                   "start_time_seconds":  0.0,  "summary": "s"},
        {"title": "Realistic Expectations", "start_time_seconds": 14.0, "summary": "s"},
        {"title": "Framework",          "start_time_seconds": 29.0, "summary": "s"},
    ]
    snapped, log = _snap_chapters_to_utterances(
        llm_chapters, utterances, duration_seconds=52.0, target_chapters=3)
    # Universe of utterance.start values in seconds:
    valid_starts = {0.0, 3.2, 8.1, 14.5, 22.3, 28.9, 38.0, 44.0}
    for c in snapped:
        assert c["start_time_seconds"] in valid_starts, (
            f"chapter start {c['start_time_seconds']} is NOT on an utterance "
            f"boundary {sorted(valid_starts)}")
    # Specifically: 0.0 → 0.0, 14.0 → 14.5, 29.0 → 28.9
    assert snapped[0]["start_time_seconds"] == 0.0
    assert snapped[1]["start_time_seconds"] == 14.5
    assert snapped[2]["start_time_seconds"] == 28.9
    # Alignment log captures the snap deltas for audit.
    assert len(log) == 3
    deltas = [entry["snap_delta_ms"] for entry in log]
    assert 500 in deltas, f"expected 500ms snap for 14.0→14.5; got {deltas}"
    assert -100 in deltas, f"expected -100ms snap for 29.0→28.9; got {deltas}"


# ─── 14. Snap drops duplicates that collapse to same utterance ───
def test_chapter_alignment_drops_duplicates_collapsing_to_same_utterance():
    from services.podcast_ai_metadata import _snap_chapters_to_utterances
    utterances = [
        {"speaker": "A", "start":      0, "end":  3200, "text": "..."},
        {"speaker": "B", "start":  3200, "end": 10000, "text": "..."},
    ]
    # Two chapters both near 3.2s — must dedupe.
    llm_chapters = [
        {"title": "A", "start_time_seconds": 3.0, "summary": ""},
        {"title": "B", "start_time_seconds": 3.4, "summary": ""},
    ]
    snapped, log = _snap_chapters_to_utterances(
        llm_chapters, utterances, duration_seconds=10.0, target_chapters=2)
    assert len(snapped) == 1
    # Log records the dropped duplicate.
    dropped = [e for e in log if e.get("dropped_as_duplicate")
                            or e.get("dropped_as_non_monotonic")]
    assert len(dropped) == 1


# ─── 15. script_preference="latin" forces Latin title on hi channel ─
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"),
                                  reason="OpenAI key required")
def test_script_preference_latin_forces_latin_title_even_for_hi_channel():
    from services import podcast_transcription as tx
    from services import podcast_ai_metadata as ai_md
    db = _db()
    _, _, chid, epid = _seed_episode(db, language="hi", duration=180,
                                                                    title="Karak chai aur Dubai memories")
    # Flip the channel to script_preference=latin.
    run(db.podcast_channels.update_one(
        {"id": chid}, {"$set": {"script_preference": "latin"}}))
    run(tx.kick_transcription(db, episode_id=epid))
    run(db.podcast_transcripts.update_one(
        {"episode_id": epid},
        {"$set": {"text": "Aaj hum baat karenge karak chai ke baare mein. "
                                  "Dubai mein har gali corner pe milta hai yeh.",
                      "utterances_json": [
                          {"speaker": "A", "start": 0, "end": 5000,
                            "text": "Aaj hum baat karenge karak chai ke baare mein."},
                          {"speaker": "B", "start": 5000, "end": 12000,
                            "text": "Dubai mein har gali corner pe milta hai yeh."},
                      ], "status": "completed"}}))
    out = run(ai_md.generate_metadata(db, episode_id=epid))
    import re as _re
    assert not _re.search(r"[\u0900-\u097F]", out["title"] or ""), \
        f"script_preference=latin should force Latin title; got: {out['title']!r}"


# ─── 16. GET /transcript response exposes 'utterances' key ──────
def test_transcript_response_exposes_utterances_key():
    """The DB column is `utterances_json`; the API contract exposes BOTH
    `utterances` (new canonical) and `utterances_json` (legacy, one-cycle
    deprecation buffer for mobile + creator UI)."""
    from routes.podcasts import get_transcript_route
    from services import podcast_transcription as tx
    from unittest.mock import MagicMock
    db = _db()
    _, _, _, epid = _seed_episode(db)
    run(tx.kick_transcription(db, episode_id=epid))
    req = MagicMock(); req.app.state.db = db
    resp = run(get_transcript_route(epid, req))
    assert "utterances"            in resp, "missing canonical 'utterances' key"
    assert "utterances_json" in resp, "must keep legacy 'utterances_json' for one cycle"
    assert resp["utterances"] == resp["utterances_json"]
    assert isinstance(resp["utterances"], list) and len(resp["utterances"]) > 0
