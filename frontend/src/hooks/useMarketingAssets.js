// Phase Π+3 — useMarketingAssets — small hook that reads
// `GET /api/marketing/assets` and returns `{key -> image_url}`.
//
// Why:  the AI-generated hero images for the /for-business, /for-advertisers
// and `/` landing feature tiles (`live_trivia`, `game_campaigns`,
// `coupon_wallet`, `audio_ads`, `sponsored_games`, `route_based_ads`,
// `mobile_hero`) live in `marketing_assets` and are served through the
// Tigris fallback CDN.  The marketing pages used to render only
// lucide-react icons because they never consumed this endpoint.
//
// Result is cached at module scope so multiple mounts of the marketing
// pages don't re-fetch.
//
// Phase STATIC.BOOT.v2 (2026-08-01) — bundled fallback.  The 18
// landing hero images ARE ALSO shipped as webpack-imported assets via
// `@/assets/landing/index.js` so `urlFor(key)` NEVER returns an empty
// string for those keys — even before the API responds, even if the
// backend static files went missing in a bad deploy.  The bundled URL
// wins over the API URL to guarantee prod parity with dev.
import { useEffect, useState } from "react";
import axios from "axios";
import { LANDING_IMAGES } from "@/assets/landing";

const API      = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const BASE_URL = process.env.REACT_APP_BACKEND_URL || "";

let _cache          = null;      // Promise<{by_key, items}> once loaded.
let _resolved   = null;    // synchronous copy for re-mounts.

async function _load() {
    if (_resolved) return _resolved;
    if (!_cache) {
        _cache = axios.get(`${API}/marketing/assets`)
            .then((r) => r?.data || { by_key: {}, items: [] })
            .catch(() => ({ by_key: {}, items: [] }));
    }
    _resolved = await _cache;
    return _resolved;
}

/**
 * Returns `{ byKey, urlFor, isLoading }`.
 *
 * `urlFor(key)` returns an absolute URL (prefixed with
 * `REACT_APP_BACKEND_URL`) OR the bundled asset URL from webpack
 * — the bundled URL wins whenever the key exists in
 * `LANDING_IMAGES`.  Returns "" only when the key is unknown
 * to both the bundle AND the API.
 */
export function useMarketingAssets() {
    const [byKey, setByKey]          = useState(_resolved?.by_key || {});
    const [isLoading, setIsLoading] = useState(!_resolved);

    useEffect(() => {
        let alive = true;
        _load().then((r) => {
            if (!alive) return;
            setByKey(r.by_key || {});
            setIsLoading(false);
        });
        return () => { alive = false; };
    }, []);

    const urlFor = (key) => {
        // 1. BUNDLED wins — guaranteed to exist as a hashed webpack
        //    asset in the built bundle, regardless of prod deploy state.
        const bundled = key && LANDING_IMAGES[key];
        if (bundled) return bundled;
        // 2. API-provided fallback — still supported for CMS-driven
        //    keys not in the bundle.
        const rel = key && byKey[key];
        if (!rel) return "";
        if (rel.startsWith("http://") || rel.startsWith("https://")) return rel;
        return `${BASE_URL}${rel}`;
    };

    return { byKey, urlFor, isLoading };
}

export default useMarketingAssets;
