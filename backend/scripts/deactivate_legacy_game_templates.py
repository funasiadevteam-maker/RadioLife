"""Phase 23 Session 4.5b — backend remediation script.

(1) Upserts the `tpl_pick_a_card` template row so /advertiser/templates
        returns it.  Idempotent.
(2) Flips `active=False` on `tpl_slot_machine`, `tpl_memory_match`,
        `tpl_word_puzzle` so the listener-facing picker hides them.  Already-
        created campaigns of those types KEEP playing — the dispatcher in
        components/games still routes them to their respective components.
(3) Reports the resulting visible template list.

Run after `seed_games_v2` (which the bootstrap calls on every backend boot).
"""
from __future__ import annotations
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


PICK_A_CARD_ROW = {
    "template_id":            "tpl_pick_a_card",
    "game_type":                "pick_a_card",
    "name":                          "Pick a Card",
    "description":              ("Listener taps 1 of N face-down cards; "
                                              "chosen card flips to reveal the prize "
                                              "(server-decided weighted outcome)."),
    "preview_image_url":  "/static/games/pick_a_card_preview.png",
    "default_config_json": {"num_cards": 3, "flip_duration_ms": 550},
    "min_prizes": 2, "max_prizes": 6,
    "active": True, "version": 1,
}

# Phase 23 Session 7 — slot_machine RE-ACTIVATED as a listener-visible
# template (re-skinned to the uploaded design + server-resolved).  The
# legacy hide list now only contains memory_match + word_puzzle.
HIDE = ["tpl_memory_match", "tpl_word_puzzle"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    r = await db.game_templates.update_one(
        {"template_id": PICK_A_CARD_ROW["template_id"]},
        {"$set": {**PICK_A_CARD_ROW, "updated_at": now},
          "$setOnInsert": {"created_at": now}},
        upsert=True)
    if r.upserted_id:
        print(f"created tpl_pick_a_card: {r.upserted_id}")
    else:
        print("tpl_pick_a_card already present — set active=True")

    r2 = await db.game_templates.update_many(
        {"template_id": {"$in": HIDE}},
        {"$set": {"active": False}})
    print(f"deactivated {r2.modified_count}/{len(HIDE)} legacy templates")

    active = await db.game_templates.find({"active": True},
                                                                                  {"template_id": 1, "name": 1}
                                                                          ).to_list(50)
    print("Active templates now:")
    for t in active:
        print(f"  - {t['template_id']:24s} {t.get('name')}")


if __name__ == "__main__":
    asyncio.run(main())
