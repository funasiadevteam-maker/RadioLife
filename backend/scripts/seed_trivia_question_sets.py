"""Phase C — Seed pre-baked trivia question sets.

Idempotent by set `id`.  Safe to run multiple times: existing sets are
updated in-place; new ones inserted.  Also creates the required
indexes on `trivia_question_sets`.

Usage:
    python3 backend/scripts/seed_trivia_question_sets.py

The dispatcher / Phase C hub can also invoke `seed()` on startup — see
`server.py` bootstrap.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Allow running standalone.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND, ".env"))

from motor.motor_asyncio import AsyncIOMotorClient        # noqa: E402

logger = logging.getLogger("bigfm.trivia.seed")

QUESTION_SETS = [
    {
        "id":                    "tqs_pop_culture_10",
        "title":                "Pop Culture 101",
        "category":          "pop_culture",
        "language":          "en",
        "difficulty":      "easy",
        "questions": [
            {"id": "q_pop_01",
              "prompt": "Which band released the album 'Abbey Road' in 1969?",
              "options": ["The Beatles", "The Rolling Stones", "Led Zeppelin",
                                  "Pink Floyd"],
              "correct_index": 0, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_02",
              "prompt": "Who directed the film 'Inception' (2010)?",
              "options": ["Steven Spielberg", "Christopher Nolan",
                                  "Martin Scorsese", "James Cameron"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_03",
              "prompt": "In 'Friends', what is Ross's profession?",
              "options": ["Chef", "Palaeontologist", "Actor", "Musician"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_04",
              "prompt": "Which artist painted the ceiling of the Sistine Chapel?",
              "options": ["Leonardo da Vinci", "Raphael", "Michelangelo",
                                  "Donatello"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_05",
              "prompt": "Which colour comes between blue and yellow in the "
                                "visible spectrum?",
              "options": ["Red", "Green", "Purple", "Orange"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_06",
              "prompt": "Who wrote the play 'Romeo and Juliet'?",
              "options": ["Christopher Marlowe", "William Shakespeare",
                                  "John Milton", "Geoffrey Chaucer"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_07",
              "prompt": "In what year did the first iPhone launch?",
              "options": ["2005", "2007", "2009", "2010"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_08",
              "prompt": "Which fictional wizard attends Hogwarts?",
              "options": ["Frodo Baggins", "Gandalf", "Harry Potter",
                                  "Merlin"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_09",
              "prompt": "Which social network was originally called "
                                "'thefacebook'?",
              "options": ["Twitter", "Instagram", "Facebook", "LinkedIn"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_pop_10",
              "prompt": "What sport is Serena Williams famous for?",
              "options": ["Tennis", "Golf", "Basketball", "Swimming"],
              "correct_index": 0, "time_limit_seconds": 15, "points": 100},
        ],
    },
    {
        "id":                    "tqs_music_hits_10",
        "title":                "Music Hits",
        "category":          "music",
        "language":          "en",
        "difficulty":      "medium",
        "questions": [
            {"id": "q_mus_01",
              "prompt": "Which artist recorded 'Bohemian Rhapsody'?",
              "options": ["Queen", "The Beatles", "Led Zeppelin", "ABBA"],
              "correct_index": 0, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_02",
              "prompt": "Who is known as the 'King of Pop'?",
              "options": ["Elvis Presley", "Michael Jackson", "Prince",
                                  "Justin Timberlake"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_03",
              "prompt": "What year did the Woodstock festival take place?",
              "options": ["1965", "1969", "1972", "1978"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_04",
              "prompt": "Which instrument does Yo-Yo Ma primarily play?",
              "options": ["Violin", "Cello", "Piano", "Flute"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_05",
              "prompt": "Which pop star's real name is Robyn Fenty?",
              "options": ["Beyoncé", "Rihanna", "Nicki Minaj", "Alicia Keys"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_06",
              "prompt": "The song 'Blinding Lights' was released by which "
                                "artist?",
              "options": ["Drake", "Post Malone", "The Weeknd", "Bruno Mars"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_07",
              "prompt": "Which band released the album 'Dark Side of the Moon'?",
              "options": ["The Beatles", "Pink Floyd", "The Doors",
                                  "The Who"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_08",
              "prompt": "Which K-Pop group released 'Dynamite' in 2020?",
              "options": ["BLACKPINK", "TWICE", "BTS", "EXO"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_09",
              "prompt": "Whose 1982 album 'Thriller' is the best-selling of "
                                "all time?",
              "options": ["Prince", "Michael Jackson", "Madonna",
                                  "Whitney Houston"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_mus_10",
              "prompt": "Which instrument has 88 keys?",
              "options": ["Guitar", "Piano", "Saxophone", "Harp"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
        ],
    },
    {
        "id":                    "tqs_general_knowledge_10",
        "title":                "General Knowledge",
        "category":          "general",
        "language":          "en",
        "difficulty":      "medium",
        "questions": [
            {"id": "q_gen_01",
              "prompt": "What is the capital of Australia?",
              "options": ["Sydney", "Melbourne", "Canberra", "Perth"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_02",
              "prompt": "Which planet is known as the Red Planet?",
              "options": ["Venus", "Mars", "Jupiter", "Saturn"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_03",
              "prompt": "How many continents are there on Earth?",
              "options": ["5", "6", "7", "8"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_04",
              "prompt": "What is the largest ocean on Earth?",
              "options": ["Atlantic", "Indian", "Arctic", "Pacific"],
              "correct_index": 3, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_05",
              "prompt": "In what year did World War II end?",
              "options": ["1943", "1945", "1947", "1950"],
              "correct_index": 1, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_06",
              "prompt": "What is the chemical symbol for gold?",
              "options": ["Go", "Gd", "Au", "Ag"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_07",
              "prompt": "Which is the tallest mountain in the world?",
              "options": ["K2", "Kangchenjunga", "Mount Everest",
                                  "Makalu"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_08",
              "prompt": "What is the currency of Japan?",
              "options": ["Won", "Yuan", "Yen", "Ringgit"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_09",
              "prompt": "Who painted the Mona Lisa?",
              "options": ["Vincent van Gogh", "Pablo Picasso",
                                  "Leonardo da Vinci", "Claude Monet"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
            {"id": "q_gen_10",
              "prompt": "How many players are on a football (soccer) team "
                                "on the field?",
              "options": ["9", "10", "11", "12"],
              "correct_index": 2, "time_limit_seconds": 15, "points": 100},
        ],
    },
]


async def ensure_indexes(db) -> None:
    try:
        await db.trivia_question_sets.create_index("id", unique=True,
                                                                                        name="tqs_id_uniq")
        await db.trivia_question_sets.create_index(
            [("category", 1), ("language", 1)], name="tqs_cat_lang")
        await db.trivia_question_sets.create_index("active",
                                                                                        name="tqs_active",
                                                                                        sparse=True)
    except Exception as e:
        logger.warning("[trivia.qsets] index setup: %s", e)


async def seed(db) -> dict:
    """Idempotent upsert.  Returns {upserted, updated, total} counts."""
    await ensure_indexes(db)
    now = datetime.now(timezone.utc)
    upserted = 0
    updated  = 0
    for qs in QUESTION_SETS:
        doc = {**qs,
                    "question_count": len(qs["questions"]),
                    "active":                True,
                    "updated_at":      now}
        res = await db.trivia_question_sets.update_one(
            {"id": qs["id"]},
            {"$set": doc,
              "$setOnInsert": {"_id": qs["id"], "created_at": now}},
            upsert=True)
        if res.upserted_id:
            upserted += 1
        elif res.modified_count:
            updated += 1
    total = await db.trivia_question_sets.count_documents({"active": True})
    return {"upserted": upserted, "updated": updated, "total": total}


async def _main():
    logging.basicConfig(level=logging.INFO)
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    res = await seed(db)
    logger.info("Seed done: %s", res)


if __name__ == "__main__":
    asyncio.run(_main())
