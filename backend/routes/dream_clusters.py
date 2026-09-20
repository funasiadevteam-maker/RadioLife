"""RadioLife Social V2 — DREAM CLUSTERS + COMPATIBILITY.

Clusters: Claude maps each shared dream to normalized themes (Falling,
Being Chased, Water …); the Clusters view groups public dreams by theme so
people instantly find others who dreamed the same thing.

Compatibility: a PLAYFUL, entertainment-only score between two people based
on their shared dream themes + star signs. Never a real relationship claim.
"""
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from auth import current_user, current_user_optional
from routes.social_v2 import _friend_ids, _user_public
from routes.dreams_guidance import _dream_public
from services.object_storage import get_storage

router = APIRouter(prefix="/api/social", tags=["dream_clusters"])

DISCLAIMER = ("Playful and AI-generated for entertainment only — not a real "
              "compatibility, psychological or relationship assessment.")

# Normalized dream-theme taxonomy (key -> label). Kept small + universal.
THEMES = [
    ("falling", "Falling"), ("being_chased", "Being Chased"),
    ("flying", "Flying"), ("teeth", "Teeth Falling Out"),
    ("water", "Water & Ocean"), ("tests", "Exams & Tests"),
    ("naked", "Unprepared / Exposed"), ("late", "Running Late"),
    ("lost", "Lost or Searching"), ("death", "Death & Endings"),
    ("house", "Houses & Rooms"), ("animals", "Animals"),
    ("travel", "Travel & Journeys"), ("money", "Money & Work"),
    ("romance", "Love & Reunion"), ("family", "Family"),
    ("nature", "Nature & Sky"), ("supernatural", "Supernatural"),
    ("conflict", "Conflict & Fear"), ("rebirth", "Rebirth & Hope"),
]
THEME_LABELS = {k: v for k, v in THEMES}
THEME_KEYS = [k for k, _ in THEMES]

_THEME_SYSTEM = (
    "You label dreams with themes for a social app. Given a dream, pick the 1-4 "
    "BEST-matching theme keys from this fixed list (return keys only, no new ones): "
    + ", ".join(THEME_KEYS)
    + ". Return ONLY compact JSON, no markdown: {\"themes\": [\"key\", ...]}.")

_COMPAT_SYSTEM = (
    "You write SHORT, playful, uplifting 'dream compatibility' blurbs for a social "
    "app — pure entertainment, like a magazine quiz. Rules: (1) never claim it is a "
    "real relationship, psychological or medical assessment; (2) be warm, kind and "
    "light; (3) never predict breakups, health or the future. Return ONLY compact "
    "JSON: {\"headline\": str, \"blurb\": str, \"shared_note\": str}.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


# ══════════════════ Match Card Art (AI bg + composited text) ═══════
# Gemini Nano Banana paints a dreamy background; Pillow composites the
# crisp branded card text on top; the PNG is stored in object storage
# and served from a stable public URL for og:image previews + downloads.
_CARD_W, _CARD_H = 1200, 630
_F_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_F_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_F_NARROW = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"


def _card_key(card_id: str) -> str:
    return f"social/match_cards/{card_id}.png"


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host}"


def _card_image_url(request: Request, card_id: str) -> str:
    return f"{_base_url(request)}/api/social/compatibility/card/{card_id}/image.png"


