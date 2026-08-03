/** Phase 41M.B — Top Fans section on StationPage.
 *
 * Public surface — lists top 10 fans by badge count + lifetime listen
 * minutes. Hides cleanly when no fans yet.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Trophy, Headphones } from "lucide-react";
import { API } from "@/AuthContext";
import BadgeChip from "@/components/BadgeChip";

function fmtMinutes(m) {
  if (!m) return "0m";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest > 0 ? `${h}h ${rest}m` : `${h}h`;
}

function initials(name) {
  return (name || "?")
    .split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
}

export default function TopFansSection({ slug, limit = 10 }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/stations/${slug}/top_fans?limit=${limit}`);
        if (alive) setData(r.data);
      } catch {
        if (alive) setData({ top_fans: [], count: 0 });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [slug, limit]);

  // Layout-shift hygiene: reserve same height while loading.
  if (loading) {
    return (
      <div data-testid="top-fans-loading"
           style={{ marginTop: 28, minHeight: 80, opacity: 0.4 }}>
        <SectionHeader />
      </div>
    );
  }

  const fans = data?.top_fans || [];
  const badgeMeta = data?.badge_meta || {};
  if (fans.length === 0) {
    return null;   // gracefully hide on empty
  }

  return (
    <div data-testid="top-fans-section" style={{ marginTop: 32 }}>
      <SectionHeader />
      <div style={{ display: "grid",
                     gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                     gap: 10, marginTop: 12 }}>
        {fans.map((f, i) => (
          <div key={f.user_id}
               data-testid={`top-fan-row-${f.user_id}`}
               style={{ display: "flex", alignItems: "center", gap: 10,
                         padding: 10, borderRadius: 10,
                         background: "rgba(255,255,255,0.03)",
                         border: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ display: "flex", alignItems: "center",
                           justifyContent: "center",
                           width: 32, height: 32, borderRadius: "50%",
                           background: "rgba(34,211,238,0.12)",
                           color: "#22d3ee",
                           fontSize: 12, fontWeight: 700,
                           flexShrink: 0 }}>
              {i + 1 <= 3 ? "🏆" : initials(f.name)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: "#fff",
                             fontWeight: 600,
                             overflow: "hidden",
                             textOverflow: "ellipsis",
                             whiteSpace: "nowrap" }}>
                {f.name}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6,
                             fontSize: 10, color: "#9aa3af",
                             marginTop: 2 }}>
                <Headphones size={9} />
                <span>{fmtMinutes(f.listen_minutes)}</span>
                <span style={{ opacity: 0.4 }}>·</span>
                <span>{f.badge_count} badge{f.badge_count === 1 ? "" : "s"}</span>
              </div>
              {f.badge_types && f.badge_types.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap",
                               gap: 2, marginTop: 4 }}>
                  {f.badge_types.slice(0, 3).map((bt) => {
                    const meta = badgeMeta[bt] || {};
                    return (
                      <BadgeChip key={bt}
                                  badge={{ badge_type: bt,
                                           label: meta.label || bt,
                                           icon: meta.icon,
                                           criteria_text: meta.criteria_text }} />
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionHeader() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Trophy size={14} color="#fbbf24" />
      <h3 style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                    letterSpacing: 1.4, fontFamily: "monospace",
                    margin: 0 }}>
        TOP FANS
      </h3>
    </div>
  );
}
