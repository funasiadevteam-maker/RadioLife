"""Phase 18a — Creative safety classifier.

Calls `claude-sonnet-4.5` (text) via emergentintegrations with the
Emergent LLM key.  Returns a structured verdict that gates the
auto-approve-under-$100 path in the campaign-submit flow.

Cost target: ~$0.001/creative.  Prompt is tight, output is JSON-only.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("bigfm.creative_safety")

# Common-knowledge trademark trigger list (≈50 brands).
_TRADEMARK_TRIGGERS = [
    "coca-cola", "coke", "pepsi", "mcdonald's", "burger king", "kfc",
    "subway", "starbucks", "dunkin", "domino's", "pizza hut", "taco bell",
    "spotify", "apple music", "netflix", "amazon prime", "disney plus",
    "youtube music", "instagram", "tiktok", "facebook", "snapchat",
    "uber", "lyft", "careem", "talabat", "deliveroo", "swiggy", "zomato",
    "nike", "adidas", "puma", "gucci", "louis vuitton", "rolex", "tag heuer",
    "samsung", "apple", "iphone", "google pixel", "huawei", "xiaomi",
    "tesla", "bmw", "mercedes", "audi", "toyota", "honda", "ferrari",
]

# Per-market lexicon — restrict cross-market references (parity with RJ).
_MARKET_BANNED = {
    "dubai": {"frisco", "dfw", "dallas", "texas"},
    "dfw":   {"dubai", "uae", "burj khalifa", "marina"},
}


_SYS_PROMPT = """You are BigFM's creative-safety reviewer for radio ads. Examine the AD CREATIVE TRANSCRIPT and return a single JSON object — nothing else.

Flag any of these categories (severity: "low"|"medium"|"high"):
- profanity / hate speech / slurs (HIGH)
- alcohol references (HIGH unless explicitly allowed by market policy)
- gambling / lottery / casino (HIGH)
- political / election content / divisive religious content (HIGH)
- recreational drug references (HIGH)
- explicit sexual content (HIGH)
- medical claims ("cures", "treats", FDA-style language) (HIGH)
- financial guarantees ("guaranteed return", "make $X/day") (HIGH)
- trademark conflicts (mentioning the brands in TRADEMARK_LIST without permission) (MEDIUM)
- cross-market lexicon violations (the ad is for MARKET={market} but references {banned_terms}) (MEDIUM)

OUTPUT FORMAT (JSON only, no markdown fences):
{{
  "verdict": "approved" | "review" | "rejected",
  "issues":  [{{"category": "...", "severity": "low|medium|high", "excerpt": "..."}}],
  "confidence": 0.0-1.0
}}

Rules:
- Any HIGH severity issue → verdict "rejected".
- One or more MEDIUM issues, no HIGH → verdict "review".
- No issues → verdict "approved".
- Be terse; do NOT invent issues that aren't in the transcript.
"""


async def classify_creative(*, transcript: str,
                                                image_url: Optional[str] = None,
                                                advertiser_market: str = "dubai") -> dict:
    """Run the safety classifier.  Returns the structured payload (always
    a dict; on classifier failure returns a `review` verdict with a note)."""
    transcript = (transcript or "").strip()
    if not transcript:
        return {"verdict": "review",
                  "issues":  [{"category": "missing_transcript",
                                  "severity": "low",
                                  "excerpt": ""}],
                  "confidence": 1.0,
                  "note": "Empty transcript — manual review."}

    banned = ", ".join(sorted(_MARKET_BANNED.get(advertiser_market.lower(), []))) or "—"
    system = _SYS_PROMPT.format(market=advertiser_market, banned_terms=banned)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return _heuristic_classify(transcript, advertiser_market,
                                                note="EMERGENT_LLM_KEY not set; ran heuristic only")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        return _heuristic_classify(transcript, advertiser_market,
                                                note=f"emergentintegrations import failed: {e}")
    try:
        chat = (LlmChat(api_key=api_key,
                              session_id="creative-safety",
                              system_message=system)
                  .with_model("anthropic", "claude-sonnet-4-5"))
        msg = UserMessage(text=f"TRANSCRIPT: {transcript}\n"
                                          f"TRADEMARK_LIST: {', '.join(_TRADEMARK_TRIGGERS[:30])}")
        raw = await chat.send_message(msg)
        # Tolerate model wrapping in fences.
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```", 2)[1]
            if txt.startswith("json"):
                txt = txt[4:].strip()
        parsed = json.loads(txt)
        parsed.setdefault("issues", [])
        parsed.setdefault("verdict", "review")
        parsed["raw_response"] = raw[:1500]
        return parsed
    except Exception as e:
        logger.warning("[creative_safety] Claude call failed (%s); using heuristic", e)
        return _heuristic_classify(transcript, advertiser_market,
                                                note=f"Claude failed: {e}")


def _heuristic_classify(transcript: str, market: str, *, note: str = "") -> dict:
    """Local fallback so unit tests work without network."""
    issues = []
    txt = transcript.lower()
    HIGH_TERMS = {
        "profanity":    ["fuck", "shit", "bitch", "go to hell", "damn"],
        "alcohol":       ["beer", "vodka", "whiskey", "wine", "cocktail"],
        "gambling":    ["casino", "bet", "wager", "lottery"],
        "drug":            ["cocaine", "weed", "marijuana"],
    }
    for cat, words in HIGH_TERMS.items():
        for w in words:
            if w in txt:
                issues.append({"category": cat, "severity": "high", "excerpt": w})
                break
    MED_TERMS = {"trademark": _TRADEMARK_TRIGGERS[:30]}
    for cat, words in MED_TERMS.items():
        for w in words:
            if w in txt:
                issues.append({"category": cat, "severity": "medium", "excerpt": w})
                break
    for w in _MARKET_BANNED.get((market or "").lower(), []):
        if w in txt:
            issues.append({"category": "market_lexicon", "severity": "medium",
                                "excerpt": w})
            break
    high = any(i["severity"] == "high"   for i in issues)
    med  = any(i["severity"] == "medium" for i in issues)
    verdict = "rejected" if high else ("review" if med else "approved")
    return {"verdict": verdict, "issues": issues, "confidence": 0.6,
              "raw_response": "heuristic", "note": note}
