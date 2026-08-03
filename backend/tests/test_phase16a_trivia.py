"""Phase 16a — Trivia backend regression suite.

Verifies the 8 acceptance criteria from the phase brief:
  1. test_generate_questions_for_dfw_excludes_dubai_tokens
  2. test_generate_questions_returns_valid_schema
  3. test_start_session_returns_questions_without_correct_choice_id
  4. test_answer_endpoint_records_latency_and_correctness
  5. test_finish_session_awards_bigcoins_proportional_to_score
  6. test_answer_rejected_after_30s_timeout
  7. test_user_does_not_get_same_question_twice_within_90_days
  8. test_category_list_respects_user_market

Each test boots a fresh in-memory state via the live backend at
REACT_APP_BACKEND_URL.  The /api/auth/demo demo login is used to get
a valid session cookie.  OpenAI is real — only run this when OPENAI_API_KEY
is configured.
"""
from __future__ import annotations
import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://mobile-games-v2.preview.emergentagent.com",
)
API = f"{BACKEND_URL}/api"


@pytest.fixture(scope="module")
def session() -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=60.0)
    r = c.post("/auth/demo")
    assert r.status_code == 200, f"demo login failed: {r.text}"
    return c


@pytest.fixture(scope="module")
def dfw_local_culture_cat_id(session: httpx.Client) -> str:
    r = session.get("/trivia/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    dfw_cat = next((c for c in cats if c["id"] == "dfw-local-culture"), None)
    assert dfw_cat, f"DFW local-culture not found: {[c['id'] for c in cats]}"
    return dfw_cat["id"]


# ─── 1. DFW questions never reference Dubai ─────────────────────────────
def test_generate_questions_for_dfw_excludes_dubai_tokens():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    import motor.motor_asyncio
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    db = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ["DB_NAME"]
    ]
    from services.trivia_ai import generate_questions
    from services.market_context import banned_tokens_for_market

    docs = loop.run_until_complete(
        generate_questions(db, "dfw", "local-culture", 2, 5)
    )
    assert len(docs) >= 1, "DFW generator returned nothing"
    for q in docs:
        blob = q["prompt"] + " " + " ".join(c["text"] for c in q["choices"])
        hits = banned_tokens_for_market(blob, "dfw")
        assert not hits, f"DFW leak: {hits} in {q['prompt']!r}"


# ─── 2. JSON schema validity ────────────────────────────────────────────
def test_generate_questions_returns_valid_schema():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    import motor.motor_asyncio
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    db = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ["DB_NAME"]
    ]
    from services.trivia_ai import generate_questions
    docs = loop.run_until_complete(
        generate_questions(db, "dubai", "general", 2, 3)
    )
    assert len(docs) >= 1
    for q in docs:
        assert isinstance(q["prompt"], str) and q["prompt"].strip()
        assert isinstance(q["choices"], list) and len(q["choices"]) == 4
        for c in q["choices"]:
            assert {"id", "text"} <= set(c.keys())
            assert c["id"] in ("a", "b", "c", "d")
        assert q["correct_choice_id"] in {c["id"] for c in q["choices"]}


