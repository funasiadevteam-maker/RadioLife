"""Phase 5 — Game logic: spin wheel, music trivia, lyric puzzle.

All games are server-authoritative: the result is computed on the server,
written to game_sessions, and only the outcome is returned to the client.
"""
from __future__ import annotations

import hashlib
import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from services.bigcoin import award

# Default reward pool for the platform Spin & Win
DEFAULT_SPIN_POOL = [
    {"label": "5 BigCoin",   "type": "bigcoin", "amount": 5,   "weight": 40},
    {"label": "20 BigCoin",  "type": "bigcoin", "amount": 20,  "weight": 25},
    {"label": "50 BigCoin",  "type": "bigcoin", "amount": 50,  "weight": 15},
    {"label": "100 BigCoin", "type": "bigcoin", "amount": 100, "weight": 10},
    {"label": "200 BigCoin", "type": "bigcoin", "amount": 200, "weight":  5},
    {"label": "Sponsor coupon", "type": "coupon",
     "coupon": {"title": "Karak Cafe 10% off",
                 "code": "SPIN10", "value_cents": 1000, "currency": "AED"},
     "weight":  5},
]

SPIN_COOLDOWN_SEC = 4 * 3600
TRIVIA_DAILY_LIMIT = 3
LYRIC_DAILY_LIMIT = 3
TRIVIA_REWARD = 10
TRIVIA_STREAK_BONUS = 5
LYRIC_REWARD = 15


def _weighted_pick(slices: list, server_seed: str, client_seed: str) -> int:
    """Provably-fair: hash(server_seed + client_seed) → uniform float → slice."""
    h = hashlib.sha256(f"{server_seed}|{client_seed}".encode()).hexdigest()
    # Take first 8 hex chars → uniform on [0, 1)
    u = int(h[:8], 16) / 0xFFFFFFFF
    total = sum(s["weight"] for s in slices)
    threshold = u * total
    acc = 0.0
    for i, s in enumerate(slices):
        acc += s["weight"]
        if threshold < acc:
            return i
    return len(slices) - 1


# ---------------------------------------------------------------
# Spin & Win
async def play_spin(db, user: dict, client_seed: str) -> dict:
    """Returns {result, slice_index, server_seed, client_seed, reward,
    bigcoin_earned, cooldown_until}."""
    uid = user["user_id"]
    now = datetime.now(timezone.utc)
    game = await db.games.find_one({"slug": "spin_win", "active": True})
    if not game:
        raise ValueError("spin_win game not configured")
    # Cooldown check
    cooldown = int(game.get("cooldown_sec") or SPIN_COOLDOWN_SEC)
    last = await db.game_sessions.find_one(
        {"user_id": uid, "game_id": game["_id"]},
        sort=[("played_at", -1)],
        projection={"played_at": 1, "_id": 0},
    )
    if last and last.get("played_at"):
        pa = last["played_at"]
        if pa.tzinfo is None:
            pa = pa.replace(tzinfo=timezone.utc)
        if (now - pa).total_seconds() < cooldown:
            remain = cooldown - int((now - pa).total_seconds())
            raise ValueError(f"cooldown: {remain}s remaining")
    # Run the spin
    slices = game.get("reward_pool_json") or DEFAULT_SPIN_POOL
    server_seed = secrets.token_hex(16)
    idx = _weighted_pick(slices, server_seed, client_seed)
    slice_won = slices[idx]
    sid = f"gs_{uuid.uuid4().hex[:14]}"
    bigcoin_earned = 0
    reward_payload = {"slice_index": idx, "label": slice_won.get("label")}
    if slice_won["type"] == "bigcoin":
        amt = int(slice_won["amount"])
        await award(db, uid, amt, "game_win",
                      metadata={"game": "spin_win", "session_id": sid,
                                "label": slice_won.get("label")})
        bigcoin_earned = amt
        reward_payload["bigcoin"] = amt
    elif slice_won["type"] == "coupon":
        cdata = slice_won.get("coupon") or {}
        wid = f"wi_{uuid.uuid4().hex[:14]}"
        await db.user_wallet_items.insert_one({
            "_id": wid, "user_id": uid, "item_type": "coupon",
            "source_game_id": game["_id"], "source_session_id": sid,
            "title": cdata.get("title"), "code": cdata.get("code"),
            "value_cents": cdata.get("value_cents"),
            "currency": cdata.get("currency"),
            "status": "active",
            "expires_at": now + timedelta(days=30),
            "created_at": now,
        })
        reward_payload["wallet_item_id"] = wid
    # Persist game_session
    await db.game_sessions.insert_one({
        "_id": sid, "user_id": uid, "game_id": game["_id"],
        "result": "won", "reward_awarded_json": reward_payload,
        "bigcoin_earned": bigcoin_earned,
        "wallet_item_created": reward_payload.get("wallet_item_id"),
        "client_seed": client_seed, "server_seed": server_seed,
        "duration_sec": 3.0, "played_at": now,
    })
    await db.games.update_one({"_id": game["_id"]},
                                {"$inc": {"plays_count": 1}})
    return {
        "session_id": sid, "result": "won",
        "slice_index": idx, "label": slice_won.get("label"),
        "type": slice_won["type"],
        "bigcoin_earned": bigcoin_earned,
        "wallet_item_id": reward_payload.get("wallet_item_id"),
        "server_seed": server_seed, "client_seed": client_seed,
        "cooldown_until": (now + timedelta(seconds=cooldown)).isoformat(),
    }


