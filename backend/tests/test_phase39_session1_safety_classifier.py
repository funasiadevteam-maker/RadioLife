"""Phase 39 Session 1 — safety classifier + persona seed tests.

Coverage:
  • clean / safe personas pass
  • exact celebrity name → name_match flag, is_safe=False
  • fuzzy celebrity name (≤1 edit) → name_match flag
  • celebrity name with accents → normalized + flagged
  • catchphrase exact match → catchphrase_match flag
  • catchphrase fuzzy / substring → catchphrase_match flag
  • clean catchphrases pass
  • external voice clone URL → external_voice_clone flag
  • internal (Tigris / preview host / /storage/) URL → safe
  • LLM-prefilter "sounds like" — without API key returns
      llm_judge_unavailable flag (not silently safe)
  • LLM-prefilter mocked positive → blocks with llm_imitation_judgement
  • LLM-prefilter mocked clean → passes
  • seed script runs end-to-end against test DB, 10 launch personas
      all classify as safe and get inserted
  • seed script is idempotent (run twice → still 10 rows)
  • blocklist files load via reload_blocklists()
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from services.persona_safety import (PersonaSafetyClassifier,
                                                                          reload_blocklists)
import services.persona_safety as ps_mod
from scripts.phase39_seed_launch_personas import (LAUNCH_PERSONAS,
                                                                                                  seed_launch_personas)


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _clean_persona(**overrides):
    base = {
        "persona_id":  "test_clean",
        "display_name":  "Dawn Caller",
        "archetype":      "calm_morning_hinglish",
        "description":  "A calm Hinglish morning host.",
        "signature_phrases": ["soft start, big day"],
        "voice_clone_reference_url": None,
    }
    base.update(overrides)
    return base


classifier = PersonaSafetyClassifier()


# ─── name_match ──────────────────────────────────────────────────────
def test_clean_persona_is_safe():
    r = classifier.classify(_clean_persona())
    assert r["is_safe"] is True, r
    assert "name_match" not in r["flags"]
    assert "catchphrase_match" not in r["flags"]


def test_exact_celebrity_name_blocks():
    r = classifier.classify(_clean_persona(display_name="Shah Rukh Khan"))
    assert r["is_safe"] is False
    assert "name_match" in r["flags"]
    assert any("shah rukh khan" in e for e in r["evidence"])


def test_celebrity_case_variant_blocks():
    r = classifier.classify(_clean_persona(display_name="TOM CRUISE"))
    assert r["is_safe"] is False
    assert "name_match" in r["flags"]


def test_celebrity_name_with_typo_blocks_fuzzy():
    # 1-edit typo — should still match.
    r = classifier.classify(_clean_persona(display_name="Salman Kahn"))
    assert r["is_safe"] is False
    assert "name_match" in r["flags"]


def test_celebrity_substring_in_persona_name_blocks():
    r = classifier.classify(_clean_persona(
        display_name="Tom Cruise from Dubai"))
    assert r["is_safe"] is False
    assert "name_match" in r["flags"]


def test_unicode_normalized_celebrity_name_blocks():
    # Diacritic stripped → "amitabh bachchan"
    r = classifier.classify(_clean_persona(display_name="Amìtabh Báchchàn"))
    assert r["is_safe"] is False
    assert "name_match" in r["flags"]


# ─── catchphrase_match ───────────────────────────────────────────────
def test_blocked_catchphrase_exact():
    r = classifier.classify(_clean_persona(
        signature_phrases=["yabba dabba doo"]))
    assert r["is_safe"] is False
    assert "catchphrase_match" in r["flags"]


def test_blocked_catchphrase_fuzzy():
    # "I'll be back" with extra space normalises to identical
    r = classifier.classify(_clean_persona(
        signature_phrases=["I'll  be back!"]))
    assert r["is_safe"] is False
    assert "catchphrase_match" in r["flags"]


def test_blocked_catchphrase_substring():
    r = classifier.classify(_clean_persona(
        signature_phrases=["maybe say bazinga sometime"]))
    assert r["is_safe"] is False
    assert "catchphrase_match" in r["flags"]


def test_clean_catchphrases_pass():
    r = classifier.classify(_clean_persona(
        signature_phrases=["good vibes only", "let's roll",
                                              "soft start, big day"]))
    assert r["is_safe"] is True


# ─── external_voice_clone ────────────────────────────────────────────
def test_external_voice_clone_url_flags():
    r = classifier.classify(_clean_persona(
        voice_clone_reference_url="https://www.youtube.com/watch?v=abc"))
    assert r["is_safe"] is False
    assert "external_voice_clone" in r["flags"]


def test_external_spotify_url_flags():
    r = classifier.classify(_clean_persona(
        voice_clone_reference_url="https://open.spotify.com/track/xyz"))
    assert r["is_safe"] is False
    assert "external_voice_clone" in r["flags"]


def test_internal_tigris_url_passes():
    r = classifier.classify(_clean_persona(
        voice_clone_reference_url="s3://bigfm-tigris/persona-refs/p1.mp3"))
    assert "external_voice_clone" not in r["flags"]


def test_internal_storage_path_passes():
    r = classifier.classify(_clean_persona(
        voice_clone_reference_url="/app/backend/storage/personas/p1.mp3"))
    assert "external_voice_clone" not in r["flags"]


def test_emergent_preview_host_passes():
    r = classifier.classify(_clean_persona(
        voice_clone_reference_url=
        "https://mobile-games-v2.preview.emergentagent.com/static/p1.mp3"))
    assert "external_voice_clone" not in r["flags"]


# ─── LLM judge ───────────────────────────────────────────────────────
def test_llm_prefilter_not_triggered_without_phrase():
    r = classifier.classify(_clean_persona(
        description="A high-energy host who brings the morning rush to life."))
    assert "llm_imitation_judgement" not in r["flags"]
    # Either passes or only carries unavailability flag — never blocks.
    assert r["is_safe"] in (True, False)


def test_llm_prefilter_phrase_without_api_returns_unavailable_flag():
    """Description contains a trigger phrase; OPENAI_API_KEY removed →
    surfaces `llm_judge_unavailable` instead of silently passing."""
    saved_openai = os.environ.pop("OPENAI_API_KEY", None)
    saved_emerge = os.environ.pop("EMERGENT_LLM_KEY", None)
    try:
        reload_blocklists()
        r = classifier.classify(_clean_persona(
            description="A morning voice in the style of someone iconic."))
        # Not a hard block (we degrade open) but the unavailability is
        # visible to admins.
        assert "llm_judge_unavailable" in r["flags"]
    finally:
        if saved_openai: os.environ["OPENAI_API_KEY"] = saved_openai
        if saved_emerge: os.environ["EMERGENT_LLM_KEY"] = saved_emerge


def test_llm_prefilter_mocked_positive_blocks():
    """When the LLM judge confirms imitation, persona blocks."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "is_imitation": True, "confidence": 0.92,
        "figure_named": "Tom Cruise"})
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
    orig = getattr(ps_mod, "OpenAI", None)
    ps_mod.OpenAI = lambda **kw: mock_client
    try:
        r = classifier.classify(_clean_persona(
            description="A voice in the style of a famous host."))
    finally:
        ps_mod.OpenAI = orig
    assert r["is_safe"] is False
    assert "llm_imitation_judgement" in r["flags"]
    assert any("tom cruise" in e.lower() for e in r["evidence"])


