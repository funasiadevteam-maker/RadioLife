// Phase STATIC.BOOT.v2 (2026-08-01) — universal image-load probe.
//
// Purpose: some `<img>` elements are cheap to render but expensive to
// FAIL (broken-image icon is jarring UX).  This hook uses a hidden
// `Image()` load/error listener to detect whether the URL resolves
// BEFORE the render commits, so the caller can render a fallback
// gradient/initials placeholder in-place.  Works for both `<img src>`
// AND CSS `background-image: url(...)` because it uses the JS Image
// API which is independent of any DOM `<img>`.
//
// Returns one of: "empty" | "loading" | "ok" | "error"
//   empty   — no URL provided.  Caller should render fallback immediately.
//   loading — probe in flight.  Caller can render skeleton or fallback.
//   ok        — probe succeeded.  Safe to render the URL.
//   error   — probe failed.  Caller must render fallback.

import { useState, useEffect } from "react";

export function useImageProbe(url) {
  const [state, setState] = useState(url ? "loading" : "empty");
  useEffect(() => {
    if (!url) { setState("empty"); return; }
    setState("loading");
    const im = new Image();
    let cancelled = false;
    im.onload    = () => { if (!cancelled) setState("ok"); };
    im.onerror = () => { if (!cancelled) setState("error"); };
    im.src = url;
    return () => { cancelled = true; im.onload = im.onerror = null; };
  }, [url]);
  return state;
}

export default useImageProbe;
