// Phase RWD.3 — Premium client helpers (web).
import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

export async function fetchPremiumStatus() {
  const r = await axios.get(`${API}/me/premium/status`);
  return r.data;
}

export function usePremiumStatus() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancel = false;
    fetchPremiumStatus()
      .then((d) => { if (!cancel) setData(d); })
      .catch(() => {})
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, []);
  return { data, loading };
}
