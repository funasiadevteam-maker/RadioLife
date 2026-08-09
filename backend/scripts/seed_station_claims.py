"""Phase 42-C — Seed two test station claims so the tester always has
known IDs to operate on.

Fixture 1: `pra_verifying_<token>` — `verifying` state, email_domain
            method, fresh verification_token available in the mocked_emails
            collection.  Tester completes by POSTing to
            `/api/radio/claims/verify/<token>`.

Fixture 2: `pra_submitted_admin_<id>` — `submitted` state, manual_admin
            method.  Tester approves/rejects via the admin queue.

Both claims target real `imp_*` stations from the 58K catalog.

Idempotent.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


async def _pick_station(db, *, with_homepage: bool, homepage_domain_hint=None):
    """Find a real `imp_*` station that's unclaimed.  When
    `with_homepage=True` we restrict to rows whose `homepage` field is a
    real URL so the email-domain auto-match flow has a target."""
    q = {"active": True,
              "$or": [{"claim_status": "unclaimed"},
                          {"claim_status": {"$exists": False}}]}
    if with_homepage:
        q["homepage"] = {"$regex": r"^https?://", "$options": "i"}
    if homepage_domain_hint:
        q["homepage"] = {"$regex": homepage_domain_hint, "$options": "i"}
    s = await db.imported_radio_stations.find_one(q,
                                                                                                            sort=[("votes", -1)])
    return s


async def _ensure_claim(db, *, station, contact_email, contact_role,
                                              organization_name, owner_email,
                                              verification_method):
    """Idempotent insert: if a fixture claim for this station + owner +
    method already exists in a non-finalized state, refresh it; else
    insert a new one."""
    owner = await db.users.find_one({"email": owner_email})
    if not owner:
        raise RuntimeError(f"owner user {owner_email} not found")
    user_id = owner["user_id"]

    existing = await db.radio_station_claims.find_one({
        "station_id": station["id"],
        "claimed_by_user_id": user_id,
        "verification_method": verification_method,
        "claim_status": {"$in": ["submitted", "verifying"]},
    })
    now = _now()
    if existing:
        # Reuse existing — refresh status fields + bump updated_at.
        await db.radio_station_claims.update_one(
            {"id": existing["id"]},
            {"$set": {"contact_email": contact_email,
                              "contact_role": contact_role,
                              "organization_name": organization_name,
                              "updated_at": now}})
        return existing["id"], existing["verification_token"], "refreshed"

    claim_id = _new_id("rsc")
    token = uuid.uuid4().hex
    if verification_method == "email_domain":
        verification_status = "email_sent"
        claim_status = "verifying"
        admin_review_status = "not_required"
    else:
        verification_status = "pending"
        claim_status = "submitted"
        admin_review_status = "pending"
    await db.radio_station_claims.insert_one({
        "_id": claim_id, "id": claim_id,
        "station_id": station["id"],
        "station_name_snapshot": station.get("name"),
        "station_homepage_snapshot": station.get("homepage"),
        "claimed_by_user_id": user_id,
        "claimed_by_email": owner.get("email"),
        "organization_name": organization_name,
        "contact_email": contact_email,
        "contact_role": contact_role,
        "verification_method": verification_method,
        "verification_status": verification_status,
        "verification_token": token,
        "verification_attempted_at": now,
        "verification_completed_at": None,
        "agreement_status": "signed",
        "agreement_signed_at": now,
        "agreement_version": "v1.0",
        "admin_review_status": admin_review_status,
        "admin_reviewer_id": None,
        "admin_reviewed_at": None,
        "admin_rejection_reason": None,
        "claim_status": claim_status,
        "created_at": now, "updated_at": now,
    })
    # Stamp station as claim_pending.
    await db.imported_radio_stations.update_one(
        {"id": station["id"]},
        {"$set": {"claim_status": "claim_pending"}})

    # For email_domain method also log the mocked email so the tester
    # can read the token without depending on the live endpoint.
    if verification_method == "email_domain":
        base = (os.environ.get("BIGFM_PUBLIC_BASE_URL")
                      or os.environ.get("REACT_APP_BACKEND_URL")
                      or "https://app.bigfantv.com")
        link = f"{base.rstrip('/')}/claim/verify/{token}"
        await db.mocked_emails.insert_one({
            "_id": _new_id("memail"),
            "provider": "mocked",
            "to": contact_email,
            "subject": f"Verify your ownership of {station.get('name')} on RadioLife",
            "html": (f"<p>Confirm by clicking:</p>"
                              f"<p><a href='{link}'>{link}</a></p>"),
            "tags": ["station_claim", "verification", "seed"],
            "claim_id": claim_id,
            "verification_token": token,
            "created_at": now,
        })
    return claim_id, token, "created"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # FIXTURE 1 — verifying / email_domain.
    # Pick a station with a real homepage.  Use that homepage's domain
    # as the contact_email's domain so the matcher takes the email path.
    s1 = await _pick_station(db, with_homepage=True)
    if s1 is None:
        print("ERROR: no unclaimed station with homepage available",
                    file=sys.stderr)
        client.close()
        sys.exit(2)
    # Build matching contact_email from the homepage.
    from services.station_claim_service import derive_homepage_domain
    domain = derive_homepage_domain(s1) or "example.com"
    email1 = f"manager@{domain}"
    cid1, tok1, action1 = await _ensure_claim(
        db, station=s1,
        contact_email=email1,
        contact_role="Station Manager",
        organization_name=f"{s1.get('name')} Inc.",
        owner_email="demo@bigfm.dubai",
        verification_method="email_domain")
    print(f"fixture_1_verifying:")
    print(f"  claim_id={cid1}")
    print(f"  station_id={s1['id']}")
    print(f"  station_name={s1.get('name')}")
    print(f"  homepage={s1.get('homepage')}")
    print(f"  contact_email={email1}")
    print(f"  verification_token={tok1}")
    print(f"  status={action1}")

    # FIXTURE 2 — submitted / manual_admin.
    # Pick a different station; use a gmail contact so domain doesn't
    # match the homepage.
    s2 = await _pick_station(db, with_homepage=True,
                                                                  homepage_domain_hint=r"^(?!.*" + (
                                                                      derive_homepage_domain(s1) or "")
                                                                      + r")")
    # Fallback: just take the next top-voted station.
    if s2 is None or s2["id"] == s1["id"]:
        async for cand in db.imported_radio_stations.find(
                {"active": True, "id": {"$ne": s1["id"]},
                  "$or": [{"claim_status": "unclaimed"},
                                  {"claim_status": {"$exists": False}}]}) \
                .sort("votes", -1).limit(5):
            s2 = cand
            break
    if s2 is None:
        print("ERROR: no second station available", file=sys.stderr)
        client.close()
        sys.exit(2)
    email2 = "fan.claim@gmail.com"
    cid2, tok2, action2 = await _ensure_claim(
        db, station=s2,
        contact_email=email2,
        contact_role="Owner",
        organization_name=f"{s2.get('name')} Group",
        owner_email="predictest@bigfm.dubai",
        verification_method="manual_admin")
    print(f"fixture_2_submitted_admin:")
    print(f"  claim_id={cid2}")
    print(f"  station_id={s2['id']}")
    print(f"  station_name={s2.get('name')}")
    print(f"  homepage={s2.get('homepage')}")
    print(f"  contact_email={email2}")
    print(f"  status={action2}")

    print("\nmocked_emails collection — verification tokens live there.")
    print("Tester reads via: db.mocked_emails.find({tags: 'station_claim'})")
    client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
