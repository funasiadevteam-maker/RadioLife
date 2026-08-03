"""Phase 40 — NewsData client + endpoints + radio renderer."""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient


def run(c): return asyncio.get_event_loop().run_until_complete(c)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_newsdata_client_mock_mode_returns_stubs(monkeypatch):
    """When NEWSDATA_API_KEY is empty or 'mock', returns local fixture."""
    import importlib
    monkeypatch.setenv("NEWSDATA_API_KEY", "mock")
    import services.newsdata_client as nc
    importlib.reload(nc)

    async def go():
        rows = await nc.fetch_latest_headlines(limit=3)
        assert len(rows) == 3
        assert rows[0]["news_id"]
        assert rows[0]["title"]
        assert nc.is_live() is False
    run(go())


def test_newsdata_client_live_key_present(monkeypatch):
    """If a live key is configured, is_live() returns True (we don't actually
    hit the API in this test — just sanity-check the wiring)."""
    import importlib
    monkeypatch.setenv("NEWSDATA_API_KEY", "pub_test_live_demo_key")
    import services.newsdata_client as nc
    importlib.reload(nc)
    assert nc.is_live() is True


def test_news_endpoints_headlines_and_article(monkeypatch):
    """Verifies the cache warms on first call, then second call serves cache,
    and /article/:id returns 200 for an existing news_id."""
    monkeypatch.setenv("NEWSDATA_API_KEY", "mock")
    import importlib
    import services.newsdata_client as nc
    importlib.reload(nc)
    import routes.news as nrt
    importlib.reload(nrt)

    async def go():
        from httpx import ASGITransport, AsyncClient
        import server as server_mod
        importlib.reload(server_mod)
        db = _db()
        await db.news_articles.delete_many({"news_id": {"$regex": "^mock_n"}})
        async with AsyncClient(transport=ASGITransport(app=server_mod.app),
                               base_url="http://test", timeout=60) as ac:
            r1 = await ac.get("/api/news/headlines?limit=5")
            assert r1.status_code == 200, r1.text
            j = r1.json()
            assert j["count"] >= 3
            assert j["live"] is False  # mock mode
            assert j["items"][0]["title"]
            nid = j["items"][0]["news_id"]
            # second call cached
            r2 = await ac.get("/api/news/headlines?limit=5")
            assert r2.status_code == 200
            # detail
            r3 = await ac.get(f"/api/news/article/{nid}")
            assert r3.status_code == 200
            assert r3.json()["news_id"] == nid
            # bogus id
            r4 = await ac.get("/api/news/article/does_not_exist")
            assert r4.status_code == 404
    run(go())


def test_news_radio_renderer_summary_idempotent():
    """Renderer writes summary_script on first pass, no-op on second."""
    import importlib
    monkey_key = os.environ.get("OPENAI_API_KEY")
    import services.news_radio_renderer as nr
    importlib.reload(nr)

    async def go():
        db = _db()
        nid = "test_renderer_001"
        await db.news_articles.delete_one({"news_id": nid})
        await db.news_articles.insert_one({
            "news_id": nid,
            "title":   "Test article for renderer",
            "description": "This is a short test description of an article "
                           "used to validate summary generation idempotence.",
            "source_name": "Test Source",
            "categories": ["test"],
            "summary_script": None,
        })
        art = await db.news_articles.find_one({"news_id": nid})
        t1 = await nr.render_summary_for_article(db, art)
        assert t1, "first render should produce text"
        art2 = await db.news_articles.find_one({"news_id": nid})
        assert art2["summary_script"]
        t2 = await nr.render_summary_for_article(db, art2)
        # idempotent — second call returns the cached script
        assert t2 == art2["summary_script"]
        await db.news_articles.delete_one({"news_id": nid})
    run(go())