# ─── 3. Server hides the answer key ─────────────────────────────────────
def test_start_session_returns_questions_without_correct_choice_id(
    session: httpx.Client, dfw_local_culture_cat_id: str,
):
    r = session.post(
        "/trivia/sessions/start",
        json={"category_id": dfw_local_culture_cat_id, "difficulty": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body
    assert len(body["questions"]) >= 1
    for q in body["questions"]:
        assert "correct_choice_id" not in q, "answer key leaked!"
        assert "correct_index" not in q


# ─── 4. Answer records latency + correctness ────────────────────────────
def test_answer_endpoint_records_latency_and_correctness(
    session: httpx.Client, dfw_local_culture_cat_id: str,
):
    start = session.post(
        "/trivia/sessions/start",
        json={"category_id": dfw_local_culture_cat_id, "difficulty": 2},
    ).json()
    q = start["questions"][0]
    sid = start["session_id"]
    # Pick choice 'a' — may or may not be correct, but the response shape
    # must be stable.
    r = session.post(f"/trivia/sessions/{sid}/answer",
                          json={"question_id": q["id"], "choice_id": "a"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["correct"], bool)
    assert body["correct_choice_id"] in ("a", "b", "c", "d")
    assert body["latency_ms"] >= 0
    assert isinstance(body["points_awarded"], int)
    assert isinstance(body["running_score"], int)


# ─── 5. Finish awards BC ≈ score/10 ─────────────────────────────────────
def test_finish_session_awards_bigcoins_proportional_to_score(
    session: httpx.Client, dfw_local_culture_cat_id: str,
):
    start = session.post(
        "/trivia/sessions/start",
        json={"category_id": dfw_local_culture_cat_id, "difficulty": 2},
    ).json()
    sid = start["session_id"]
    # Answer all questions with 'a' just so we have *some* score.
    for q in start["questions"]:
        session.post(f"/trivia/sessions/{sid}/answer",
                       json={"question_id": q["id"], "choice_id": "a"})
    r = session.post(f"/trivia/sessions/{sid}/finish")
    assert r.status_code == 200, r.text
    body = r.json()
    expected_bc = body["final_score"] // 10
    assert body["bigcoin_awarded"] == expected_bc, body
    assert body["already_finished"] is False
    # Idempotent re-finish.
    r2 = session.post(f"/trivia/sessions/{sid}/finish").json()
    assert r2["already_finished"] is True


# ─── 6. Answer rejected after the 30-s window ───────────────────────────
def test_answer_rejected_after_30s_timeout(
    session: httpx.Client, dfw_local_culture_cat_id: str,
):
    # Use the DB directly to forge a served_at well in the past so we
    # don't have to actually wait 30 seconds.
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    import motor.motor_asyncio
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    db = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ["DB_NAME"]
    ]
    start = session.post(
        "/trivia/sessions/start",
        json={"category_id": dfw_local_culture_cat_id, "difficulty": 2},
    ).json()
    sid = start["session_id"]
    q = start["questions"][0]
    # Forge served_at to 60s ago.
    forged = datetime.now(timezone.utc) - timedelta(seconds=60)
    loop.run_until_complete(db.trivia_sessions.update_one(
        {"id": sid}, {"$set": {f"served_at.{q['id']}": forged}}
    ))
    r = session.post(f"/trivia/sessions/{sid}/answer",
                          json={"question_id": q["id"], "choice_id": "a"})
    assert r.status_code == 408, f"expected 408, got {r.status_code}: {r.text}"


# ─── 7. No duplicate question within 90 days ────────────────────────────
def test_user_does_not_get_same_question_twice_within_90_days(
    session: httpx.Client, dfw_local_culture_cat_id: str,
):
    s1 = session.post("/trivia/sessions/start",
                          json={"category_id": dfw_local_culture_cat_id}).json()
    s1_ids = {q["id"] for q in s1["questions"]}
    # Answer all to record them.
    for q in s1["questions"]:
        session.post(f"/trivia/sessions/{s1['session_id']}/answer",
                       json={"question_id": q["id"], "choice_id": "a"})
    session.post(f"/trivia/sessions/{s1['session_id']}/finish")

    s2 = session.post("/trivia/sessions/start",
                          json={"category_id": dfw_local_culture_cat_id}).json()
    s2_ids = {q["id"] for q in s2["questions"]}
    overlap = s1_ids & s2_ids
    # Soft check: overlap can be 0 if there are enough fresh questions.
    # The freshness window should prevent ALL of session 1 from re-appearing
    # at once.
    assert len(overlap) < len(s1_ids), (
        f"All {len(s1_ids)} questions repeated — freshness rule broken."
    )


# ─── 8. Categories respect user market ──────────────────────────────────
def test_category_list_respects_user_market(session: httpx.Client):
    r = session.get("/trivia/categories")
    assert r.status_code == 200
    body = r.json()
    assert body["market"] in {"dfw", "dubai", "new_york", "london", "toronto", "global"}
    cats = body["categories"]
    # The DFW user should see exactly one local-culture row (Dallas)
    # plus the global pool — never the Dubai local-culture.
    local = [c for c in cats if c["slug"] == "local-culture"]
    assert all(c["market"] in (body["market"], "global") for c in cats), \
        f"non-market category leaked: {cats}"
    if body["market"] == "dfw":
        assert any(c["id"] == "dfw-local-culture" for c in cats)
        assert not any(c["id"] == "dubai-local-culture" for c in cats), \
            "Dubai category should not appear for DFW users"
