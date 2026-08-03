"""Phase PW-M.1 — Initialize the 6 new Merchant Predict & Win collections.

Idempotent.  Called at server boot (see server.py bootstrap) and can be
re-run standalone.  All indexes are created with `if not exists` semantics
(Mongo returns success if the index already exists with the same key
pattern + options)."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bigfm.pw_m.init")


async def init_collections(db) -> dict:
    """Create the 6 merchant Predict & Win collections + indexes.

    Returns a report dict for the caller to log."""
    report = {"created_indexes": [], "errors": []}

    # 1. merchant_prediction_preferences  (one row per merchant)
    try:
        await db.merchant_prediction_preferences.create_index(
            "merchant_id", unique=True, name="mpp_merchant_id_unique")
        report["created_indexes"].append(
            "merchant_prediction_preferences.merchant_id (unique)")
    except Exception as e:
        report["errors"].append(f"mpp:{e}")

    # 2. merchant_prize_inventory  (many per merchant)
    for keys, opts, label in [
        ([("merchant_id", 1), ("active", 1)],  {},  "mpi_merchant_active"),
        ([("merchant_id", 1), ("location_id", 1)],  {},  "mpi_merchant_location"),
        ([("prize_id", 1)],                            {"unique": True},  "mpi_prize_id_unique"),
    ]:
        try:
            await db.merchant_prize_inventory.create_index(keys, name=label, **opts)
            report["created_indexes"].append(f"merchant_prize_inventory.{label}")
        except Exception as e:
            report["errors"].append(f"mpi:{label}:{e}")

    # 3. merchant_predict_win_campaigns  (child campaigns)
    for keys, opts, label in [
        ([("campaign_id", 1)],                                                    {"unique": True},   "mpwc_campaign_id_unique"),
        ([("merchant_id", 1), ("campaign_status", 1)],  {},  "mpwc_merchant_status"),
        ([("parent_predict_win_campaign_id", 1),
          ("campaign_status", 1)],                                            {},  "mpwc_parent_status"),
        ([("approval_status", 1), ("updated_at", -1)],  {},  "mpwc_approval_queue"),
    ]:
        try:
            await db.merchant_predict_win_campaigns.create_index(keys, name=label, **opts)
            report["created_indexes"].append(f"merchant_predict_win_campaigns.{label}")
        except Exception as e:
            report["errors"].append(f"mpwc:{label}:{e}")

    # 4. merchant_predict_win_entries  (links customer entry → merchant campaign)
    for keys, opts, label in [
        ([("entry_id", 1)],                                                                                                          {"unique": True}, "mpwe_id_unique"),
        ([("merchant_campaign_id", 1), ("user_id", 1)],                              {"unique": True}, "mpwe_mc_user_unique"),
        ([("parent_predict_win_entry_id", 1), ("merchant_campaign_id", 1)],  {},  "mpwe_pe_mc"),
    ]:
        try:
            await db.merchant_predict_win_entries.create_index(keys, name=label, **opts)
            report["created_indexes"].append(f"merchant_predict_win_entries.{label}")
        except Exception as e:
            report["errors"].append(f"mpwe:{label}:{e}")

    # 5. merchant_predict_win_awards  (award ledger — one row per (campaign, winner))
    for keys, opts, label in [
        ([("award_id", 1)],                                                                        {"unique": True}, "mpwa_id_unique"),
        ([("merchant_campaign_id", 1), ("award_status", 1)],  {},  "mpwa_mc_status"),
        ([("user_id", 1)],                                                                        {},  "mpwa_user"),
        ([("wallet_item_id", 1)],                                                          {},  "mpwa_wallet_item"),
    ]:
        try:
            await db.merchant_predict_win_awards.create_index(keys, name=label, **opts)
            report["created_indexes"].append(f"merchant_predict_win_awards.{label}")
        except Exception as e:
            report["errors"].append(f"mpwa:{label}:{e}")

    # 6. merchant_predict_win_analytics  (event log; TTL-managed at 180d)
    for keys, opts, label in [
        ([("merchant_campaign_id", 1), ("event_type", 1), ("created_at", -1)],  {},  "mpwan_mc_type_time"),
        ([("created_at", 1)],  {"expireAfterSeconds": 60 * 60 * 24 * 180},              "mpwan_ttl_180d"),
    ]:
        try:
            await db.merchant_predict_win_analytics.create_index(keys, name=label, **opts)
            report["created_indexes"].append(f"merchant_predict_win_analytics.{label}")
        except Exception as e:
            report["errors"].append(f"mpwan:{label}:{e}")

    return report


async def _cli():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    logging.basicConfig(level=logging.INFO)
    r = await init_collections(db)
    print(f"Created {len(r['created_indexes'])} indexes; errors={len(r['errors'])}")
    for i in r["created_indexes"]:
        print(f"  + {i}")
    for e in r["errors"]:
        print(f"  ! {e}")


if __name__ == "__main__":
    asyncio.run(_cli())
