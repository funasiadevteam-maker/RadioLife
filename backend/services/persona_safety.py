"""Phase 39 Session 1 — Persona safety classifier.

Single source of truth for "is this persona configuration safe to expose?"
Used by:
  • `scripts/phase39_seed_launch_personas.py` (every seed run re-classifies)
  • `GET /api/admin/personas/safety_audit`  (admin moderation surface)
  • Future Session 2 persona create/update endpoints (server-side guard).

Four signals, evaluated in priority order:

  1. **Name match** — `display_name` fuzzy-matched against
      `data/celebrity_blocklist.json` (~150 high-risk public figures).
      Match = normalized exact OR Levenshtein ≤1.
  2. **Catchphrase match** — every `signature_phrases[i]` fuzzy-matched
      against `data/catchphrase_blocklist.json` (~50 trademarked or
      strongly-associated phrases). Match = normalized substring OR
      Levenshtein ≤2 against any blocklisted phrase.
  3. **External voice clone** — `voice_clone_reference_url` must point to
      our own storage (Tigris `s3://…` or `/storage/…`).  Anything else
      (YouTube, Spotify, S3 public buckets, etc.) is flagged.
  4. **LLM-as-judge** — if `description` mentions "sounds like X",
      "in the style of Y", "channeling Z", we ask GPT-4o-mini to
      determine whether X/Y/Z names a real public figure.  Blocks on
      `confidence ≥ 0.7`.  Skipped when OpenAI is unavailable —
      degrades open with a "llm_judge_unavailable" flag (never silently
      passes risky input).

Returns:
    {
      "is_safe":     bool,
      "risk_score": 0.0-1.0,
      "flags":      list[str],    # canonical flag names
      "evidence":  list[str],    # human-readable details
    }
"""
from __future__ import annotations
import json
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger("bigfm.persona_safety")

# Module-level OpenAI import — guarded.  Tests patch
# `services.persona_safety.OpenAI` so the import-once pattern matters.
try:
    from openai import OpenAI  # noqa: F401
except Exception:
    OpenAI = None  # type: ignore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# LLM judge — flag-only phrases (cheap regex prefilter so we don't pay
# OpenAI to classify every persona).  Hit any of these → LLM call fires.
_LLM_TRIGGER_PHRASES = (
    "sounds like ", "sound like ", "in the style of ", "style of ",
    "channeling ", "channelling ", "mimic ", "imitate ", "imitating ",
    "voice of ", "like (the actor", "like (the singer", "evokes ",
    "à la ", "a la ", "reminiscent of ",
)

# Internal-storage URL prefixes considered safe.
_INTERNAL_URL_PREFIXES = (
    "s3://",
    "/storage/",
    "/app/backend/storage/",
    "tigris://",
    # platform-internal preview URLs end with the live preview host
)


# ─── normalization ───────────────────────────────────────────────────
def _normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    # Strip combining marks (accents)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^\w\s]+", " ", s)  # punctuation → space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _levenshtein_bounded(a: str, b: str, max_dist: int) -> int:
    """Bounded Levenshtein. Returns max_dist+1 if exceeded (early exit)."""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        min_in_row = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                prev[j] + 1,            # delete
                cur[j - 1] + 1,        # insert
                prev[j - 1] + (0 if ca == cb else 1),  # sub
            )
            if cur[j] < min_in_row:
                min_in_row = cur[j]
        if min_in_row > max_dist:
            return max_dist + 1
        prev = cur
    return prev[-1]


# ─── blocklist loaders (cached at module level) ──────────────────────
@lru_cache(maxsize=1)
def _celebrity_names() -> tuple[str, ...]:
    path = DATA_DIR / "celebrity_blocklist.json"
    if not path.exists():
        log.warning("[persona_safety] celebrity_blocklist.json missing")
        return ()
    data = json.loads(path.read_text())
    return tuple(_normalize(n) for n in data.get("names", []) if n)