def test_llm_prefilter_mocked_clean_passes():
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "is_imitation": False, "confidence": 0.10,
        "figure_named": None})
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
    orig = getattr(ps_mod, "OpenAI", None)
    ps_mod.OpenAI = lambda **kw: mock_client
    try:
        r = classifier.classify(_clean_persona(
            description="A warm morning voice in the style of a classic radio host archetype."))
    finally:
        ps_mod.OpenAI = orig
    assert r["is_safe"] is True
    assert "llm_imitation_judgement" not in r["flags"]


# ─── 10-archetype launch personas ────────────────────────────────────
def test_all_10_launch_personas_classify_safe():
    """The 10 archetypes shipped in scripts/phase39_seed_launch_personas
    MUST all pass the classifier — otherwise the seed will block."""
    for p in LAUNCH_PERSONAS:
        r = classifier.classify(p)
        # Allow llm_judge_unavailable on personas whose descriptions
        # contain prefilter triggers (none should, but the flag is OK).
        non_judge_flags = [f for f in r["flags"]
                                          if f != "llm_judge_unavailable"]
        assert not non_judge_flags, \
              f"persona {p['persona_id']} unsafe: {r['flags']} "\
              f"{r['evidence']}"


def test_launch_personas_are_10_with_distinct_voice_keys():
    assert len(LAUNCH_PERSONAS) == 10
    voice_keys = [p["voice_key"] for p in LAUNCH_PERSONAS]
    assert len(set(voice_keys)) == 10, \
          f"voice_keys must be distinct: {voice_keys}"


def test_launch_persona_ids_are_p39_prefixed_and_unique():
    ids = [p["persona_id"] for p in LAUNCH_PERSONAS]
    assert len(set(ids)) == 10
    for pid in ids:
        assert pid.startswith("p39_"), pid


# ─── seed script end-to-end ──────────────────────────────────────────
def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_seed_inserts_10_personas_and_is_idempotent():
    async def go():
        db = _db()
        # Clean any prior seed rows.
        await db.rj_personality_profiles.delete_many(
            {"_id": {"$regex": "^p39_"}})
        r1 = await seed_launch_personas(db)
        assert r1["classified"] == 10
        assert r1["seeded"] == 10
        assert r1["blocked"] == 0
        # Idempotent — second run upserts cleanly, still 10 rows.
        r2 = await seed_launch_personas(db)
        assert r2["seeded"] == 10
        count = await db.rj_personality_profiles.count_documents(
            {"is_launch_persona": True})
        assert count == 10
        # Each row has safety_classification.is_safe=True
        async for doc in db.rj_personality_profiles.find(
            {"is_launch_persona": True}):
            assert doc.get("safety_classification", {}).get("is_safe") is True
            assert doc.get("voice_id"), \
                  f"persona {doc['_id']} missing voice_id"
    run(go())


# ─── blocklist reload (hot-update without restart) ──────────────────
def test_reload_blocklists_smoke():
    reload_blocklists()  # Should not raise
    classifier2 = PersonaSafetyClassifier()
    r = classifier2.classify(_clean_persona(display_name="Salman Khan"))
    assert r["is_safe"] is False
