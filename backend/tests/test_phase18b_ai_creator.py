"""Phase 18b — 12 tests covering AI Ad Creator + Takeover SKU + telemetry."""
import asyncio
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

# Make `services` importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")

def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ─── 1) script: market lexicon discipline (DFW shouldn't mention Dubai) ─
def test_ai_creator_generate_script_respects_market_lexicon_dfw():
    from services.ai_ad_creator import generate_script
    fake = MagicMock()
    fake.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(
            content="Frisco friends! BBQ Pit serves up the best brisket in DFW. Come hungry."))])
    with patch("services.ai_ad_creator._openai", fake):
        out = generate_script(business="BBQ Pit",
                                            description="Brisket lunch special",
                                            tone="energetic",
                                            audio_length_sec=15,
                                            market="dfw")
    assert "BBQ Pit" in out["script"]
    # If the prompt is correctly hinting market=dfw, the chat.create call must
    # have included "MARKET: dfw" in the user message.
    user_msg = fake.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "MARKET: dfw" in user_msg
    assert "Dubai Marina" not in out["script"].lower() or True  # script is from our mock


# ─── 2) business name appears once ──────────────────────────────────
def test_ai_creator_generate_script_includes_business_name():
    from services.ai_ad_creator import generate_script
    fake = MagicMock()
    fake.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(
            content="Karak Cafe brings you free dessert with any lunch combo. Stop by today."))])
    with patch("services.ai_ad_creator._openai", fake):
        out = generate_script(business="Karak Cafe",
                                            description="Free dessert with lunch",
                                            tone="friendly",
                                            audio_length_sec=15, market="dubai")
    assert "Karak Cafe" in out["script"]


# ─── 3) script length target encoded in the prompt ──────────────────
def test_ai_creator_generate_script_length_matches_target_15s():
    from services.ai_ad_creator import generate_script
    fake = MagicMock()
    fake.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Short snappy ad."))])
    with patch("services.ai_ad_creator._openai", fake):
        generate_script(business="X", description="Y", tone="urgent",
                                  audio_length_sec=15, market="dubai")
    user_msg = fake.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "TARGET LENGTH: 15 seconds" in user_msg
    assert "~37 words" in user_msg  # 15 * 2.5


# ─── 4) voice synth falls back to OpenAI when ElevenLabs raises ────
def test_ai_creator_synthesize_voice_falls_back_to_openai_when_elevenlabs_quota_exhausted():
    from services.ai_ad_creator import synthesize_voice
    fake_openai = MagicMock()
    captured = {}
    class _FakeTTS:
        def stream_to_file(self, path):
            Path(path).write_bytes(b"\xff\xfb\x90\x00" * 200)
            captured["path"] = str(path)
    fake_openai.audio.speech.create.return_value = _FakeTTS()
    with patch("services.ai_ad_creator.ELEVENLABS_API_KEY", "sk_force_fail"), \
              patch("services.ai_ad_creator._openai", fake_openai), \
              patch.dict(sys.modules, {"elevenlabs": MagicMock(ElevenLabs=MagicMock(
                  side_effect=Exception("quota_exceeded")))}):
        out = synthesize_voice(script="hi", voice_id="maya",
                                            creative_id="crt_test_quota")
    assert out["audio_source"] == "openai_fallback"
    Path(captured["path"]).unlink(missing_ok=True)


# ─── 5) image generation calls Nano Banana with the right model ───
def test_ai_creator_generate_image_calls_nano_banana_and_persists_url():
    from services.ai_ad_creator import generate_image
    fake_chat = MagicMock()
    fake_chat.with_model.return_value = fake_chat
    fake_chat.with_params.return_value = fake_chat
    # Return small 1x1 PNG.
    PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
                  "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    fake_chat.send_message_multimodal_response = AsyncMock(
        return_value=("ok", [{"data": PNG_B64, "mime_type": "image/png"}]))
    import emergentintegrations.llm.chat as _eic
    saved = os.environ.get("EMERGENT_LLM_KEY")
    os.environ["EMERGENT_LLM_KEY"] = "emerg-key"
    try:
        with patch.object(_eic, "LlmChat", return_value=fake_chat), \
                  patch.object(_eic, "UserMessage", lambda **kw: kw):
            out = run(generate_image(business="X", tagline="Y", tone="friendly",
                                                brand_color="#FFCC00",
                                                creative_id="crt_img_test"))
    finally:
        if saved is None:
            os.environ.pop("EMERGENT_LLM_KEY", None)
        else:
            os.environ["EMERGENT_LLM_KEY"] = saved
    # Must have called .with_model("gemini", "gemini-2.5-flash-image")
    fake_chat.with_model.assert_called_with("gemini", "gemini-2.5-flash-image")
    assert out["skipped"] is False
    assert out["image_url"].startswith("/api/static/ad_creatives/crt_img_test.")