async def _dreamy_bg() -> Optional[bytes]:
    """Best-effort dreamy background via Gemini Nano Banana. None on failure."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import base64
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=f"matchbg_{uuid.uuid4().hex[:8]}",
                       system_message="You are an artistic background image generator.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"])
        msg = UserMessage(text=(
            "A dreamy ethereal cosmic background for a romantic 'dream match' card: "
            "soft violet, magenta and indigo nebula clouds, gentle glowing stars, "
            "celestial haze and bokeh light, calm and magical. Abstract, no text, "
            "no letters, no people, no faces. Wide cinematic composition, high quality."))
        _text, images = await chat.send_message_multimodal_response(msg)
        if images:
            return base64.b64decode(images[0]["data"])
    except Exception:
        return None
    return None


def _grad_bg():
    from PIL import Image
    img = Image.new("RGB", (_CARD_W, _CARD_H))
    c0, c1 = (46, 16, 101), (190, 24, 93)  # violet → rose
    px = img.load()
    for y in range(_CARD_H):
        t = y / max(1, _CARD_H - 1)
        row = (int(c0[0] * (1 - t) + c1[0] * t),
               int(c0[1] * (1 - t) + c1[1] * t),
               int(c0[2] * (1 - t) + c1[2] * t))
        for x in range(_CARD_W):
            px[x, y] = row
    return img


def _draw_heart(draw, cx, cy, size, color):
    r = size / 4.0
    draw.pieslice([cx - 2 * r, cy - r, cx, cy + r], 180, 360, fill=color)
    draw.pieslice([cx, cy - r, cx + 2 * r, cy + r], 180, 360, fill=color)
    draw.polygon([(cx - 2 * r, cy), (cx + 2 * r, cy), (cx, cy + 2 * r)], fill=color)


def _font(path, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def _compose_card(card: dict, bg_bytes: Optional[bytes]) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter
    W, H = _CARD_W, _CARD_H
    canvas = None
    if bg_bytes:
        try:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
            scale = max(W / bg.width, H / bg.height)
            bg = bg.resize((max(1, int(bg.width * scale)),
                            max(1, int(bg.height * scale))), Image.LANCZOS)
            l = (bg.width - W) // 2
            t = (bg.height - H) // 2
            canvas = bg.crop((l, t, l + W, t + H))
        except Exception:
            canvas = None
    if canvas is None:
        canvas = _grad_bg()

    # Darken + vignette so the crisp text always reads.
    overlay = Image.new("RGBA", (W, H), (10, 6, 30, 150))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    cx = W // 2

    gold = (251, 191, 36)
    white = (255, 255, 255)
    rose = (251, 113, 133)
    soft = (245, 224, 235)

    # Eyebrow
    eb = _font(_F_NARROW, 26)
    draw.text((cx, 66), "RADIOLIFE  ·  DREAM MATCH", font=eb, fill=gold, anchor="mm")

    # Names with a heart between them.
    owner = (card.get("owner_name") or "You")[:22]
    target = (card.get("target_name") or "Friend")[:22]
    nf = _font(_F_BOLD, 46)
    ow = draw.textlength(owner, font=nf)
    tw = draw.textlength(target, font=nf)
    heart_w, gap = 46, 26
    total = ow + gap + heart_w + gap + tw
    x = cx - total / 2
    name_y = 132
    draw.text((x, name_y), owner, font=nf, fill=white, anchor="lm")
    hx = x + ow + gap + heart_w / 2
    _draw_heart(draw, hx, name_y, heart_w, rose)
    draw.text((x + ow + gap + heart_w + gap, name_y), target, font=nf,
              fill=white, anchor="lm")

    # Hero score.
    sf = _font(_F_BOLD, 168)
    draw.text((cx, 300), f"{int(card.get('score') or 0)}%", font=sf,
              fill=white, anchor="mm")

    # Headline (single line, trimmed).
    hf = _font(_F_BOLD, 36)
    head = (card.get("headline") or "Dream sync ✨")[:46]
    draw.text((cx, 420), head, font=hf, fill=soft, anchor="mm")

    # Shared themes chips (centered text row).
    themes = (card.get("shared_themes") or [])[:4]
    if themes:
        cf = _font(_F_REG, 24)
        label = "  ·  ".join(str(t) for t in themes)[:70]
        draw.text((cx, 470), label, font=cf, fill=(214, 211, 232), anchor="mm")

    # Signs line.
    signs = " · ".join([s for s in [card.get("my_sign"), card.get("their_sign")] if s])
    if signs:
        gf = _font(_F_REG, 22)
        draw.text((cx, 512), signs[:60], font=gf, fill=(196, 181, 253), anchor="mm")

    # Footer disclaimer.
    ff = _font(_F_NARROW, 22)
    draw.text((cx, H - 44), "PLAYFUL · AI-GENERATED · ENTERTAINMENT ONLY",
              font=ff, fill=(190, 170, 210), anchor="mm")

    _ = ImageFilter  # keep import used if optimizer prunes
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _storage_read(key: str) -> Optional[bytes]:
    try:
        st = get_storage()
        if not st.exists(key=key):
            return None
        h = st.head(key=key)
        size = int((h or {}).get("size") or 0)
        if size <= 0:
            return None
        return st.open_range(key=key, start=0, end=size - 1)
    except Exception:
        return None


async def _ensure_card_image(db, card: dict) -> Optional[str]:
    """Generate (if missing) + persist the match-card PNG. Returns storage key."""
    card_id = card["card_id"]
    key = _card_key(card_id)
    try:
        st = get_storage()
        if st.exists(key=key):
            return key
        bg = await _dreamy_bg()
        png = _compose_card(card, bg)
        st.upload_bytes(key=key, data=png, content_type="image/png")
        await db.compat_cards.update_one(
            {"card_id": card_id},
            {"$set": {"image_key": key, "has_art": True,
                      "art_ai": bool(bg), "art_at": _now()}})
        return key
    except Exception:
        return None


async def _llm(system: str, prompt: str, session: str) -> Optional[dict]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=prompt))
        s = raw if isinstance(raw, str) else str(raw)
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            return json.loads(s[a:b + 1])
    except Exception:
        return None
    return None


def _keyword_themes(text: str) -> list:
    """Cheap fallback if the LLM is unavailable."""
    t = (text or "").lower()
    hits = []
    table = {
        "falling": ["fall", "falling", "cliff"], "being_chased": ["chase", "chased", "running from"],
        "flying": ["fly", "flying", "float"], "teeth": ["teeth", "tooth"],
        "water": ["ocean", "sea", "water", "flood", "wave", "river", "swim"],
        "tests": ["exam", "test", "school", "class"], "naked": ["naked", "undressed"],
        "late": ["late", "missed", "train", "flight"], "lost": ["lost", "searching", "maze"],
        "death": ["death", "died", "dying", "funeral"], "house": ["house", "room", "home"],
        "animals": ["dog", "cat", "snake", "bird", "animal"], "travel": ["travel", "journey", "road", "car"],
        "money": ["money", "work", "job", "boss"], "romance": ["love", "kiss", "ex", "reunion"],
        "family": ["mother", "father", "family", "child"], "nature": ["sky", "forest", "mountain", "star"],
        "supernatural": ["ghost", "spirit", "magic", "demon"], "conflict": ["fight", "afraid", "fear", "scared"],
        "rebirth": ["light", "hope", "born", "new"],
    }
    for key, words in table.items():
        if any(w in t for w in words):
            hits.append(key)
    return hits[:4]


async def extract_and_store_themes(db, dream_id: str) -> list:
    """Best-effort: assign normalized themes to a dream (called in background)."""
    d = await db.dreams.find_one({"_id": dream_id})
    if not d or d.get("themes"):
        return (d or {}).get("themes", [])
    text = f"{d.get('title') or ''}\n{d.get('description') or ''}".strip()
    res = await _llm(_THEME_SYSTEM, f"Dream:\n{text}", f"themes_{dream_id}")
    themes = []
    if isinstance(res, dict):
        themes = [k for k in (res.get("themes") or []) if k in THEME_KEYS]
    if not themes:
        themes = _keyword_themes(text)
    themes = themes[:4]
    await db.dreams.update_one({"_id": dream_id}, {"$set": {"themes": themes}})
    try:  # cluster alerts: ping followers of these themes (skip the author)
        if d.get("visibility") == "public" and themes:
            await _fanout_cluster_alerts(db, d, themes)
    except Exception:
        pass
    return themes


async def _fanout_cluster_alerts(db, dream: dict, themes: list) -> None:
    author = dream.get("user_id")
    notified: set = set()
    for t in themes:
        async for f in db.cluster_follows.find({"theme": t}).limit(500):
            uid = f.get("user_id")
            if not uid or uid == author or uid in notified:
                continue
            notified.add(uid)
            aid = f"al_{uuid.uuid4().hex[:14]}"
            await db.dream_alerts.insert_one({
                "_id": aid, "user_id": uid, "type": "cluster", "theme": t,
                "theme_label": THEME_LABELS.get(t, t), "dream_id": dream["_id"],
                "title": dream.get("title") or "A new dream", "read": False,
                "created_at": _now()})


async def _my_theme_follows(db, uid: str) -> set:
    return {f["theme"] async for f in db.cluster_follows.find({"user_id": uid})}


async def ensure_clusters_ai_indexes(db) -> None:
    await db.dreams.create_index([("themes", 1)], name="dreams_themes")
    await db.cluster_follows.create_index([("theme", 1)], name="cf_theme")
    await db.cluster_follows.create_index([("user_id", 1)], name="cf_user")
    await db.dream_alerts.create_index([("user_id", 1), ("read", 1),
                                        ("created_at", -1)], name="alerts_user")
    await db.compat_cards.create_index("card_id", unique=True, name="compat_card")
    # Backfill themes for a handful of public dreams that don't have any yet.
    cursor = db.dreams.find(
        {"status": "active", "visibility": "public",
         "themes": {"$exists": False}}).limit(40)
    ids = [d["_id"] async for d in cursor]
    for did in ids:
        try:
            await extract_and_store_themes(db, did)
        except Exception:
            pass


# ───────────────────────────── Clusters ────────────────────────────
@router.get("/clusters")
async def clusters(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    pipeline = [
        {"$match": {"status": "active", "visibility": "public",
                    "themes": {"$exists": True, "$ne": []}}},
        {"$unwind": "$themes"},
        {"$group": {"_id": "$themes", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    counts = {row["_id"]: row["count"] async for row in db.dreams.aggregate(pipeline)}
    follows = await _my_theme_follows(db, user["user_id"])
    out = []
    for key in sorted(counts, key=lambda k: counts[k], reverse=True):
        if key not in THEME_LABELS:
            continue
        samples = []
        async for d in db.dreams.find(
                {"status": "active", "visibility": "public", "themes": key}
        ).sort("similar_count", -1).limit(3):
            author = None
            if not d.get("anonymous"):
                au = await db.users.find_one({"user_id": d["user_id"]})
                author = _user_public(au) if au else None
            samples.append(_dream_public(d, user["user_id"], author))
        out.append({"theme": key, "label": THEME_LABELS[key],
                    "count": counts[key], "following": key in follows,
                    "samples": samples})
    return {"clusters": out}


@router.get("/clusters/{theme}")
async def cluster_dreams(theme: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    if theme not in THEME_LABELS:
        raise HTTPException(404, {"code": "unknown_theme"})
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    q = {"status": "active", "themes": theme,
         "$or": [{"visibility": "public"},
                 {"visibility": "friends", "user_id": {"$in": list(friends) + [uid]}},
                 {"user_id": uid}]}
    rows = []
    author_ids = set()
    async for d in db.dreams.find(q).sort("created_at", -1).limit(60):
        rows.append(d)
        if not d.get("anonymous") or d.get("user_id") == uid:
            author_ids.add(d["user_id"])
    authors = {}
    if author_ids:
        async for u in db.users.find({"user_id": {"$in": list(author_ids)}}):
            authors[u["user_id"]] = _user_public(u)
    return {"theme": theme, "label": THEME_LABELS[theme],
            "following": theme in await _my_theme_follows(db, uid),
            "items": [_dream_public(d, uid, authors.get(d["user_id"])) for d in rows]}


# ─────────────────────── Cluster follows + alerts ──────────────────
@router.post("/clusters/{theme}/follow")
async def follow_cluster(theme: str, request: Request,
                         user: dict = Depends(current_user)):
    if theme not in THEME_LABELS:
        raise HTTPException(404, {"code": "unknown_theme"})
    db = request.app.state.db
    await db.cluster_follows.update_one(
        {"_id": f"{theme}:{user['user_id']}"},
        {"$set": {"theme": theme, "user_id": user["user_id"], "created_at": _now()}},
        upsert=True)
    return {"ok": True, "following": True}


@router.delete("/clusters/{theme}/follow")
async def unfollow_cluster(theme: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.cluster_follows.delete_one({"_id": f"{theme}:{user['user_id']}"})
    return {"ok": True, "following": False}


@router.get("/alerts")
async def my_alerts(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = []
    async for a in db.dream_alerts.find(
            {"user_id": user["user_id"]}).sort("created_at", -1).limit(50):
        items.append({"id": a["_id"], "type": a.get("type"), "theme": a.get("theme"),
                      "theme_label": a.get("theme_label"), "dream_id": a.get("dream_id"),
                      "title": a.get("title"), "read": bool(a.get("read")),
                      "created_at": _iso(a.get("created_at"))})
    unread = await db.dream_alerts.count_documents(
        {"user_id": user["user_id"], "read": False})
    return {"items": items, "unread": unread}


@router.get("/alerts/unread_count")
async def alerts_unread(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return {"unread": await db.dream_alerts.count_documents(
        {"user_id": user["user_id"], "read": False})}


class AlertReadBody(BaseModel):
    alert_id: Optional[str] = None


@router.post("/alerts/read")
async def alerts_read(body: AlertReadBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"user_id": user["user_id"]}
    if body.alert_id:
        q["_id"] = body.alert_id
    await db.dream_alerts.update_many(q, {"$set": {"read": True}})
    return {"ok": True}


# ─────────────────────────── Compatibility ─────────────────────────
async def _user_themes(db, uid: str) -> list:
    themes: dict = {}
    async for d in db.dreams.find(
            {"user_id": uid, "themes": {"$exists": True, "$ne": []}}
    ).sort("created_at", -1).limit(40):
        for t in d.get("themes", []):
            themes[t] = themes.get(t, 0) + 1
    return sorted(themes, key=lambda k: themes[k], reverse=True)


async def _user_sign(db, uid: str) -> Optional[str]:
    r = await db.ai_readings.find_one(
        {"user_id": uid, "type": "horoscope"}, sort=[("created_at", -1)])
    return r.get("subject") if r else None


@router.get("/compatibility/candidates")
async def compat_candidates(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    items = []
    if friends:
        async for u in db.users.find({"user_id": {"$in": list(friends)}}).limit(60):
            pub = _user_public(u)
            items.append({"user_id": u["user_id"], "name": pub.get("name"),
                          "avatar_url": pub.get("avatar_url")})
    return {"items": items, "note": "Pick a friend to see your playful dream match."}


class CompatBody(BaseModel):
    target_user_id: str


@router.post("/compatibility")
async def compatibility(body: CompatBody, request: Request,
                        user: dict = Depends(current_user)):
    return await _compute_compat(request.app.state.db, user["user_id"],
                                 body.target_user_id)


async def _compute_compat(db, uid: str, target_id: str) -> dict:
    if target_id == uid:
        raise HTTPException(400, {"code": "cannot_match_self"})
    target = await db.users.find_one({"user_id": target_id})
    if not target:
        raise HTTPException(404, {"code": "user_not_found"})
    my_themes = await _user_themes(db, uid)
    their_themes = await _user_themes(db, target_id)
    shared = [t for t in my_themes if t in their_themes]
    my_sign = await _user_sign(db, uid)
    their_sign = await _user_sign(db, target_id)
    import hashlib
    seed = int(hashlib.md5("|".join(sorted([uid, target_id]))
                           .encode()).hexdigest(), 16)
    base = 55 + (seed % 26)
    score = min(99, base + 4 * len(shared))
    me = _user_public(await db.users.find_one({"user_id": uid}))
    them = _user_public(target)
    prompt = (
        f"Person A ({me.get('name')}) star sign {my_sign or 'unknown'}, dream themes "
        f"{[THEME_LABELS.get(t, t) for t in my_themes[:5]] or 'none yet'}. "
        f"Person B ({them.get('name')}) star sign {their_sign or 'unknown'}, dream themes "
        f"{[THEME_LABELS.get(t, t) for t in their_themes[:5]] or 'none yet'}. "
        f"Shared themes: {[THEME_LABELS.get(t, t) for t in shared] or 'none'}. "
        f"Their playful dream-match score is {score}/100. Write a fun, kind blurb.")
    res = await _llm(_COMPAT_SYSTEM, prompt, f"compat_{uid}_{target_id}")
    if not isinstance(res, dict):
        res = {"headline": f"{score}% dream sync ✨",
               "blurb": ("Your dream worlds share a gentle, curious energy — a fun "
                         "match to explore stories together."),
               "shared_note": ("You both wander similar dreamscapes."
                               if shared else "Two different dream worlds, equally magical.")}
    return {"score": score,
            "headline": res.get("headline") or f"{score}% dream sync",
            "blurb": res.get("blurb"),
            "shared_note": res.get("shared_note"),
            "shared_themes": [THEME_LABELS.get(t, t) for t in shared],
            "my_sign": my_sign, "their_sign": their_sign,
            "target": {"user_id": target["user_id"],
                       "name": them.get("name"), "avatar_url": them.get("avatar_url")},
            "label": "PLAYFUL · entertainment only", "disclaimer": DISCLAIMER}


@router.post("/compatibility/share")
async def compatibility_share(body: CompatBody, request: Request,
                              user: dict = Depends(current_user)):
    """Persist a match as a shareable public card (+1 BigPoint for sharing)."""
    db = request.app.state.db
    res = await _compute_compat(db, user["user_id"], body.target_user_id)
    me = _user_public(await db.users.find_one({"user_id": user["user_id"]}))
    card_id = f"mc_{uuid.uuid4().hex[:14]}"
    await db.compat_cards.insert_one({
        "_id": card_id, "card_id": card_id, "owner_id": user["user_id"],
        "owner_name": me.get("name"), "target_name": res["target"]["name"],
        "score": res["score"], "headline": res["headline"], "blurb": res["blurb"],
        "shared_note": res["shared_note"], "shared_themes": res["shared_themes"],
        "my_sign": res["my_sign"], "their_sign": res["their_sign"],
        "public": True, "created_at": _now()})
    card_doc = {"card_id": card_id, "owner_name": me.get("name"),
                "target_name": res["target"]["name"], "score": res["score"],
                "headline": res["headline"], "shared_themes": res["shared_themes"],
                "my_sign": res["my_sign"], "their_sign": res["their_sign"]}
    # Generate the share-ready Match Card Art (AI bg + composited text).
    await _ensure_card_image(db, card_doc)
    pts = 0
    try:
        from routes.dreams_guidance import award_social_share
        pts = await award_social_share(db, user["user_id"], f"compat:{card_id}")
    except Exception:
        pts = 0
    return {"card_id": card_id, "path": f"/dreams/match/{card_id}",
            "share_path": f"/api/social/dreams/match/{card_id}",
            "image_url": _card_image_url(request, card_id),
            "points_awarded": pts, **res}


@router.get("/compatibility/card/{card_id}/image.png")
async def compat_card_image(card_id: str, request: Request):
    """Public PNG of the Match Card Art — used for og:image + downloads."""
    db = request.app.state.db
    c = await db.compat_cards.find_one({"card_id": card_id, "public": True})
    if not c:
        raise HTTPException(404, {"code": "card_not_found"})
    key = c.get("image_key") or _card_key(card_id)
    data = _storage_read(key)
    if data is None:
        await _ensure_card_image(db, c)
        data = _storage_read(key)
    if data is None:
        raise HTTPException(404, {"code": "image_unavailable"})
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400, "
                                              "stale-while-revalidate=604800"})


@router.get("/dreams/match/{card_id}")
async def match_card_ssr(card_id: str, request: Request):
    """SSR OG landing for a shared match card. Crawlers read the meta tags;
    real browsers are redirected to the SPA view at /dreams/match/<id>."""
    db = request.app.state.db
    base = _base_url(request)
    spa = f"{base}/dreams/match/{card_id}"
    c = await db.compat_cards.find_one({"card_id": card_id, "public": True})
    if not c:
        return RedirectResponse(spa, status_code=302)
    img = _card_image_url(request, card_id)
    title = (f"{c.get('owner_name')} & {c.get('target_name')} — "
             f"{c.get('score')}% dream match \u2728")
    desc = (c.get("headline") or "A playful dream compatibility match on RadioLife.")
    landing = f"{base}/api/social/dreams/match/{card_id}"
    import html as _h
    e = _h.escape
    out = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(landing)}">
<meta property="og:type" content="website">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name" content="RadioLife">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(img)}">
<link rel="canonical" href="{e(landing)}">
<style>body{{margin:0;background:#0d0a24;color:#fff;font-family:system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}img{{max-width:520px;width:100%;border-radius:20px;box-shadow:0 18px 60px rgba(0,0,0,.5)}}</style>
<script>(function(){{try{{var ua=navigator.userAgent||"";var bot=/facebookexternalhit|twitterbot|whatsapp|telegrambot|slackbot|linkedinbot|discordbot|preview|googlebot|bingbot|applebot|pinterest/i.test(ua);if(!bot)window.location.replace("{e(spa)}");}}catch(x){{}}}})();</script>
</head><body><img src="{e(img)}" alt="{e(title)}"></body></html>"""
    return HTMLResponse(out)


@router.get("/compatibility/card/{card_id}")
async def compat_card(card_id: str, request: Request,
                      user: Optional[dict] = Depends(current_user_optional)):
    """Public, no-login view of a shared match card."""
    db = request.app.state.db
    c = await db.compat_cards.find_one({"card_id": card_id, "public": True})
    if not c:
        raise HTTPException(404, {"code": "card_not_found"})
    return {"card_id": card_id, "owner_name": c.get("owner_name"),
            "target_name": c.get("target_name"), "score": c.get("score"),
            "headline": c.get("headline"), "blurb": c.get("blurb"),
            "shared_note": c.get("shared_note"),
            "shared_themes": c.get("shared_themes") or [],
            "my_sign": c.get("my_sign"), "their_sign": c.get("their_sign"),
            "image_url": _card_image_url(request, card_id),
            "label": "PLAYFUL · entertainment only", "disclaimer": DISCLAIMER,
            "created_at": _iso(c.get("created_at"))}


__all__ = ["router", "ensure_clusters_ai_indexes", "extract_and_store_themes",
           "THEME_LABELS"]
