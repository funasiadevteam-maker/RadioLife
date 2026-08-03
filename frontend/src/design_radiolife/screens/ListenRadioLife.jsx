// Phase R.1 — Listen (radio directory).
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Search } from "lucide-react";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import { RLChip } from "../DesignSystem";
import StationRow from "../components/StationRow";
import FlagshipStrip from "@/components/FlagshipStrip";

// Derived genre buckets — mapped from channel taxonomy / free-form tags.
const GENRES = [
  { id: "all", label: "All" },
  { id: "vip", label: "VIP" },
  { id: "party", label: "Party" },
  { id: "chill", label: "Chill" },
  { id: "devotional", label: "Devotional" },
  { id: "retro", label: "Retro" },
  { id: "workout", label: "Workout" },
];

function genreOf(channel) {
  const key = `${channel.slug || ""} ${channel.name || ""} ${channel.tagline || ""}`.toLowerCase();
  if (key.includes("vip") || key.includes("premium")) return "vip";
  if (key.includes("party") || key.includes("dance")) return "party";
  if (key.includes("lounge") || key.includes("chill") || key.includes("late night")) return "chill";
  if (key.includes("devotional") || key.includes("mehfil")) return "devotional";
  if (key.includes("retro") || key.includes("classic")) return "retro";
  if (key.includes("workout") || key.includes("gym") || key.includes("running")) return "workout";
  return "other";
}

export default function ListenRadioLife() {
  const [channels, setChannels] = useState([]);
  const [genre, setGenre] = useState("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    axios.get(`${API}/channels`)
      .then((r) => setChannels(r.data?.channels || []))
      .catch(() => setChannels([]));
  }, []);

  const filtered = useMemo(() => {
    let list = channels;
    if (genre !== "all") list = list.filter((c) => genreOf(c) === genre);
    const ql = q.trim().toLowerCase();
    if (ql) {
      list = list.filter((c) => `${c.name} ${c.slug} ${c.tagline || ""}`
                                            .toLowerCase().includes(ql));
    }
    return list;
  }, [channels, genre, q]);

  // Phase F — pass user's country_code so FlagshipStrip can overlay
  // the "🔥 Boosted" chip on any winning card.
  const country = useGeoStore((s) => s.country);

  return (
    <div className="px-4 pt-6 pb-6 space-y-4" data-testid="rl-listen-page">
      <header>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">
          Listen
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          {channels.length} channels · non-stop personalised radio
        </p>
      </header>

      {/* Phase A Item 2 — Flagship rail with purple/pink gradient ring
          on each card (visual parity with Legacy dark mode's flagship
          treatment).  Renders nothing when no flagships are available. */}
      <FlagshipStrip
        light={true}
        variant="grid"
        limit={6}
        matchesCountryCode={country || null}
        title="Flagship Stations"
        testId="rl-listen-flagship-strip" />

      {/* Search */}
      <div className="relative">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2
                                                    text-slate-400 pointer-events-none" />
        <input
          type="text"
          placeholder="Search stations, moods…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="rl-listen-search-input"
          className="w-full h-11 pl-10 pr-3 rounded-full bg-white
                              border border-slate-200 focus:border-purple-400
                              focus:outline-none focus:ring-2 focus:ring-purple-400/20
                              text-sm placeholder:text-slate-400" />
      </div>

      {/* Genre chips */}
      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1"
                data-testid="rl-genre-chips">
        {GENRES.map((g) => (
          <RLChip
            key={g.id}
            active={genre === g.id}
            onClick={() => setGenre(g.id)}
            data-testid={`rl-genre-${g.id}`}>
            {g.label}
          </RLChip>
        ))}
      </div>

      {/* Station list */}
      <div className="space-y-2" data-testid="rl-station-list">
        {filtered.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-2xl border border-slate-100">
            <div className="font-semibold text-slate-900">No stations match your filter</div>
            <div className="text-sm text-slate-500 mt-1">Try a different genre or search term.</div>
          </div>
        ) : (
          filtered.map((c) => <StationRow key={c.slug} channel={c} />)
        )}
      </div>
    </div>
  );
}
