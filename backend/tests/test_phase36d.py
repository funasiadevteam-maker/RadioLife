"""Phase 36d — Magic clips + shoppable action cards + Lightning splits.

Plus 2 tester-ergonomics tests from Part A (mock LiveKit token base64 claims).
"""
from __future__ import annotations
import asyncio, base64, json, os, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
except Exception: pass

from services import object_storage as obs                # noqa: E402

TIGRIS_LIVE = (os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris"


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


# ─── A1. Mock LiveKit token carries decodable claims ────────────
def test_36d_A1_mock_livekit_token_decodes_to_claims():
    from services import livekit_client as lk
    assert lk.is_live() is False
    t = lk.mint_room_token(room_name="bigfm-test", identity="host-x",
                                                    role="host",
                                                    permissions={"can_publish_video": True,
                                                                              "can_publish_screen": True})
    assert t.startswith("mock_lk_")
    suffix = t[len("mock_lk_"):]
    pad = "=" * (-len(suffix) % 4)
    claims = json.loads(base64.urlsafe_b64decode(suffix + pad))
    assert claims["room"] == "bigfm-test"
    assert claims["identity"] == "host-x"
    assert claims["role"] == "host"
    assert claims["can_publish_video"] is True
    assert claims["can_publish_screen"] is True
    # And the opposite path: defaults are False.
    t2 = lk.mint_room_token(room_name="r2", identity="g1", role="guest")
    suffix = t2[len("mock_lk_"):]; pad = "=" * (-len(suffix) % 4)
    c2 = json.loads(base64.urlsafe_b64decode(suffix + pad))
    assert c2["can_publish_video"] is False
    assert c2["can_publish_screen"] is False


# ─── 2. detect_top_moments snaps to utterance boundaries ─────────
def test_36d_02_detect_top_moments_snaps_to_utterance_bounds():
    from services import podcast_clips as pc
    db = _db()
    ep_id = f"pep_clips_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": "ch_x", "duration_seconds": 180,
            "title": "clip src", "publish_status": "published"}))
        # 6 utterances; the 3 long ones with questions should win.
        utterances = []
        for i, (s, e, text) in enumerate([
            (0, 5, "Hello and welcome."),
            (5, 10, "Today we explore something interesting."),
            (10, 50, "Why is the sky blue? Why does it darken at night? "
                          "What about clouds making sunsets red? These are all "
                          "questions worth exploring deeply with our guest."),
            (50, 55, "Hmm right."),
            (55, 110, "Let me tell you a long story about the most amazing "
                            "experience I had visiting that big telescope. The wind "
                            "was howling, the stars were sharp, every detail came "
                            "into focus, and I realized something profound that night."),
            (110, 180, "What if we considered that? Would your view change? "
                              "Many listeners may disagree, but let's explore the why "
                              "behind that argument and trace through the logic.")
        ]):
            utterances.append({"start_seconds": s, "end_seconds": e,
                                              "text": text})
        run(db.podcast_transcripts.insert_one({
            "episode_id": ep_id, "status": "completed",
            "utterances": utterances}))
        windows = run(pc.detect_top_moments(db, episode_id=ep_id, count=3))
        assert len(windows) == 3
        # Each window must start at an utterance start time.
        starts = {u["start_seconds"] for u in utterances}
        for w in windows:
            assert w["start_seconds"] in starts, (
                f"clip start {w['start_seconds']} not on utterance boundary")
            assert w["end_seconds"] - w["start_seconds"] >= 5
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        run(db.podcast_transcripts.delete_one({"episode_id": ep_id}))


