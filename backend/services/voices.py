"""Combined RJ voice catalog (core + extra) + voice preview scripts.

Imports the 6 channel-tied RJ voices from `channels.py` and merges them with
the 3 original Phase 0/1 hosts.
"""
from __future__ import annotations

import random
from typing import Dict

from channels import RJ_VOICES_EXT, VOICE_PREVIEW_SCRIPTS_EXT

# Original 3 hosts (Phase 0/1)
RJ_VOICES_CORE: Dict[str, dict] = {
    "veer_dubai": {
        "voice_id": "1WrEi9ztXQkVmKgG6j9A",
        "display_name": "Veer",
        "persona": "male, late-night radio voice, intimate and charming, Mumbai-Dubai NRI, mid-thirties, deep voice, smooth delivery",
        "fits_energies": ("chill", "medium"),
        "duo_label": "VEER",
        "duo_blurb": "smooth late-night charm, late-30s, Mumbai-origin, lives in Bur Dubai. Witty, slightly sarcastic, loves film references.",
    },
    "monika_dubai": {
        "voice_id": "rCmVtv8cYU60uhlsOo1M",
        "display_name": "Monika",
        "persona": "female, warm British-Indian, modulated and expressive, mid-twenties, Dubai resident, brunch-and-chai friend energy",
        "fits_energies": ("chill", "medium"),
        "duo_label": "MONIKA",
        "duo_blurb": "warm Delhi-origin, mid-20s, lives in JLT. High-energy, bubbly, foodie, the heart of the duo.",
    },
    "dj_dubai": {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "display_name": "DJ Charlie",
        "persona": "club MC, deep confident Australian-Indian, late-twenties, hypes the floor, explosive delivery, English-dominant party Hinglish",
        "fits_energies": ("high", "party"),
        "duo_label": "CHARLIE",
        "duo_blurb": "party DJ, 30s, Indo-Punjabi, club-MC energy. Always hyped, calls everyone boss/yaar/bro.",
    },
}

# Merged: 9 voices total
RJ_VOICES: Dict[str, dict] = {**RJ_VOICES_CORE, **RJ_VOICES_EXT}
DEFAULT_VOICE_KEY = "veer_dubai"

VOICE_PREVIEW_SCRIPTS_CORE: Dict[str, str] = {
    "veer_dubai":   "[warm] Aap sun rahe ho... [soft] BigFM. [warm] Dil se, doston.",
    "monika_dubai": "[excited] Heyy! [warm] Aapki Monika, BigFM par. [chuckles] Music chalega NON-stop!",
    "dj_dubai":     "[shouts] BigFM!!! [hyped] DJ Charlie on the mic... [excited] LET'S GO!!!",
}
VOICE_PREVIEW_SCRIPTS: Dict[str, str] = {
    **VOICE_PREVIEW_SCRIPTS_CORE, **VOICE_PREVIEW_SCRIPTS_EXT,
}


def pick_voice_for_energy(energy: str) -> str:
    if energy in ("high", "party"):
        return "dj_dubai"
    return random.choice(["veer_dubai", "monika_dubai"])