@lru_cache(maxsize=1)
def _celebrity_max_edits() -> int:
    path = DATA_DIR / "celebrity_blocklist.json"
    if not path.exists():
        return 1
    return int(json.loads(path.read_text()).get("_meta", {})
                            .get("fuzzy_max_edits", 1))


@lru_cache(maxsize=1)
def _catchphrases() -> tuple[str, ...]:
    path = DATA_DIR / "catchphrase_blocklist.json"
    if not path.exists():
        log.warning("[persona_safety] catchphrase_blocklist.json missing")
        return ()
    data = json.loads(path.read_text())
    return tuple(_normalize(p) for p in data.get("phrases", []) if p)


@lru_cache(maxsize=1)
def _catchphrase_max_edits() -> int:
    path = DATA_DIR / "catchphrase_blocklist.json"
    if not path.exists():
        return 2
    return int(json.loads(path.read_text()).get("_meta", {})
                            .get("fuzzy_max_edits", 2))


def reload_blocklists() -> None:
    """Drop cached blocklist data so the next call re-reads from disk.
    Useful for tests that mutate the JSON files at runtime."""
    _celebrity_names.cache_clear()
    _celebrity_max_edits.cache_clear()
    _catchphrases.cache_clear()
    _catchphrase_max_edits.cache_clear()


# ─── individual signal checks ────────────────────────────────────────
def _check_name(display_name: str) -> tuple[bool, list[str]]:
    """Returns (matched, evidence_list)."""
    name_norm = _normalize(display_name)
    if not name_norm:
        return False, []
    max_e = _celebrity_max_edits()
    for celeb in _celebrity_names():
        if not celeb:
            continue
        # Exact normalized hit
        if name_norm == celeb:
            return True, [f"name exact match: '{celeb}'"]
        # Substring containment (catches "Tom Cruise from Dubai")
        if celeb in name_norm or name_norm in celeb:
            return True, [f"name substring match: '{celeb}'"]
        # Levenshtein bounded
        d = _levenshtein_bounded(name_norm, celeb, max_e)
        if d <= max_e:
            return True, [f"name fuzzy match (dist={d}): '{celeb}'"]
    return False, []


def _check_catchphrases(phrases: list[str]) -> tuple[bool, list[str]]:
    if not phrases:
        return False, []
    blocklist = _catchphrases()
    if not blocklist:
        return False, []
    max_e = _catchphrase_max_edits()
    evidence: list[str] = []
    for raw in phrases:
        p_norm = _normalize(raw)
        if not p_norm:
            continue
        for bad in blocklist:
            if not bad:
                continue
            # Substring containment either way
            if bad in p_norm or (len(p_norm) > 4 and p_norm in bad):
                evidence.append(f"catchphrase substring match: "
                                              f"'{raw}' ~ '{bad}'")
                continue
            d = _levenshtein_bounded(p_norm, bad, max_e)
            if d <= max_e:
                evidence.append(f"catchphrase fuzzy match (dist={d}): "
                                              f"'{raw}' ~ '{bad}'")
    return (len(evidence) > 0), evidence


def _check_voice_clone_url(url: Optional[str]) -> tuple[bool, list[str]]:
    if not url:
        return False, []
    url_l = str(url).strip().lower()
    if not url_l:
        return False, []
    for prefix in _INTERNAL_URL_PREFIXES:
        if url_l.startswith(prefix):
            return False, []
    try:
        host = urlparse(url_l).hostname or ""
    except Exception:
        host = ""
    # Tolerate the platform's preview host as internal.
    if host.endswith(".emergentagent.com"):
        return False, []
    # Anything else flagged as external.
    return True, [f"external voice clone reference: {host or url_l[:60]}"]