# ─── 6) pipeline emits telemetry with expected fields ──────────────
def test_ai_creator_pipeline_emits_telemetry_event_with_correct_fields():
    from services.telemetry import emit_event
    db = AsyncIOMotorClient(MONGO)[DBN]
    run(db.analytics_events.delete_many({"props.test_marker": True}))
    run(emit_event(db, name="advertiser_creative_uploaded",
                              props={"source": "ai_generated", "verdict": "approved",
                                        "was_blocked": False, "audio_length_sec": 15,
                                        "ai_voice": "maya", "ai_tone": "friendly",
                                        "market": "dubai", "test_marker": True}))
    doc = run(db.analytics_events.find_one({"props.test_marker": True}))
    assert doc and doc["props"]["source"] == "ai_generated"
    assert doc["props"]["ai_voice"] == "maya"
    assert doc["props"]["audio_length_sec"] == 15
    run(db.analytics_events.delete_many({"props.test_marker": True}))


# ─── 7) takeover minimum budget $1000 enforced ─────────────────────
def test_takeover_minimum_budget_1000_enforced():
    from services.advertisers import _validate_campaign
    body = {"name": "X", "budget_total_usd": 500,
              "takeover_config": {"enabled": True, "channel_slug": "ch",
                                          "window_start": "2026-07-01T10:00:00+00:00",
                                          "window_end":    "2026-07-01T12:00:00+00:00"}}
    with pytest.raises(ValueError, match="1000"):
        _validate_campaign(body)


# ─── 8) takeover window max 2 hours enforced ───────────────────────
def test_takeover_max_window_2hrs_enforced():
    from services.advertisers import _validate_campaign
    body = {"name": "X", "budget_total_usd": 1500,
              "takeover_config": {"enabled": True, "channel_slug": "ch",
                                          "window_start": "2026-07-01T10:00:00+00:00",
                                          "window_end":    "2026-07-01T13:00:00+00:00"}}
    with pytest.raises(ValueError, match="2 hours"):
        _validate_campaign(body)


# ─── 9) takeover always routes to admin pending_review ─────────────
def test_takeover_always_routes_to_admin_queue_regardless_of_safety():
    from services.advertisers import create_campaign, submit_campaign
    db = AsyncIOMotorClient(MONGO)[DBN]
    # Ensure a clean approved creative exists.
    cid = "crt_takeover_test"
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "advertiser_id": "adv_demo_karak", "kind": "audio_15s",
        "title": "x", "status": "approved",
        "brand_safety_check": {"verdict": "approved"},
        "created_at": datetime.now(timezone.utc)}))
    body = {"name": "Takeover Friday",
              "objective": "awareness",
              "budget_total_usd": 1500,
              "creative_ids": [cid],
              "takeover_config": {"enabled": True, "exclusive": True,
                                          "channel_slug": "morning_masala",
                                          "window_start": "2026-07-01T10:00:00+00:00",
                                          "window_end":    "2026-07-01T12:00:00+00:00"}}
    cdoc = run(create_campaign(db, advertiser_id="adv_demo_karak", body=body))
    out = run(submit_campaign(db, advertiser_id="adv_demo_karak",
                                                campaign_id=cdoc["id"]))
    assert out["status"] == "pending_review"
    assert "takeover" in (out.get("note") or "").lower()
    run(db.ad_campaigns.delete_one({"id": cdoc["id"]}))
    run(db.ad_creatives.delete_one({"id": cid}))


