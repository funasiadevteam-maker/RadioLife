"""One-off: generate the wheel BGM loop, upload it to object storage, and
attach the demo sponsor logo. Safe to re-run (idempotent)."""
import asyncio
import os
import subprocess
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from routes.instant_games import BGM_KEY  # noqa: E402
from services.object_storage import get_storage  # noqa: E402

LOGO_URL = ("https://static.prod-images.emergentagent.com/jobs/"
            "c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/"
            "06e4642fac025b6512bc1891d895c61cee518ddbc6e9043ec05ce31fad9c33f6.jpeg")

BGM_PATH = "/tmp/wheel_loop.mp3"


def make_bgm() -> bytes:
    # 8s cheerful pad: C-major triad (C5/E5/G5) with a 5 Hz tremolo — 40 whole
    # tremolo cycles over 8s so it loops seamlessly (no click, no fade gap).
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=523.25:d=8",
        "-f", "lavfi", "-i", "sine=659.25:d=8",
        "-f", "lavfi", "-i", "sine=783.99:d=8",
        "-filter_complex",
        "[0][1][2]amix=inputs=3:normalize=0,tremolo=f=5:d=0.6,"
        "aformat=channel_layouts=stereo,volume=0.22",
        "-c:a", "libmp3lame", "-b:a", "128k", BGM_PATH,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    with open(BGM_PATH, "rb") as f:
        return f.read()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    data = make_bgm()
    print(f"BGM bytes: {len(data)}")
    get_storage().upload_bytes(key=BGM_KEY, data=data, content_type="audio/mpeg")
    print(f"uploaded {BGM_KEY}")
    r = await db.branded_games.update_one(
        {"_id": "wheel_demo_sponsor"}, {"$set": {"logo_url": LOGO_URL}})
    print(f"sponsor logo set (matched {r.matched_count})")


if __name__ == "__main__":
    asyncio.run(main())
