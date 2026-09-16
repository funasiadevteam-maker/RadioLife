// Soft-launch — protected preview entry (/preview).
// Redeems an admin-generated access token (?token=...), stores it, refreshes
// launch status, then bounces to "/" — where RootGate shows the REAL app for
// bypass holders (admins, approved businesses, valid tokens) or Coming Soon.
import React, { useEffect, useState } from "react";
import { useSearchParams, Navigate, Link } from "react-router-dom";
import axios from "axios";
import { useLaunchStore } from "@/hooks/useLaunchStatus";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function PreviewEntry() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [phase, setPhase] = useState("checking");
  const refresh = useLaunchStore((s) => s.refresh);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (token) {
        try {
          await axios.post(`${API}/launch/preview/redeem`, { token }, { withCredentials: true });
          try { localStorage.setItem("rl_preview_token", token); } catch (_e) { /* ignore */ }
          axios.defaults.headers.common["X-Preview-Token"] = token;
        } catch (_e) {
          if (!cancelled) { setPhase("invalid"); return; }
        }
      }
      await refresh();
      if (!cancelled) setPhase("done");
    })();
    return () => { cancelled = true; };
  }, [token, refresh]);

  if (phase === "checking") {
    return (
      <div data-testid="preview-entry-loading" style={{ minHeight: "70vh" }}
        className="nlv2 flex items-center justify-center text-white">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto rounded-full border-2 border-white/20 border-t-white animate-spin" />
          <div className="mt-4 text-sm" style={{ color: "#a8b0cc" }}>Unlocking your preview…</div>
        </div>
      </div>
    );
  }

  if (phase === "invalid") {
    return (
      <div data-testid="preview-entry-invalid" style={{ minHeight: "70vh" }}
        className="nlv2 flex items-center justify-center text-white px-6">
        <div className="max-w-sm w-full nlv2-glass rounded-2xl p-6 text-center">
          <div className="text-lg font-black">Invalid or expired link</div>
          <p className="mt-2 text-sm" style={{ color: "#a8b0cc" }}>
            This preview link is no longer valid. Ask your RadioLife contact for a fresh access link.
          </p>
          <Link to="/" data-testid="preview-entry-home"
            className="mt-4 inline-flex items-center gap-1 px-4 py-2 rounded-full bg-white/10 text-sm font-semibold hover:bg-white/20">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  return <Navigate to="/" replace />;
}
