"""Phase 36c Stage 2 — Versioned consent template.

When the template text below is changed, BUMP CONSENT_TEMPLATE_VERSION.
Older signed forms reference their prior version number AND store the
full text at signing — the immutable audit trail does not depend on
this module being preserved unchanged.
"""
from __future__ import annotations

CONSENT_TEMPLATE_VERSION = 1

CONSENT_TEMPLATE_V1 = (
    "By joining this recording, you grant {creator_display_name} permission "
    "to record, edit, and publish your contribution as part of the podcast "
    "'{channel_title}' on RadioLife and any third-party podcast directories "
    "(Apple Podcasts, Spotify, Amazon Music, etc.).\n\n"
    "Your audio recording will be processed by automated transcription and "
    "may be edited for length, clarity, or content moderation. You retain "
    "no editorial rights over the final published episode.\n\n"
    "You may revoke this consent before the episode is published by "
    "contacting the host. Once published, revocation is best-effort — "
    "third-party podcast directories may continue to host the episode.\n\n"
    "You confirm that you are 18+ years old and that you have authority to "
    "grant this consent for yourself."
)


def render(*, creator_display_name: str, channel_title: str) -> dict:
    """Return the current versioned consent text + version. The text is
    fully expanded with the supplied substitutions so that signers see
    the same text we snapshot into podcast_release_forms.consent_text."""
    text = CONSENT_TEMPLATE_V1.format(
        creator_display_name=(creator_display_name or "the host").strip()[:120],
        channel_title=(channel_title or "the podcast").strip()[:120])
    return {"consent_version": CONSENT_TEMPLATE_VERSION,
              "consent_text": text}
