"""iter_210 FUUSIC: currency propagation + splits/mine merchant fix.

Verifies:
  (A) scan-to-pay resolve/quote/authorize/capture all return currency='aed'
      for biz_demo_karak (Dubai) — not 'usd'.
  (B) 100%-BigPoints capture succeeds end-to-end with card_cents=0, carries
      receipt fields, and returns currency='aed'.
  (C) Tip-earns-points regression (ppd=10): $5 subtotal + $2 tip at 100%
      BigPoints → bigcoin_earned=20 (tip-only). tip=0 → earn 0.
  (D) splits/mine returns bsplit_demo_whospaid with merchant.business_name
      = 'Karak Cafe Dubai (QA Demo)' (NOT null), currency='aed' at both
      split and merchant level, status='partial'.
"""
import os, sys, asyncio, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

sys.path.insert(0, "/app/backend")

MERCHANT_ID = "biz_demo_karak"
EMAIL = "demo@bigfm.dubai"
PASSWORD = "DemoPass123!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


async def _gen_qr(amount_cents: int) -> str:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import scan_to_pay_service as sp
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    r = await sp.generate_qr(db, merchant_id=MERCHANT_ID,
                             cashier_user_id="seed_cashier",
                             amount_cents=amount_cents)
    client.close()
    return r["token"]


def _mk_qr(amount_cents: int) -> str:
    return asyncio.get_event_loop().run_until_complete(_gen_qr(amount_cents))


# ─────────── (A) + (B) Currency propagation + 100% BigPoints flow ───────────
class TestCurrencyPropagation:

    def test_resolve_returns_aed(self, session):
        tok = _mk_qr(500)
        r = session.get(f"{BASE_URL}/api/scan-to-pay/qr/{tok}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["currency"] == "aed", f"expected aed, got {d.get('currency')}"
        assert d["merchant"]["currency"] == "aed"

    def test_quote_returns_aed(self, session):
        tok = _mk_qr(500)
        r = session.post(f"{BASE_URL}/api/scan-to-pay/quote",
                         json={"qr_token": tok, "points_to_use": 0,
                               "tip_cents": 0}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("currency") == "aed"

    def test_full_100pct_bigpoints_flow_aed(self, session):
        """Resolve → quote → authorize → capture with 100% BigPoints
        (card_cents=0 → no Stripe). All must return currency='aed'."""
        subtotal, tip = 500, 200
        tok = _mk_qr(subtotal)

        # Quote: use 100% BigPoints covering subtotal+tip
        qr = session.post(f"{BASE_URL}/api/scan-to-pay/quote",
                          json={"qr_token": tok, "points_to_use": subtotal + tip,
                                "tip_cents": tip}, timeout=15)
        assert qr.status_code == 200, qr.text
        q = qr.json()
        assert q["currency"] == "aed"
        assert q["card_cents"] == 0, f"expected card_cents=0, got {q['card_cents']}"
        # Tip earns points: ppd=10 → $2 tip = 20 BC
        assert q["points_earned"] == 20, f"tip-earn expected 20, got {q['points_earned']}"

        # Authorize
        ar = session.post(f"{BASE_URL}/api/scan-to-pay/authorize",
                          json={"qr_token": tok, "points_to_use": subtotal + tip,
                                "tip_cents": tip}, timeout=15)
        assert ar.status_code == 200, ar.text
        a = ar.json()
        assert a["currency"] == "aed", f"authorize currency: {a.get('currency')}"
        assert a["card_cents"] == 0
        tx_id = a["transaction_id"]

        # Capture
        cr = session.post(f"{BASE_URL}/api/scan-to-pay/capture",
                          json={"transaction_id": tx_id}, timeout=15)
        assert cr.status_code == 200, cr.text
        c = cr.json()
        assert c["currency"] == "aed", f"capture currency: {c.get('currency')}"
        # Receipt fields
        assert c["subtotal_cents"] == subtotal
        assert c["tip_cents"] == tip
        assert c["points_used"] == subtotal + tip
        assert c["charge_cents"] == 0
        assert c["bigcoin_earned"] == 20

    def test_tip_zero_earns_zero(self, session):
        """Regression: same bill with tip=0 earns 0 BC (points cover all)."""
        subtotal = 500
        tok = _mk_qr(subtotal)
        qr = session.post(f"{BASE_URL}/api/scan-to-pay/quote",
                          json={"qr_token": tok,
                                "points_to_use": subtotal,
                                "tip_cents": 0}, timeout=15)
        assert qr.status_code == 200
        q = qr.json()
        assert q["card_cents"] == 0
        assert q["points_earned"] == 0, f"expected 0, got {q['points_earned']}"


# ─────────── (D) splits/mine merchant + currency ───────────
class TestSplitsMine:

    def test_splits_mine_merchant_and_currency(self, session):
        r = session.get(f"{BASE_URL}/api/scan-to-pay/splits/mine?status=partial",
                        timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("items") or body.get("splits") or []
        seeded = [x for x in items
                  if x.get("split_id") == "bsplit_demo_whospaid"]
        assert seeded, f"bsplit_demo_whospaid not found in {len(items)} items"
        sp = seeded[0]

        # Currency at split level
        assert sp.get("currency") == "aed", \
            f"split currency: {sp.get('currency')}"

        # Merchant block
        m = sp.get("merchant") or {}
        assert m.get("business_name") == "Karak Cafe Dubai (QA Demo)", \
            f"business_name: {m.get('business_name')!r}"
        assert m.get("category") == "cafe", f"category: {m.get('category')!r}"
        assert m.get("currency") == "aed", \
            f"merchant currency: {m.get('currency')!r}"

        # Status
        assert sp.get("status") == "partial"

        # Shares: You/paid + Alex/pending
        shares = sp.get("shares") or []
        assert len(shares) == 2
        statuses = {s.get("display_name"): s.get("status") for s in shares}
        assert statuses.get("You") == "paid"
        assert statuses.get("Alex") in ("invited", "claimed", "pending")