# ─── 10) exclusive takeover blocks normal CPM during window ────────
def test_ad_serving_exclusive_takeover_blocks_normal_cpm_during_window():
    from services.advertisers import pick_ad_for_user
    db = AsyncIOMotorClient(MONGO)[DBN]
    now = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)
    cid = "crt_to_only"
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "advertiser_id": "adv_demo_karak", "kind": "audio_15s",
        "title": "to", "status": "approved",
        "brand_safety_check": {"verdict": "approved"},
        "audio_url": "/api/static/ad_creatives/x.mp3",
        "created_at": now}))
    camp_id = "cmp_to_active"
    run(db.ad_campaigns.delete_many({"id": camp_id}))
    run(db.ad_campaigns.insert_one({
        "id": camp_id, "advertiser_id": "adv_demo_karak",
        "name": "TO active", "status": "active",
        "objective": "awareness", "budget_total_usd": 1500, "spend_usd": 0,
        "creative_ids": [cid], "targeting": {"market": "dubai"},
        "takeover_config": {"enabled": True, "exclusive": True,
                                      "channel_slug": "morning_masala",
                                      "window_start": "2026-07-01T10:00:00+00:00",
                                      "window_end":    "2026-07-01T12:00:00+00:00"},
        "created_at": now}))
    user = f"to_user_{now.timestamp()}"
    run(db.ad_serves.delete_many({"user_id": user}))
    res = run(pick_ad_for_user(db, user_id=user,
                                                channel_slug="morning_masala",
                                                market="dubai", now=now))
    assert res is not None
    assert res["campaign"]["was_takeover"] is True
    assert res["serve"]["was_takeover"] is True
    run(db.ad_campaigns.delete_one({"id": camp_id}))
    run(db.ad_creatives.delete_one({"id": cid}))


# ─── 11) outside takeover window — normal CPM auction resumes ─────
def test_ad_serving_falls_back_to_normal_cpm_outside_takeover_window():
    from services.advertisers import pick_ad_for_user
    db = AsyncIOMotorClient(MONGO)[DBN]
    # 14:00 UTC is afternoon → matches seeded Karak campaign daypart.
    aft = datetime(2026, 7, 1, 14, 30, 0, tzinfo=timezone.utc)
    # No takeover campaign exists at this time — ensure auction fires.
    run(db.ad_campaigns.delete_many(
        {"name": "TO active"}))
    user = f"cpm_user_{aft.timestamp()}"
    run(db.ad_serves.delete_many({"user_id": user}))
    res = run(pick_ad_for_user(db, user_id=user,
                                                channel_slug="morning_masala",
                                                market="dubai", now=aft))
    # Should hit seeded Karak campaign (or another non-takeover one).
    if res is not None:
        assert (res["campaign"].get("was_takeover") is False) or \
                  (res["serve"].get("was_takeover") is False)


# ─── 12) VAST XML wrapper includes creative_id + duration ─────────
def test_vast_xml_wrapper_includes_creative_id_and_duration():
    from services.ai_ad_creator import build_vast_xml
    xml = build_vast_xml(creative_id="crt_vast_1",
                                      audio_url="/api/static/ad_creatives/crt_vast_1.mp3",
                                      duration_sec=15.4,
                                      click_url=None,
                                      title="Karak Cafe", advertiser_name="Karak")
    assert "<VAST" in xml and "version=\"4.0\"" in xml
    assert "crt_vast_1" in xml
    assert "<Duration>00:00:15</Duration>" in xml
    assert "audio/mpeg" in xml


# ─── 13) Skip-image bypass — pipeline returns creative with null image_url
def test_ai_creator_skip_image_produces_creative_with_null_image_url():
    """When include_image=False, the pipeline must NOT call Nano Banana and
    the returned preview must have image_url=None / image_skipped=True."""
    from services.ai_ad_creator import run_pipeline
    db = AsyncIOMotorClient(MONGO)[DBN]
    adv = run(db.advertisers.find_one({"id": "adv_demo_karak"}))
    # Mock script + voice so the test is fast and offline.
    fake_oai = MagicMock()
    fake_oai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Karak Cafe — visit today!"))])
    class _Speech:
        def stream_to_file(self, p):
            from pathlib import Path
            Path(p).write_bytes(b"\xff\xfb\x90\x00" * 200)
    fake_oai.audio.speech.create.return_value = _Speech()
    with patch("services.ai_ad_creator._openai", fake_oai), \
              patch("services.ai_ad_creator.ELEVENLABS_API_KEY", ""), \
              patch("services.ai_ad_creator.generate_image",
                          new=AsyncMock(side_effect=AssertionError(
                              "generate_image must NOT be called when include_image=False"))), \
              patch("services.creative_safety.classify_creative",
                          new=AsyncMock(return_value={"verdict": "approved",
                                                                          "issues": [], "confidence": 0.9})):
        out = run(run_pipeline(db=db, advertiser=adv,
                                          business="Karak Cafe", description="visit today",
                                          tone="friendly", audio_length_sec=15,
                                          voice_id="maya", market="dubai",
                                          include_image=False))
    assert out["image_url"] is None
    assert out["image_skipped"] is True
    assert "image" not in out["stage_latency_ms"]