# ─── 3. Action card CRUD + listener time-filter ─────────────────
def test_36d_03_action_card_crud_and_listener_filter():
    from services import podcast_action_cards as ac
    db = _db()
    ep_id = f"pep_ac_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": "ch_ac", "title": "ac"}))
        card = run(ac.create_card(db, episode_id=ep_id,
                                                              creator_id="u_ac",
                                                              body={"card_type": "save_coupon",
                                                                          "title": "20 % off karak",
                                                                          "description": "Tap to save",
                                                                          "start_time_seconds": 30,
                                                                          "end_time_seconds": 60,
                                                                          "offer_id": "ofr_qa_onetime_demo",
                                                                          "destination_url": "https://bigfm.dubai/o"}))
        assert card["id"].startswith("pac_")
        # Active window — 45s is inside [30, 60].
        actives = run(ac.list_active_cards_at_time(
            db, episode_id=ep_id, current_seconds=45))
        assert len(actives) == 1 and actives[0]["id"] == card["id"]
        # Out of window — 65s is past end.
        empty = run(ac.list_active_cards_at_time(
            db, episode_id=ep_id, current_seconds=65))
        assert empty == []
        # Patch — flip inactive.
        upd = run(ac.patch_card(db, card_id=card["id"], episode_id=ep_id,
                                                          creator_id="u_ac",
                                                          body={"active": False}))
        assert upd["active"] is False
        # Now even inside window, listener fetch should be empty.
        actives2 = run(ac.list_active_cards_at_time(
            db, episode_id=ep_id, current_seconds=45))
        assert actives2 == []
    finally:
        run(db.podcast_action_cards.delete_many({"episode_id": ep_id}))
        run(db.podcast_episodes.delete_one({"id": ep_id}))


# ─── 4. Save-offer via action card stamps attribution ────────────
def test_36d_04_save_offer_via_card_stamps_attribution():
    from services import podcast_action_cards as ac
    db = _db()
    ep_id = f"pep_attr_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": "ch_attr", "title": "x"}))
        card = run(ac.create_card(db, episode_id=ep_id,
                                                              creator_id="u_attr",
                                                              body={"card_type": "save_coupon",
                                                                          "title": "T", "description": "D",
                                                                          "start_time_seconds": 0,
                                                                          "end_time_seconds": 30,
                                                                          "offer_id": "ofr_qa_onetime_demo"}))
        saved = run(ac.save_offer_via_card(
            db, card_id=card["id"], user_id="u_listener"))
        assert saved["attribution_source"] == "podcast_action_card"
        assert saved["attribution_card_id"] == card["id"]
        assert saved["attribution_episode_id"] == ep_id
        assert saved["offer_id"] == "ofr_qa_onetime_demo"
    finally:
        run(db.saved_offers.delete_many(
            {"attribution_episode_id": ep_id}))
        run(db.podcast_action_cards.delete_many({"episode_id": ep_id}))
        run(db.podcast_episodes.delete_one({"id": ep_id}))


# ─── 5. RSS channel-level <podcast:value> emits when enabled ────
def test_36d_05_rss_channel_value_emits_when_enabled():
    from services import podcast_rss as rss
    db = _db()
    ch_id = f"ch_v_{uuid.uuid4().hex[:6]}"
    ep_id = f"pep_v_{uuid.uuid4().hex[:6]}"
    try:
        run(db.podcast_channels.insert_one({
            "id": ch_id, "creator_id": "u", "show_title": "V",
            "show_description": "v", "author_name": "a",
            "show_artwork_url": "https://x/x.png",
            "category_primary": "Technology", "language": "en-us",
            "explicit": False, "compliance_state": "approved",
            "rss_enabled": True,
            "value_config": {
                "enabled": True, "method": "keysend", "suggested": "0.00000005",
                "splits": [
                    {"name": "Host", "type": "node",
                      "address": "0288abc1234567890abcdef", "split": 90},
                    {"name": "Platform", "type": "node",
                      "address": "0388def0987654321fedcba", "split": 10,
                      "fee": True}]}}))
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id, "guid": f"bigfm-ep-{ep_id}",
            "title": "V ep", "description": "v",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "file_size_bytes": 50_000, "duration_seconds": 1.5,
            "publish_status": "published", "publish_state": "published",
            "season": 1, "episode_number": 1, "episode_type": "full",
            "created_at": datetime.now(timezone.utc),
            "published_at": datetime.now(timezone.utc)}))
        xml = run(rss.get_or_build_xml(db, channel_id=ch_id))
        assert '<podcast:value type="lightning"' in xml
        assert 'method="keysend"' in xml
        assert 'split="90"' in xml
        assert 'fee="true"' in xml
        assert 'address="0288abc1234567890abcdef"' in xml
        # Channel-level block lives BEFORE the first <item>.
        item_at = xml.find("<item>")
        value_at = xml.find("<podcast:value ")
        assert value_at < item_at, "channel-level value must precede <item>"
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        run(db.podcast_channels.delete_one({"id": ch_id}))


