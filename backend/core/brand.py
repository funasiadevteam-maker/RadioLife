"""FUUSIC — central consumer brand constants (single source of truth).

The CONSUMER brand is FUUSIC. Technical identifiers (bigfm_session cookie,
/api routes, DB collections, bigfm:* events, env vars) are intentionally NOT
renamed here — see /app/memory/FUUSIC_REBRAND_TECHDEBT.md.
"""

BRAND_NAME = "FUUSIC"
BRAND_TAGLINE = "Everything You Love, Together."
BRAND_DESCRIPTOR = "Listen · Connect · Play · Shop · Earn"
BRAND_MEANING = (
    "Friends · Unite · Unique Experiences · Social · Interaction · Commerce"
)
BRAND_FROM_NAME = "FUUSIC"
BRAND_BUSINESS_NAME = "FUUSIC Business"
BRAND_PREMIUM_NAME = "FUUSIC Premium"

# ── Domain / web / mail — the SINGLE SWITCH for the Phase-3 fuusic.com cutover.
# Defaults are today's live, working values (radiolife.app). To flip the whole
# platform to fuusic.com, set these env vars once (in backend/.env) — no code
# change needed. Do NOT flip until DNS/TLS/OAuth origins + real mailboxes exist.
import os as _os

PUBLIC_BRAND_DOMAIN = _os.environ.get("PUBLIC_BRAND_DOMAIN", "radiolife.app")
PUBLIC_WEB_URL = _os.environ.get(
    "PUBLIC_WEB_URL", f"https://{PUBLIC_BRAND_DOMAIN}").rstrip("/")
MAIL_FROM_DOMAIN = _os.environ.get("MAIL_FROM_DOMAIN", PUBLIC_BRAND_DOMAIN)
BRAND_SUPPORT_EMAIL = _os.environ.get(
    "SUPPORT_EMAIL", f"support@{PUBLIC_BRAND_DOMAIN}")
BRAND_PARTNER_EMAIL = _os.environ.get(
    "PARTNER_EMAIL", f"partner@{PUBLIC_BRAND_DOMAIN}")
# Marketing/legal display domain for the consumer brand (post-cutover: fuusic.com).
BRAND_DOMAIN = _os.environ.get("BRAND_DISPLAY_DOMAIN", "fuusic.com")
