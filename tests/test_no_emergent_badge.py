"""
Regression guard — no "Made with Emergent" badge anywhere in our source
OR in the built bundle served to users.

Scope:
 • /app/frontend/public/*.html
 • /app/frontend/src/**/*.{js,jsx,ts,tsx,css}
 • /app/mobile/**/*.{js,jsx,ts,tsx,html,json}
 • Built bundle (the JS the browser actually receives) — best-effort:
     looks in /app/frontend/build/static/js/*.js if present, otherwise
     fetches the dev-server's bundle from the configured preview URL.

node_modules and build artefacts are excluded from the SOURCE scan —
third-party libraries may legitimately reference the string for
unrelated reasons.
"""
from __future__ import annotations
import os
import re
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path("/app")
NEEDLES = ("Made with Emergent", "MadeWithEmergent")
SCAN_DIRS = [
    ROOT / "frontend" / "public",
    ROOT / "frontend" / "src",
    ROOT / "mobile",
]
EXTS = {".html", ".js", ".jsx", ".ts", ".tsx", ".css", ".json"}
IGNORE_PARTS = {"node_modules", "build", ".next", "dist", ".expo"}


def _iter_files():
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in IGNORE_PARTS for part in p.parts):
                continue
            if p.suffix.lower() not in EXTS:
                continue
            yield p


def test_no_made_with_emergent_string_in_source():
    """No source file contains the literal "Made with Emergent" string."""
    hits = []
    for p in _iter_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for needle in NEEDLES:
            if needle in text:
                hits.append((str(p), needle))
    assert not hits, (
        "Found 'Made with Emergent' badge references in source:\n  "
        + "\n  ".join(f"{f}  → {n!r}" for f, n in hits)
    )


def test_no_emergent_badge_selector_in_source():
    """`emergent-badge` (id/selector) only allowed in defensive code that
    hides or removes the platform-injected element:
        • /app/frontend/src/index.css — global CSS hide rule
        • /app/frontend/src/shell/AppShell.jsx — runtime MutationObserver
    No JS / JSX / HTML elsewhere may carry the string."""
    DEFENSIVE = {
        ROOT / "frontend" / "src" / "index.css",
        ROOT / "frontend" / "src" / "shell" / "AppShell.jsx",
        ROOT / "frontend" / "src" / "shell" / "__tests__" / "Phase15c.test.jsx",
    }
    hits = []
    for p in _iter_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        if "emergent-badge" in text and p not in DEFENSIVE:
            hits.append(str(p))
    assert not hits, (
        "`emergent-badge` selector leaked outside defensive code:\n  "
        + "\n  ".join(hits)
    )


def test_no_emergent_main_js_script_in_public_html():
    """No <script> tag loading the Emergent badge bundle."""
    pattern = re.compile(r"emergent[-_/]main\.js|emergentagent\.com/.+/badge", re.I)
    hits = []
    for p in (ROOT / "frontend" / "public").rglob("*.html"):
        if pattern.search(p.read_text(encoding="utf-8", errors="replace")):
            hits.append(str(p))
    assert not hits, f"Emergent badge script tag still present in: {hits}"


# ─── Bundle.js content guard ───────────────────────────────────────────────
# The user's tester fetched the live bundle and found the strings inside.
# We replicate that: if `build/static/js/*.js` exists, scan it; otherwise
# fetch the dev bundle from the preview origin (best effort — skipped if
# offline). Either way, NEEDLES + the "emergent-badge" id must not appear.

def _gather_bundle_text() -> list[tuple[str, str]]:
    """Return [(label, text), ...] for each bundle source we can read."""
    out: list[tuple[str, str]] = []
    # 1. Built bundle, if produced.
    for p in (ROOT / "frontend" / "build" / "static" / "js").glob("*.js") \
                  if (ROOT / "frontend" / "build" / "static" / "js").exists() else []:
        out.append((f"build:{p.name}", p.read_text(encoding="utf-8", errors="replace")))
    # 2. Dev bundle from preview (best-effort).
    env_path = ROOT / "frontend" / ".env"
    base_url = None
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                base_url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if base_url:
        # Default CRA dev bundle entrypoint.
        for path in ("/static/js/bundle.js", "/static/js/main.chunk.js"):
            url = base_url.rstrip("/") + path
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    if resp.status == 200:
                        out.append((f"live:{path}", resp.read().decode("utf-8", "replace")))
                        break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                continue
    return out


def test_built_bundle_has_no_badge_strings():
    """Bundle.js (built or live) must NOT contain 'Made with Emergent'
    or 'emergent-badge'."""
    bundles = _gather_bundle_text()
    if not bundles:
        # No bundle available to scan (no build artefact, no reachable
        # preview). We don't fail in that case — the source-side tests
        # above cover the regression. Mark as skipped so it's visible.
        import pytest
        pytest.skip("No bundle.js available (no build artefact, no preview reachable)")
    bad = []
    for label, text in bundles:
        for needle in ("Made with Emergent", "MadeWithEmergent", "emergent-badge"):
            if needle in text:
                bad.append((label, needle))
    assert not bad, (
        "Badge strings still present in bundle:\n  "
        + "\n  ".join(f"{lbl}  → {n!r}" for lbl, n in bad)
    )