# ─── 6. RSS episode-level value override emits inside <item> ────
def test_36d_06_rss_episode_value_override_inside_item():
    from services import podcast_rss as rss
    db = _db()
    ch_id = f"ch_vo_{uuid.uuid4().hex[:6]}"
    ep_id = f"pep_vo_{uuid.uuid4().hex[:6]}"
    try:
        run(db.podcast_channels.insert_one({
            "id": ch_id, "creator_id": "u", "show_title": "VO",
            "show_description": "v", "author_name": "a",
            "show_artwork_url": "https://x/x.png",
            "category_primary": "Technology", "language": "en-us",
            "explicit": False, "compliance_state": "approved",
            "rss_enabled": True}))
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id, "guid": f"bigfm-ep-{ep_id}",
            "title": "VO ep", "description": "vo",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "file_size_bytes": 50_000, "duration_seconds": 1.5,
            "publish_status": "published", "publish_state": "published",
            "season": 1, "episode_number": 1, "episode_type": "full",
            "value_config": {
                "enabled": True, "method": "keysend",
                "splits": [
                    {"name": "Guest", "type": "node",
                      "address": "0499fff1234guestnode", "split": 100}]},
            "created_at": datetime.now(timezone.utc),
            "published_at": datetime.now(timezone.utc)}))
        xml = run(rss.get_or_build_xml(db, channel_id=ch_id))
        # The episode-level value must land INSIDE the <item> block.
        item_start = xml.find("<item>")
        item_end = xml.find("</item>", item_start)
        block = xml[item_start:item_end]
        assert '<podcast:value type="lightning"' in block
        assert '0499fff1234guestnode' in block
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        run(db.podcast_channels.delete_one({"id": ch_id}))


# ─── 7. Clip card_type validation rejects unknown values ────────
def test_36d_07_action_card_rejects_unknown_card_type():
    from services import podcast_action_cards as ac
    db = _db()
    ep_id = f"pep_acv_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": "ch", "title": "x"}))
        with pytest.raises(ValueError):
            run(ac.create_card(db, episode_id=ep_id, creator_id="u",
                                                  body={"card_type": "nuke_world",
                                                              "start_time_seconds": 0,
                                                              "end_time_seconds": 10}))
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))


