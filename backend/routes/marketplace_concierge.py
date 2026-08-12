"""AI Ordering Concierge (Phase F seed) — natural-language ordering that
understands memberships. Given a request like "use my Pizza Club to order a
large pepperoni tonight", Gemini 3 Flash maps it to a concrete menu item +
options + membership entitlement, and we re-price it authoritatively via the
menu pricing engine before proposing the order for the user to confirm."""
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from auth import current_user
from routes.marketplace_orders import CheckoutItem, _price_menu
from services.membership_entitlements import entitlement_remaining, day_time_allows

load_dotenv()

router = APIRouter(prefix="/api/shop/concierge", tags=["marketplace-concierge"])

SYSTEM = (
    "You are RadioLife's ordering concierge. The user has memberships at one or more "
    "venues. You are given, as JSON, the user's request plus each venue's menu (items "
    "with ids, prices, and option groups whose options have ids) and the user's usable "
    "membership entitlements at that venue.\n"
    "Choose exactly ONE item to order that best matches the request. Respond with STRICT "
    "JSON only (no markdown), shape:\n"
    '{"business_id": str, "item_id": str, "apply_entitlement_id": str|null, '
    '"selected_option_ids": [str], "qty": int, "message": str, "need_clarification": bool}\n'
    "Rules: use ONLY ids that appear in the context. If the user references a membership/club "
    "or asks for something 'free', set apply_entitlement_id to the matching entitlement_id. "
    "For size/single option groups pick exactly one option (default if unstated); for the "
    "requested upgrades (e.g. 'large', 'extra cheese') pick the matching option ids. If nothing "
    "reasonably matches or it's ambiguous, set need_clarification=true, leave item_id empty, and "
    "put a short friendly question in message. Keep message under 240 characters, warm and concise."
)


class ConciergeBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


async def _build_context(db, user) -> List[Dict[str, Any]]:
    uid = user.get("user_id")
    email = (user.get("email") or "").lower().strip()
    ors: List[Dict[str, Any]] = [{"user_id": uid}]
    if email:
        ors.append({"gifted_to_email": email})
    biz_ids: Dict[str, str] = {}
    ent_by_biz: Dict[str, List[Dict[str, Any]]] = {}
    async for m in db.memberships.find({"status": "active", "$or": ors}):
        bid = m.get("business_id")
        if not bid:
            continue
        biz_ids.setdefault(bid, m.get("sponsor_name") or "")
        plan = await db.membership_plans.find_one({"plan_id": m.get("plan_id")})
        for e in (plan or {}).get("entitlements", []):
            if not e.get("active", True):
                continue
            rem = await entitlement_remaining(db, m, e)
            if rem["remaining"] <= 0 or not day_time_allows(e.get("day_time")):
                continue
            ent_by_biz.setdefault(bid, []).append({
                "entitlement_id": e.get("entitlement_id"), "label": e.get("label"),
                "target_type": e.get("target_type"), "category": e.get("category"),
                "target_ids": e.get("target_ids", []), "remaining": rem["remaining"]})
    ctx = []
    for bid, sponsor in biz_ids.items():
        if not sponsor:
            prof = await db.marketplace_profiles.find_one({"business_id": bid}, {"public_name": 1})
            sponsor = (prof or {}).get("public_name") or ""
        menu = []
        async for it in db.menu_items.find({"business_id": bid, "available": True}).limit(50):
            menu.append({
                "item_id": it["item_id"], "name": it.get("name"),
                "category": it.get("section"), "price_cents": it.get("price_cents", 0),
                "option_groups": [{
                    "name": g.get("name"), "type": g.get("type"),
                    "options": [{"id": o.get("option_id"), "label": o.get("label"),
                                 "delta_cents": o.get("price_delta_cents", 0)} for o in g.get("options", [])],
                } for g in (it.get("option_groups") or [])],
            })
        ctx.append({"business_id": bid, "business_name": sponsor, "menu": menu,
                    "my_entitlements": ent_by_biz.get(bid, [])})
    return ctx


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        return json.loads(t[a:b + 1])
    except Exception:
        return None


@router.post("")
async def concierge(body: ConciergeBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    ctx = await _build_context(db, user)
    if not ctx:
        return {"ok": False, "message": "You don't have any active memberships yet — join a venue's "
                "club and I'll help you order your perks by chat."}

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(500, {"code": "llm_key_missing"})
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=key, session_id=f"concierge_{user.get('user_id')}",
                   system_message=SYSTEM).with_model("gemini", "gemini-3-flash-preview")
    payload = json.dumps({"request": body.text, "venues": ctx})
    try:
        raw = await chat.send_message(UserMessage(text=payload))
    except Exception:
        raise HTTPException(502, {"code": "concierge_unavailable"})
    parsed = _parse_json(raw if isinstance(raw, str) else str(raw))
    if not parsed:
        return {"ok": False, "message": "Sorry, I didn't catch that. Try naming the item and your club, "
                "e.g. \u201cuse my Pizza Club for a large pepperoni\u201d."}

    if parsed.get("need_clarification") or not parsed.get("item_id"):
        return {"ok": False, "message": parsed.get("message") or "Could you tell me which item you'd like?"}

    bid = parsed.get("business_id")
    venue = next((v for v in ctx if v["business_id"] == bid), None)
    item = next((i for i in (venue or {}).get("menu", []) if i["item_id"] == parsed.get("item_id")), None)
    if not venue or not item:
        return {"ok": False, "message": parsed.get("message") or "I couldn't find that on your menus — mind rephrasing?"}

    valid_opts = {o["id"] for g in item["option_groups"] for o in g["options"]}
    sel = [o for o in (parsed.get("selected_option_ids") or []) if o in valid_opts]
    # ensure required size/single groups have a pick (default) so pricing passes
    for g in item["option_groups"]:
        if g["type"] in ("size", "single"):
            if not any(o["id"] in sel for o in g["options"]) and g["options"]:
                sel.append(g["options"][0]["id"])
    ent_id = parsed.get("apply_entitlement_id") or None
    qty = max(1, min(int(parsed.get("qty") or 1), 20))

    try:
        q = await _price_menu(db, user, bid, [CheckoutItem(
            item_id=item["item_id"], qty=qty, selected_option_ids=sel,
            apply_entitlement_id=ent_id)], use_gift_card=False, redeem_points=0)
    except HTTPException:
        # entitlement not applicable — re-price without it so we still propose the order
        ent_id = None
        q = await _price_menu(db, user, bid, [CheckoutItem(
            item_id=item["item_id"], qty=qty, selected_option_ids=sel)],
            use_gift_card=False, redeem_points=0)

    line = q["line_items"][0]
    opt_summary = ", ".join(o["label"] for o in line.get("selected_options", [])) or None
    ent_label = None
    if ent_id:
        ent_label = next((e["label"] for e in venue["my_entitlements"] if e["entitlement_id"] == ent_id), None)
    return {
        "ok": True,
        "message": parsed.get("message") or f"Here's your {item['name']} — ready when you are.",
        "proposal": {
            "business_id": bid, "business_name": venue["business_name"],
            "item_id": item["item_id"], "name": item["name"], "qty": qty,
            "selected_option_ids": sel, "option_summary": opt_summary,
            "unit_price_cents": line["price_cents"],
            "apply_entitlement_id": ent_id, "entitlement_label": ent_label,
            "entitlement_discount_cents": q.get("entitlement_discount_cents", 0),
            "subtotal_cents": q["subtotal_cents"], "total_cents": q["total_cents"],
        },
    }


__all__ = ["router"]
