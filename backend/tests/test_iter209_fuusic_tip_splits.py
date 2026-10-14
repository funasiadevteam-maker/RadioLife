"""iter_209 FUUSIC — TIP EARNS POINTS + WHO'S PAID TRACKER (backend).

- TIP EARNS POINTS: Uses services.scan_to_pay_service.generate_qr directly to
  make a QR, then exercises resolve→quote→authorize→capture via API.
- WHO'S PAID TRACKER: GET /api/scan-to-pay/splits/mine (default + ?status=partial).
"""
import os
import asyncio
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
MERCHANT = "biz_demo_karak"


# ---- helpers --------------------------------------------------------------
def demo_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"}, timeout=20)
    assert r.status_code == 200, f"demo login failed {r.status_code} {r.text[:200]}"
    return s


async def _generate_qr(amount_cents: int) -> str:
    from services import scan_to_pay_service
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "bigfm")]
    out = await scan_to_pay_service.generate_qr(
        db, merchant_id=MERCHANT, cashier_user_id="seed_cashier", amount_cents=amount_cents
    )
    client.close()
    return out["token"]


def _gen_qr(amount_cents: int) -> str:
    return asyncio.get_event_loop().run_until_complete(_generate_qr(amount_cents))


# ---- TIP EARNS POINTS ------------------------------------------------------
class TestTipEarnsPoints:
    """100% BigPoints payment that includes a tip must still earn BigCoin on tip."""

    def _run(self, s, subtotal, tip):
        tok = _gen_qr(subtotal)
        # quote
        q = s.post(f"{API}/scan-to-pay/quote",
                   json={"qr_token": tok, "points_to_use": subtotal + tip, "tip_cents": tip},
                   timeout=20)
        assert q.status_code == 200, f"quote {q.status_code} {q.text[:200]}"
        qd = q.json()
        # 100% points → card_cents must be 0
        assert qd["card_cents"] == 0, f"expected card_cents=0, got {qd}"
        assert qd["points_value_cents"] == subtotal + tip
        # authorize
        a = s.post(f"{API}/scan-to-pay/authorize",
                   json={"qr_token": tok, "points_to_use": subtotal + tip, "tip_cents": tip},
                   timeout=20)
        assert a.status_code == 200, f"authorize {a.status_code} {a.text[:200]}"
        ad = a.json()
        tx_id = ad["transaction_id"]
        # capture (idempotent — if already captured on authorize, still 200)
        c = s.post(f"{API}/scan-to-pay/capture",
                   json={"transaction_id": tx_id}, timeout=20)
        assert c.status_code == 200, f"capture {c.status_code} {c.text[:200]}"
        return qd, ad, c.json()

    def test_tip_earns_bigcoin_on_full_points_bill(self):
        s = demo_session()
        subtotal, tip = 500, 200   # $5 subtotal + $2 tip
        qd, _ad, cap = self._run(s, subtotal, tip)
        # points_per_dollar default = 10. tip earns int(2 * 10) = 20
        assert qd["points_earned"] == 20, f"quote.points_earned expected 20, got {qd}"
        assert cap["bigcoin_earned"] == 20, f"capture.bigcoin_earned expected 20, got {cap}"
        assert cap["points_used"] == subtotal + tip

    def test_zero_tip_earns_zero_on_full_points_bill(self):
        s = demo_session()
        subtotal, tip = 500, 0
        qd, _ad, cap = self._run(s, subtotal, tip)
        assert qd["points_earned"] == 0
        assert cap["bigcoin_earned"] == 0
        assert cap["points_used"] == 500

    def test_full_card_earns_on_whole_total(self):
        """A 0-points pay would hit the Stripe path (not safe here).
        Compute via quote endpoint only (pure preview) — no authorize."""
        s = demo_session()
        tok = _gen_qr(500)
        q = s.post(f"{API}/scan-to-pay/quote",
                   json={"qr_token": tok, "points_to_use": 0, "tip_cents": 200}, timeout=20)
        assert q.status_code == 200, q.text[:200]
        qd = q.json()
        # subtotal 500 earns 50, tip 200 earns 20 → total 70 on whole total
        assert qd["card_cents"] == 700
        assert qd["points_earned"] == 70, f"expected 70, got {qd}"


# ---- WHO'S PAID TRACKER ---------------------------------------------------
class TestWhosPaidSplits:
    def test_splits_mine_default(self):
        s = demo_session()
        r = s.get(f"{API}/scan-to-pay/splits/mine", timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        items = data.get("items") or data
        assert isinstance(items, list), f"expected list, got {type(items)}: {data}"
        # Shape sanity on first item (if any)
        if items:
            it = items[0]
            assert "total_amount_cents" in it
            assert "merchant" in it and isinstance(it["merchant"], dict)
            # merchant business_name present
            assert "business_name" in it["merchant"]
            assert "shares" in it and isinstance(it["shares"], list)
            if it["shares"]:
                sh = it["shares"][0]
                for k in ("share_amount_cents", "status", "display_name"):
                    assert k in sh, f"missing {k} in share: {sh}"

    def test_splits_mine_status_partial_contains_seed(self):
        s = demo_session()
        r = s.get(f"{API}/scan-to-pay/splits/mine", params={"status": "partial"}, timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        items = data.get("items") or data
        ids = [str(it.get("id") or it.get("split_id") or "") for it in items]
        assert "bsplit_demo_whospaid" in ids, f"seeded split not found; got ids={ids}"
        it = next(x for x in items if (x.get("id") or x.get("split_id")) == "bsplit_demo_whospaid")
        assert it["total_amount_cents"] == 2000
        assert it["merchant"].get("business_name") or it["merchant"].get("name"), f"business_name/name missing: {it['merchant']}"
        shares = it["shares"]
        assert len(shares) == 2
        statuses = sorted([s["status"] for s in shares])
        assert statuses == ["paid", "pending"], f"expected [paid, pending], got {statuses}"
        # paid share has paid_at
        paid = [s for s in shares if s["status"] == "paid"][0]
        assert paid.get("paid_at")
        # amounts
        amounts = sorted([s["share_amount_cents"] for s in shares])
        assert amounts == [1000, 1000]
        # names
        names = sorted([s["display_name"] for s in shares])
        assert names == ["Alex", "You"]
