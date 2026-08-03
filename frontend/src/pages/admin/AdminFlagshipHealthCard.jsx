// Phase FUN.1.1 — Admin flagship health widget.
// Compact card for the AdminHealth overview.  Aggregates flagship counts
// (AE / US / priority-Dubai / needs-stream / fallback-logo) with a
// "View unreachable" link that filters the admin flagship page.

import { useEffect, useState } from "react";
import axios from "axios";
import { Radio, AlertTriangle, ExternalLink, Loader2 } from "lucide-react";
import { Card } from "@/shell/primitives";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminFlagshipHealthCard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/admin/stations/flagship`);
        const items = data.items || [];
        const ae = items.filter((s) => s.flagship_region === "AE").length;
        const us = items.filter((s) => s.flagship_region === "US").length;
        const needsStream = items.filter(
          (s) => s.needs_stream_review === true).length;
        const fallbackLogo = items.filter(
          (s) => !s.logo_url || String(s.logo_url).includes("ui-avatars.com")).length;
        const unreachable = items.filter(
          (s) => s.playable_status === "unreachable").length;
        // Priority stations count (separate endpoint).
        let priority = 0;
        try {
          const { data: pd } = await axios.get(`${API}/stations/priority?limit=1`);
          priority = pd.count || 0;
        } catch (_) {}
        setStats({ ae, us, needsStream, fallbackLogo, unreachable, priority,
                              total: items.length });
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <Card data-testid="admin-flagship-health-card"
                className="p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio size={16} className="text-accent-electric" />
          <h3 className="font-display font-bold text-sm uppercase tracking-widest">
            Flagship Fleet
          </h3>
        </div>
        <a href="/admin/flagship-stations"
              data-testid="admin-flagship-health-card-viewall"
              className="text-[10px] font-mono uppercase tracking-widest
                                  text-accent-electric hover:underline
                                  inline-flex items-center gap-0.5">
          View all <ExternalLink size={10} />
        </a>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-text-secondary py-4">
          <Loader2 size={12} className="animate-spin" /> Loading…
        </div>
      ) : !stats ? (
        <div className="text-xs text-text-secondary">Unable to load flagship stats.</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="AE" value={stats.ae} testid="admin-flagship-stat-ae" />
            <Stat label="US" value={stats.us} testid="admin-flagship-stat-us" />
            <Stat label="Priority-Dubai" value={stats.priority}
                        testid="admin-flagship-stat-priority" />
          </div>
          <div className="grid grid-cols-3 gap-3 pt-2 border-t border-white/10">
            <Stat label="Needs stream" value={stats.needsStream}
                        alert={stats.needsStream > 0}
                        testid="admin-flagship-stat-needs-stream" />
            <Stat label="Fallback logo" value={stats.fallbackLogo}
                        alert={stats.fallbackLogo > 0}
                        testid="admin-flagship-stat-fallback-logo" />
            <Stat label="Unreachable" value={stats.unreachable}
                        alert={stats.unreachable > 0}
                        testid="admin-flagship-stat-unreachable" />
          </div>
          {stats.unreachable > 0 && (
            <a href="/admin/flagship-stations?filter=unreachable"
                  data-testid="admin-flagship-view-unreachable"
                  className="inline-flex items-center gap-1 text-xs
                                          text-rose-400 hover:text-rose-300 hover:underline">
              <AlertTriangle size={12} />
              View {stats.unreachable} unreachable station{stats.unreachable > 1 ? "s" : ""}
            </a>
          )}
        </>
      )}
    </Card>
  );
}

function Stat({ label, value, alert, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-[9px] font-mono uppercase tracking-widest text-text-secondary">
        {label}
      </div>
      <div className={`mt-1 font-bold text-xl ${
                                alert ? "text-amber-400" : "text-text-primary"}`}>
        {value}
      </div>
    </div>
  );
}