# ─── 8. Channel value-config patch round-trips ───────────────────
def test_36d_08_channel_value_config_patch_endpoint():
    import requests
    base = os.environ.get("PUBLIC_BACKEND_URL")
    if not base: pytest.skip("PUBLIC_BACKEND_URL not set")
    db = _db()
    # Bootstrap creator + channel.
    r = requests.post(f"{base}/api/auth/login",
                                          json={"email": "admin@bigfm.dubai",
                                                      "password": "AdminPass123!"}, timeout=10)
    tok = r.json()["session_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    chs = requests.get(
        f"{base}/api/podcasts/creators/me", headers=headers, timeout=10).json()
    cid = chs.get("id")
    creator_channels = requests.get(
        f"{base}/api/podcasts/creators/{cid}/channels",
        headers=headers, timeout=10).json()
    if not creator_channels: pytest.skip("no channel for admin creator")
    ch_id = creator_channels[0]["id"]
    body = {
        "enabled": True, "method": "keysend", "suggested": "0.0000001",
        "splits": [
            {"name": "Host", "type": "node",
              "address": "0288host1234567890abcdef", "split": 80},
            {"name": "Platform", "type": "node",
              "address": "0388plat0987654321fedcba", "split": 20,
              "fee": True}]}
    pr = requests.patch(
        f"{base}/api/podcasts/channels/{ch_id}/value-config",
        json=body, headers=headers, timeout=10)
    assert pr.status_code == 200, pr.text
    vc = pr.json().get("value_config") or {}
    assert vc.get("enabled") is True
    assert vc.get("method") == "keysend"
    assert len(vc.get("splits", [])) == 2
    # Cleanup — disable.
    requests.patch(
        f"{base}/api/podcasts/channels/{ch_id}/value-config",
        json={"enabled": False, "splits": []},
        headers=headers, timeout=10)


# ─── 9. Magic clip generate end-to-end (requires Tigris) ─────────
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36d_09_generate_clips_end_to_end():
    from services import podcast_clips as pc
    db = _db()
    ep_id = f"pep_clipgen_{uuid.uuid4().hex[:8]}"
    ch_id = "ch_clipgen"
    src_key = f"podcasts/recordings/{ep_id}/mixed.mp3"
    try:
        # Plant a real ~30s mp3 on Tigris.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                  "-i", "sine=frequency=440:duration=35",
                  "-codec:a", "libmp3lame", "-b:a", "128k", str(src)],
                check=True, capture_output=True, timeout=30)
            obs.TigrisStorage().upload(
                local_path=str(src), key=src_key, content_type="audio/mpeg")
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id, "title": "clipgen src",
            "duration_seconds": 35, "publish_status": "published",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "storage_key_audio": src_key,
            "recording_session_id": ep_id}))
        run(db.podcast_transcripts.insert_one({
            "episode_id": ep_id, "status": "completed",
            "utterances": [
                {"start_seconds":   0, "end_seconds":  10,
                  "text": "Hello there everyone."},
                {"start_seconds": 10, "end_seconds":  20,
                  "text": "Today we talk about radio and what it means. Why is it relevant?"},
                {"start_seconds": 20, "end_seconds":  35,
                  "text": "Why does this still matter so much? Many people ask "
                                "the same question every single day to us."}]}))
        out = run(pc.generate_clips(db, episode_id=ep_id, count=2))
        assert out.get("count_inserted") == 2, out
        clips = out["clips"]
        # Each clip has a Tigris key + audio_url and HEAD-verifies.
        s = obs.TigrisStorage()
        for c in clips:
            h = s.head(key=c["storage_key"])
            assert h is not None and int(h.get("size") or 0) > 1000
            assert c["audio_url"].startswith("/api/podcasts/clips/")
            # ffprobe duration matches the start/end window within ±200ms.
            import tempfile
            buf = s.open_range(key=c["storage_key"], start=0,
                                              end=int(h["size"]) - 1)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(buf); f.flush()
                p = subprocess.run(
                    ["ffprobe", "-v", "error",
                      "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", f.name],
                    capture_output=True, timeout=10)
                actual = float(p.stdout.decode().strip() or 0)
            expected = c["end_seconds"] - c["start_seconds"]
            assert abs(actual - expected) < 0.3, (
                f"clip duration {actual:.3f}s vs window {expected:.3f}s")
            s.delete(key=c["storage_key"])
    finally:
        try: obs.TigrisStorage().delete(key=src_key)
        except Exception: pass
        run(db.podcast_clips.delete_many({"episode_id": ep_id}))
        run(db.podcast_transcripts.delete_one({"episode_id": ep_id}))
        run(db.podcast_episodes.delete_one({"id": ep_id}))