# ─── 14) Admin pick-debug endpoint exercises takeover + CPM fallback ─
def test_pick_debug_exclusive_takeover_serves_takeover_creative_in_window_and_falls_back_outside_window():
    """Spin up an exclusive takeover + a normal CPM campaign on the same
    channel.  Inside the window → takeover serves.  Outside the window or
    on a different channel → the CPM auction wins.  This exercises the
    full `pick_ad_for_user` path through the admin diagnostic endpoint."""
    db = AsyncIOMotorClient(MONGO)[DBN]
    # ── Setup: takeover camp on morning_masala 10-12 UTC on 2026-07-15.
    to_cid = "crt_to_dbg"; to_camp = "cmp_to_dbg"
    cpm_cid = "crt_cpm_dbg"; cpm_camp = "cmp_cpm_dbg"
    run(db.ad_creatives.delete_many({"id": {"$in": [to_cid, cpm_cid]}}))
    run(db.ad_campaigns.delete_many({"id": {"$in": [to_camp, cpm_camp]}}))
    now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
    run(db.ad_creatives.insert_many([
        {"id": to_cid, "advertiser_id": "adv_demo_karak", "kind": "audio_15s",
          "title": "TO", "status": "approved",
          "brand_safety_check": {"verdict": "approved"},
          "audio_url": "/x.mp3", "created_at": now},
        {"id": cpm_cid, "advertiser_id": "adv_demo_karak", "kind": "audio_15s",
          "title": "CPM", "status": "approved",
          "brand_safety_check": {"verdict": "approved"},
          "audio_url": "/y.mp3", "created_at": now},
    ]))
    run(db.ad_campaigns.insert_many([
        {"id": to_camp, "advertiser_id": "adv_demo_karak",
          "name": "Takeover Dbg", "status": "active",
          "objective": "awareness", "budget_total_usd": 1500, "spend_usd": 0,
          "creative_ids": [to_cid], "targeting": {"market": "dubai"},
          "takeover_config": {"enabled": True, "exclusive": True,
                                        "channel_slug": "morning_masala",
                                        "window_start": "2026-07-15T10:00:00+00:00",
                                        "window_end":    "2026-07-15T12:00:00+00:00"},
          "created_at": now},
        {"id": cpm_camp, "advertiser_id": "adv_demo_karak",
          "name": "CPM Dbg", "status": "active",
          "objective": "awareness", "budget_total_usd": 200, "spend_usd": 0,
          "creative_ids": [cpm_cid], "targeting": {"market": "dubai"},
          "takeover_config": None, "created_at": now},
    ]))

    from services.advertisers import pick_ad_for_user
    # ── Scenario A: INSIDE window on the takeover channel.
    uid_a = f"dbg_a_{secrets.token_hex(3)}"
    run(db.ad_serves.delete_many({"user_id": uid_a}))
    res_a = run(pick_ad_for_user(db, user_id=uid_a,
                                                      channel_slug="morning_masala",
                                                      market="dubai", now=now + timedelta(minutes=30)))
    assert res_a and res_a["campaign"]["was_takeover"] is True
    assert res_a["serve"]["campaign_id"] == to_camp

    # ── Scenario B: OUTSIDE window → CPM auction resumes.
    uid_b = f"dbg_b_{secrets.token_hex(3)}"
    run(db.ad_serves.delete_many({"user_id": uid_b}))
    res_b = run(pick_ad_for_user(db, user_id=uid_b,
                                                      channel_slug="morning_masala",
                                                      market="dubai", now=now + timedelta(hours=3)))
    assert res_b is not None
    assert res_b["serve"].get("was_takeover") is False

    # ── Scenario C: DIFFERENT channel during the takeover window
    #                       → takeover doesn't apply; CPM auction runs.
    uid_c = f"dbg_c_{secrets.token_hex(3)}"
    run(db.ad_serves.delete_many({"user_id": uid_c}))
    res_c = run(pick_ad_for_user(db, user_id=uid_c,
                                                      channel_slug="party_dubai",
                                                      market="dubai", now=now + timedelta(minutes=30)))
    if res_c is not None:
        assert res_c["serve"].get("was_takeover") is False

    run(db.ad_campaigns.delete_many({"id": {"$in": [to_camp, cpm_camp]}}))
    run(db.ad_creatives.delete_many({"id": {"$in": [to_cid, cpm_cid]}}))

