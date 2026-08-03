// Phase F — Monetization M4: Boosted Flagship Slots.
// Small hook that polls the public runtime endpoint and returns a
// map keyed by station_id → activation object.  Used by FlagshipStrip
// to overlay the "🔥 Boosted" chip on winning cards.
import { useEffect, useState, useMemo } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const POLL_MS = 60_000;   // 1 min refresh — activations shift on hour bounds.


export function useLiveFlagshipBoosts(regionCode) {
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (!regionCode) return undefined;
    let cancelled = false;
    let timer = null;

    const fetchOnce = async () => {
      try {
        const { data } = await axios.get(
          `${API}/flagship/boosts/active`,
          { params: { region_code: regionCode } });
        if (!cancelled) setItems(data?.items || []);
      } catch { /* silent — non-blocking overlay */ }
    };

    fetchOnce();
    timer = setInterval(fetchOnce, POLL_MS);
    return () => { cancelled = true; if (timer) clearInterval(timer); };
  }, [regionCode]);

  const byStationId = useMemo(() => {
    const m = {};
    for (const a of items) {
      if (!a?.station_id) continue;
      // Highest-priority slot wins if there are multiple activations
      // for the same station_id (unusual, but defensive).
      const rank = { primary: 0, secondary: 1, tertiary: 2 };
      const cur = m[a.station_id];
      if (!cur || (rank[a.station_slot] ?? 9) < (rank[cur.station_slot] ?? 9)) {
        m[a.station_id] = a;
      }
    }
    return m;
  }, [items]);

  const recordImpression = async (activationId) => {
    if (!activationId) return;
    try {
      await axios.post(
        `${API}/flagship/boosts/${activationId}/impression`, {},
        { withCredentials: true });
    } catch { /* silent */ }
  };

  return { items, byStationId, recordImpression };
}


export default useLiveFlagshipBoosts;
