"""Phase 36e Turn 3.5 — Mailgun migration tests."""
from __future__ import annotations
import asyncio, os, sys, uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_mailgun_client_send_uses_basic_auth():
    from services import mailgun_client as mg
    os.environ["MAILGUN_API_KEY"] = "test-key-123"
    os.environ["MAILGUN_DOMAIN"] = "test.example.com"
    os.environ["MAILGUN_FROM"]      = "noreply@test.example.com"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "<test-msg-id@mg>", "message": "Queued"}
    with patch("services.mailgun_client.requests.post",
                          return_value=mock_resp) as mp:
        res = mg.send_email("to@example.com", "S", "<p>hi</p>",
                                          tags=["first_episode_24h"])
    assert mp.called
    args, kw = mp.call_args
    assert args[0] == "https://api.mailgun.net/v3/test.example.com/messages"
    assert kw["auth"] == ("api", "test-key-123")
    assert kw["data"]["to"] == "to@example.com"
    assert kw["data"]["subject"] == "S"
    assert kw["data"]["from"] == "noreply@test.example.com"
    assert kw["data"]["o:tag"] == ["first_episode_24h"]
    assert res["provider"] == "mailgun"
    assert res["message_id"] == "<test-msg-id@mg>"


def test_nudges_dispatcher_routes_to_mailgun_when_provider_env_set():
    """End-to-end: nudge tick routes to mailgun_client when EMAIL_PROVIDER=mailgun."""
    os.environ["MAILGUN_API_KEY"] = "k"
    os.environ["MAILGUN_DOMAIN"] = "bigfantv.com"
    os.environ["EMAIL_PROVIDER"] = "mailgun"
    async def go():
        from services import nudges as fn
        db = _db()
        cid = f"crt_t_mg_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({
            "id": cid, "user_id": f"u_{cid}",
            "display_name": "Mailgun Tester",
            "email": "test@bigfm.dubai",
            "application_status": "approved",
            "approved_at": datetime.now(timezone.utc) - timedelta(hours=25),
            "nudges_paused": False,
            "nudge_email_24h_sent_at": None,
            "nudge_email_72h_sent_at": None,
            "first_episode_published_at": None})
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": "<mg-id-1@mg>"}
            with patch("services.mailgun_client.requests.post",
                                  return_value=mock_resp) as mp:
                r = await fn.tick_first_episode_nudges(db)
            assert r["window_24h_sent"] == 1
            assert mp.called
            ev = await db.creator_nudge_events.find_one(
                {"creator_id": cid, "event_type": "email_24h_sent"})
            assert ev["provider"] == "mailgun"
            assert ev["provider_message_id"] == "<mg-id-1@mg>"
            # Backward-compat alias retained.
            assert ev["sendgrid_message_id"] == "<mg-id-1@mg>"
        finally:
            await db.podcast_creators.delete_many({"id": cid})
            await db.creator_nudge_events.delete_many({"creator_id": cid})
    run(go())


def test_admin_integrations_mailgun_status_admin_only_403_for_non_admin():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            email = f"u_mg_{uuid.uuid4().hex[:6]}@bigfm.dubai"
            reg = await ac.post("/api/auth/register",
                json={"email": email, "password": "Pwd1234!", "name": "U"})
            tok = reg.json()["session_token"]
            r = await ac.get("/api/podcasts/admin/integrations/mailgun/status",
                                            headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code in (401, 403), r.text
            # Admin → 200.
            adm = await ac.post("/api/auth/login",
                json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
            r2 = await ac.get("/api/podcasts/admin/integrations/mailgun/status",
                headers={"Authorization": f"Bearer {adm.json()['session_token']}"})
            assert r2.status_code == 200
            body = r2.json()
            assert "configured" in body and "live" in body and "domain" in body
            await ac.post("/api/auth/logout")
        db = _db()
        await db.users.delete_many({"email": email})
    run(go())


def test_mailgun_failure_downgrades_to_mock_and_logs():
    """If Mailgun raises, nudges should fall back to mock_mode + log + still record event."""
    os.environ["MAILGUN_API_KEY"] = "k"
    os.environ["MAILGUN_DOMAIN"] = "bigfantv.com"
    os.environ["EMAIL_PROVIDER"] = "mailgun"
    async def go():
        from services import nudges as fn
        db = _db()
        cid = f"crt_t_mgf_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({
            "id": cid, "user_id": f"u_{cid}",
            "display_name": "Failover Tester",
            "email": "test@bigfm.dubai",
            "application_status": "approved",
            "approved_at": datetime.now(timezone.utc) - timedelta(hours=25),
            "nudges_paused": False,
            "nudge_email_24h_sent_at": None,
            "nudge_email_72h_sent_at": None,
            "first_episode_published_at": None})
        try:
            fail_resp = MagicMock()
            fail_resp.status_code = 500
            fail_resp.text = "internal"
            with patch("services.mailgun_client.requests.post",
                                  return_value=fail_resp):
                r = await fn.tick_first_episode_nudges(db)
            # The send still counts as "sent" (we fell back to mock).
            assert r["window_24h_sent"] == 1
            ev = await db.creator_nudge_events.find_one(
                {"creator_id": cid, "event_type": "email_24h_sent"})
            assert ev["provider"] == "mock"
            assert ev["provider_message_id"].startswith("sg_mock_")
        finally:
            await db.podcast_creators.delete_many({"id": cid})
            await db.creator_nudge_events.delete_many({"creator_id": cid})
    run(go())
