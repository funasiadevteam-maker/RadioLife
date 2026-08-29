"""Pre-render a short preview clip for each curated anchor voice.

Writes `/app/backend/storage/voice_samples/<voice_id>.mp3` so the voice
picker (web) can play a sample before switching. Idempotent — skips a
voice whose sample already exists unless --force is passed.

    python -m scripts.gen_voice_samples [--force]
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from services.elevenlabs_tts import synthesize          # noqa: E402
from services.news_radio_settings import (               # noqa: E402
    CURATED_ANCHOR_VOICES, SAMPLE_LINE)

OUT_DIR = Path("/app/backend/storage/voice_samples")


def main() -> int:
    force = "--force" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for v in CURATED_ANCHOR_VOICES:
        vid = v["voice_id"]
        out = OUT_DIR / f"{vid}.mp3"
        if out.exists() and not force:
            print(f"skip {v['name']} ({vid}) — exists")
            ok += 1
            continue
        res = synthesize(text=SAMPLE_LINE, voice_id=vid, out_path=out)
        if res.get("ok"):
            print(f"ok   {v['name']} ({vid}) → {out}")
            ok += 1
        else:
            print(f"FAIL {v['name']} ({vid}): {res.get('error')}")
    print(f"done: {ok}/{len(CURATED_ANCHOR_VOICES)} samples ready")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