def _check_llm_judge(description: Optional[str]) -> tuple[bool, list[str]]:
    """Returns (matched, evidence). Falls back to (False, ['unavailable'])
    when OpenAI is missing — i.e. degrades open with a visible flag."""
    if not description:
        return False, []
    desc_l = description.lower()
    if not any(p in desc_l for p in _LLM_TRIGGER_PHRASES):
        return False, []
    # Cheap prefilter hit → ask the LLM.
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return False, ["llm_judge_unavailable: no OPENAI_API_KEY"]
    try:
        if OpenAI is None:
            return False, ["llm_judge_unavailable: openai package missing"]
        client = OpenAI(api_key=api_key)
        prompt = (
            "Does this persona description attempt to imitate a real "
            "public figure (actor, musician, politician, athlete, "
            "celebrity)?  Reply with strict JSON: "
            '{"is_imitation": bool, "confidence": float 0-1, '
            '"figure_named": string or null}.  '
            "Only flag actual real-person imitation; archetype labels "
            '(e.g. "warm Dubai morning host") are NOT imitations.\n\n'
            f"Description:\n{description}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                  "content": "You classify persona descriptions for "
                                      "celebrity-imitation risk. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=12,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if data.get("is_imitation") and float(data.get("confidence", 0)) >= 0.7:
            who = data.get("figure_named") or "<unspecified>"
            conf = float(data.get("confidence", 0))
            return True, [f"llm judgement: imitation of '{who}' "
                                      f"(confidence={conf:.2f})"]
        return False, []
    except Exception as e:
        log.warning("[persona_safety] LLM judge failed: %s", e)
        return False, [f"llm_judge_unavailable: {type(e).__name__}"]


# ─── public classifier ───────────────────────────────────────────────
class PersonaSafetyClassifier:
    """Stateless wrapper — instantiate freely.  Module-level caches do
    the heavy lifting."""

    def classify(self, persona: dict) -> dict:
        flags: list[str] = []
        evidence: list[str] = []
        risk_score = 0.0

        name_hit, name_ev = _check_name(persona.get("display_name", ""))
        if name_hit:
            flags.append("name_match")
            evidence.extend(name_ev)
            risk_score = max(risk_score, 1.0)  # name match is decisive

        cp_hit, cp_ev = _check_catchphrases(
            persona.get("signature_phrases", []) or [])
        if cp_hit:
            flags.append("catchphrase_match")
            evidence.extend(cp_ev)
            risk_score = max(risk_score, 0.9)

        url_hit, url_ev = _check_voice_clone_url(
            persona.get("voice_clone_reference_url"))
        if url_hit:
            flags.append("external_voice_clone")
            evidence.extend(url_ev)
            risk_score = max(risk_score, 0.6)

        llm_hit, llm_ev = _check_llm_judge(persona.get("description"))
        if llm_hit:
            flags.append("llm_imitation_judgement")
            evidence.extend(llm_ev)
            risk_score = max(risk_score, 0.85)
        else:
            # Always surface llm availability for ops visibility.
            for ev in llm_ev:
                if ev.startswith("llm_judge_unavailable"):
                    flags.append("llm_judge_unavailable")
                    evidence.append(ev)

        is_safe = (not name_hit) and (not cp_hit) and \
                          (not url_hit) and (not llm_hit)

        return {
            "is_safe":      bool(is_safe),
            "risk_score": float(risk_score),
            "flags":        flags,
            "evidence":  evidence,
        }


def suggest_safe_archetype(reason_flag: str) -> str:
    """Used by Session 2's persona create flow to nudge users to a
    safe alternative when they trip the classifier.  For Session 1 we
    just return a static suggestion per flag."""
    return {
        "name_match":                          "Try an original archetype like 'Dawn Caller' or 'Sunset Reflector'.",
        "catchphrase_match":              "Replace the catchphrase with an original line that reflects the vibe (e.g. 'good vibes only', 'let's roll').",
        "external_voice_clone":      "Reference clips must be uploaded to our storage — external URLs (YouTube, Spotify) aren't allowed.",
        "llm_imitation_judgement": "Rephrase the persona description without naming a real public figure.",
    }.get(reason_flag,
              "Try an original archetype label and an original signature phrase.")