async def spin_status(db, user_id: str) -> dict:
    """Returns {available, cooldown_remaining_sec, last_result}."""
    game = await db.games.find_one({"slug": "spin_win", "active": True})
    if not game:
        return {"available": False, "reason": "game_disabled"}
    cooldown = int(game.get("cooldown_sec") or SPIN_COOLDOWN_SEC)
    last = await db.game_sessions.find_one(
        {"user_id": user_id, "game_id": game["_id"]},
        sort=[("played_at", -1)],
        projection={"played_at": 1, "reward_awarded_json": 1, "_id": 0},
    )
    if not last:
        return {"available": True, "cooldown_remaining_sec": 0}
    pa = last["played_at"]
    if pa.tzinfo is None:
        pa = pa.replace(tzinfo=timezone.utc)
    elapsed = int((datetime.now(timezone.utc) - pa).total_seconds())
    remain = max(0, cooldown - elapsed)
    return {"available": remain == 0, "cooldown_remaining_sec": remain,
            "last_result": last.get("reward_awarded_json")}


# ---------------------------------------------------------------
# Music Trivia
async def trivia_today_count(db, user_id: str) -> int:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return await db.game_sessions.count_documents({
        "user_id": user_id,
        "played_at": {"$gte": today_start},
        "game_id": {"$in": ["game_trivia"]},
    })


async def generate_trivia_question(db, user_id: str) -> dict:
    """Picks a track and generates a 4-option multi-choice question."""
    # Pull a recently-played track for relevance; fall back to random
    recent = await db.playback_logs.find_one(
        {"user_id": user_id, "event": "play_start"},
        sort=[("timestamp", -1)],
        projection={"track_id": 1, "_id": 0},
    )
    track = None
    if recent and recent.get("track_id"):
        track = await db.tracks.find_one({"_id": recent["track_id"]})
    if not track:
        async for t in db.tracks.aggregate([{"$sample": {"size": 1}}]):
            track = t; break
    if not track:
        raise ValueError("no tracks available")
    # Build 4 distractors of the same field
    qtypes = ["artist", "era", "language"]
    qtype = random.choice(qtypes)
    correct = track.get(qtype) or track.get("artist")
    # Pull 3 random distractors with different value
    distractors = []
    async for t in db.tracks.aggregate([
        {"$match": {qtype: {"$ne": correct}}},
        {"$sample": {"size": 8}},
    ]):
        v = t.get(qtype)
        if v and v not in distractors:
            distractors.append(v)
        if len(distractors) >= 3: break
    while len(distractors) < 3:
        distractors.append(f"{correct}-alt-{len(distractors)}")
    options = distractors + [correct]
    random.shuffle(options)
    correct_idx = options.index(correct)
    question_id = f"trq_{uuid.uuid4().hex[:14]}"
    # Stash the answer server-side for verification
    await db.trivia_questions.insert_one({
        "_id": question_id, "user_id": user_id,
        "track_id": track["_id"],
        "qtype": qtype, "options": options, "correct_idx": correct_idx,
        "served_at": datetime.now(timezone.utc),
    })
    label = {"artist": "Who is the artist of this song?",
              "era": "Which decade is this song from?",
              "language": "What language is this song in?"}[qtype]
    return {
        "question_id": question_id, "question": label,
        "options": options, "track": {
            "title": track.get("title"), "artist": track.get("artist"),
            "audio_url": f"/api/tracks/{track['_id']}/preview",
        },
    }


async def answer_trivia(db, user_id: str, question_id: str, chosen_idx: int,
                          streak_in: int = 0) -> dict:
    q = await db.trivia_questions.find_one({"_id": question_id})
    if not q or q.get("user_id") != user_id:
        raise ValueError("question not found")
    if q.get("answered_at"):
        raise ValueError("already answered")
    await db.trivia_questions.update_one(
        {"_id": question_id},
        {"$set": {"answered_at": datetime.now(timezone.utc),
                   "chosen_idx": chosen_idx}},
    )
    correct = (chosen_idx == q["correct_idx"])
    sid = f"gs_{uuid.uuid4().hex[:14]}"
    bigcoin_earned = 0
    if correct:
        bigcoin_earned = TRIVIA_REWARD
        if streak_in > 0:
            bigcoin_earned += TRIVIA_STREAK_BONUS
        await award(db, user_id, bigcoin_earned, "game_win",
                      metadata={"game": "trivia", "session_id": sid,
                                "streak_in": streak_in})
    await db.game_sessions.insert_one({
        "_id": sid, "user_id": user_id, "game_id": "game_trivia",
        "result": "won" if correct else "lost",
        "reward_awarded_json": {"correct": correct,
                                  "correct_idx": q["correct_idx"],
                                  "chosen_idx": chosen_idx,
                                  "streak_in": streak_in},
        "bigcoin_earned": bigcoin_earned,
        "played_at": datetime.now(timezone.utc),
    })
    return {"correct": correct, "correct_idx": q["correct_idx"],
            "bigcoin_earned": bigcoin_earned,
            "new_streak": (streak_in + 1) if correct else 0,
            "session_id": sid}


# ---------------------------------------------------------------
# Complete the Lyric
async def lyric_today_count(db, user_id: str) -> int:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return await db.game_sessions.count_documents({
        "user_id": user_id,
        "played_at": {"$gte": today_start},
        "game_id": "game_lyric",
    })


async def generate_lyric_puzzle(db, user_id: str,
                                  language_hint: Optional[str] = None) -> dict:
    """Pick a lyric_puzzles doc + 3 distractors."""
    match = {"active": True}
    if language_hint:
        match["language"] = language_hint
    async for puzzle in db.lyric_puzzles.aggregate([{"$match": match},
                                                       {"$sample": {"size": 1}}]):
        break
    else:
        puzzle = None
    if not puzzle:
        raise ValueError("no lyric puzzles available")
    distractor_cur = db.lyric_puzzles.aggregate([
        {"$match": {"_id": {"$ne": puzzle["_id"]},
                     "language": puzzle.get("language")}},
        {"$sample": {"size": 3}},
    ])
    distractors = []
    async for d in distractor_cur:
        distractors.append(d["next_phrase"])
    while len(distractors) < 3:
        distractors.append(f"… [decoy {len(distractors)}]")
    options = distractors + [puzzle["next_phrase"]]
    random.shuffle(options)
    correct_idx = options.index(puzzle["next_phrase"])
    pid = f"lp_{uuid.uuid4().hex[:14]}"
    await db.lyric_attempts.insert_one({
        "_id": pid, "user_id": user_id,
        "puzzle_id": puzzle["_id"], "options": options,
        "correct_idx": correct_idx,
        "served_at": datetime.now(timezone.utc),
    })
    return {
        "puzzle_id": pid,
        "first_half": puzzle["first_half"],
        "song": puzzle.get("song"),
        "artist": puzzle.get("artist"),
        "language": puzzle.get("language"),
        "options": options,
    }


async def answer_lyric(db, user_id: str, puzzle_id: str, chosen_idx: int) -> dict:
    p = await db.lyric_attempts.find_one({"_id": puzzle_id})
    if not p or p.get("user_id") != user_id:
        raise ValueError("puzzle not found")
    if p.get("answered_at"):
        raise ValueError("already answered")
    await db.lyric_attempts.update_one(
        {"_id": puzzle_id},
        {"$set": {"answered_at": datetime.now(timezone.utc),
                   "chosen_idx": chosen_idx}},
    )
    correct = (chosen_idx == p["correct_idx"])
    sid = f"gs_{uuid.uuid4().hex[:14]}"
    bigcoin_earned = LYRIC_REWARD if correct else 0
    if correct:
        await award(db, user_id, bigcoin_earned, "game_win",
                      metadata={"game": "lyric", "session_id": sid,
                                "puzzle_id": p.get("puzzle_id")})
    await db.game_sessions.insert_one({
        "_id": sid, "user_id": user_id, "game_id": "game_lyric",
        "result": "won" if correct else "lost",
        "reward_awarded_json": {"correct": correct,
                                  "correct_idx": p["correct_idx"],
                                  "chosen_idx": chosen_idx},
        "bigcoin_earned": bigcoin_earned,
        "played_at": datetime.now(timezone.utc),
    })
    return {"correct": correct, "correct_idx": p["correct_idx"],
            "bigcoin_earned": bigcoin_earned, "session_id": sid}
