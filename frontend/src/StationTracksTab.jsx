// Phase D — Owner workspace for picking + uploading station tracks.
//
// Route: `/station/:slug/tracks` (rendered when the logged-in user is
// the station owner).  Three sub-tabs: Browse Catalog, My Station
// Tracks, Upload.  Calls:
//   GET     /api/stations/:slug/catalog/search?q=&genre=&mood=&...
//   GET     /api/stations/:slug/tracks
//   POST    /api/stations/:slug/tracks/add  { track_ids: [...] }
//   DELETE  /api/stations/:slug/tracks/:track_id
//   PATCH   /api/stations/:slug/tracks/reorder { ordered_track_ids }
//   PATCH   /api/stations/:slug/audience  { audience }
//   POST    /api/stations/:slug/tracks/upload  (multipart)
//   GET     /api/stations/:slug/moderation-jobs/:job_id
//
// Status pills:
//   pending                  — orange "Checking…"
//   auto_approved          — green "Added"
//   explicit_auto_flagged  — yellow "Explicit (gated by audience)"
//   pending_admin_review   — orange "Needs review"
//   approved                  — green "Approved (admin)"
//   rejected                  — red "Rejected: <reason>"

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Search, Plus, Upload, X, Trash2, GripVertical, Loader2,
  Music, ChevronLeft, ShieldAlert, Filter, AlertTriangle,
  CheckCircle2, Clock, Headphones, ArrowUpDown,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ──────────────────────────────────────────────────────────
function api(method, url, body, opts = {}) {
  return axios({ method, url, data: body, withCredentials: true, ...opts })
    .then((r) => r.data)
    .catch((err) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail
                              : detail?.message || err.message;
      const wrapped = new Error(msg || "Request failed");
      wrapped.detail = detail;
      wrapped.status = err?.response?.status;
      throw wrapped;
    });
}

function fmtDuration(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec - m * 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

const STATUS_META = {
  pending: { label: "Checking…", color: "#f59e0b", icon: Clock },
  auto_approved: { label: "Added", color: "#22c55e", icon: CheckCircle2 },
  explicit_auto_flagged: { label: "Explicit", color: "#fbbf24", icon: AlertTriangle },
  pending_admin_review: { label: "Needs review", color: "#fb923c", icon: ShieldAlert },
  approved: { label: "Approved", color: "#22c55e", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "#ef4444", icon: X },
};


// ─── Main component ───────────────────────────────────────────────────
export default function StationTracksTab() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("my");
  const [station, setStation] = useState(null);
  const [pool, setPool] = useState([]);
  const [audience, setAudience] = useState("general");
  const [poolLoading, setPoolLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // Phase 42-F.6 — usage snapshot (current/limit/tier) for the
  // station's track pool; refreshed alongside the track list.
  const [usage, setUsage] = useState(null);

  const refreshUsage = useCallback(async () => {
    try {
      const r = await api("GET", `${API}/api/stations/${slug}/usage`);
      setUsage(r);
    } catch { /* non-blocking */ }
  }, [slug]);

  const refreshPool = useCallback(async () => {
    setPoolLoading(true);
    try {
      const r = await api("GET", `${API}/api/stations/${slug}/tracks`);
      setPool(r.pool);
      setAudience(r.audience || "general");
    } catch (e) {
      if (e.status === 403) {
        toast.error("You must be the owner of this station to manage tracks.");
        setTimeout(() => navigate(`/station/${slug}`), 800);
      } else if (e.status === 404) {
        toast.error("Station not found.");
        setTimeout(() => navigate("/"), 800);
      } else {
        toast.error(e.message || "Failed to load station tracks");
      }
    } finally {
      setPoolLoading(false);
    }
  }, [slug, navigate]);

  // Fetch station meta once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api("GET", `${API}/api/stations/${slug}`);
        if (!cancelled) setStation(r.station || r);
      } catch { /* ignore — pool fetch will report errors */ }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  useEffect(() => { refreshPool(); }, [refreshPool]);
  useEffect(() => { refreshUsage(); }, [refreshUsage, pool.length]);

  async function flipAudience(next) {
    setBusy(true);
    try {
      await api("PATCH", `${API}/api/stations/${slug}/audience`,
                          { audience: next });
      setAudience(next);
      toast.success(`Station audience set to "${next}".`);
    } catch (e) {
      toast.error(e.message || "Failed to update audience");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="station-tracks-page"
            style={pageStyle}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <div style={maxWStyle}>
        {/* ─── Header ───────────────────────── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12,
                            marginBottom: 20 }}>
          <Link to={`/station/${slug}`}
                      data-testid="back-to-station"
                      style={iconBtnStyle}>
            <ChevronLeft size={16} />
          </Link>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: "#9aa3af",
                                letterSpacing: 0.7 }}>
              MANAGE TRACKS · {slug}
            </div>
            <h1 style={{ margin: "4px 0 0", fontSize: 22, color: "#e7e7ea" }}>
              {station?.name || slug}
            </h1>
            {station?.tagline && (
              <p style={{ fontSize: 12, color: "#9aa3af", margin: "4px 0 0" }}>
                {station.tagline}
              </p>
            )}
          </div>
        </div>

        {/* ─── Phase 42-F.6 — Usage indicator ───────────── */}
        {usage && (
          <div data-testid="station-usage-pill"
               data-tier={usage.tier}
               data-current={usage.current}
               data-limit={usage.limit}
               style={{ ...cardStyle, marginBottom: 14,
                                display: "flex", gap: 14, alignItems: "center",
                                justifyContent: "space-between", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 2 }}>
                Track pool ({usage.tier === "premium" ? "Premium" : "Free"})
              </div>
              <div style={{ fontSize: 16, color: "#e7e7ea" }}>
                <strong data-testid="usage-current">{usage.current}</strong>
                <span style={{ color: "#9aa3af" }}> / </span>
                <strong data-testid="usage-limit">{usage.limit}</strong>
                <span style={{ color: "#9aa3af", fontSize: 12, marginLeft: 8 }}>
                  ({usage.remaining} remaining)
                </span>
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 200, maxWidth: 320,
                                    height: 6, background: "rgba(255,255,255,0.06)",
                                    borderRadius: 3, overflow: "hidden" }}>
              <div data-testid="usage-bar"
                   style={{
                     height: "100%",
                     width: `${Math.min(100, (usage.current / usage.limit) * 100)}%`,
                     background: usage.current >= usage.limit ? "#ef4444"
                                              : usage.current / usage.limit > 0.8 ? "#f59e0b"
                                              : "#22d3ee",
                     transition: "width .25s ease" }} />
            </div>
            {usage.tier === "free" && (
              <Link to="/premium"
                              data-testid="usage-upgrade-link"
                              style={{ fontSize: 12, color: "#22d3ee",
                                          textDecoration: "none",
                                          padding: "4px 10px",
                                          border: "1px solid rgba(34,211,238,0.4)",
                                          borderRadius: 6 }}>
                Upgrade →
              </Link>
            )}
          </div>
        )}

        {/* ─── Audience toggle ────────────────── */}
        <div data-testid="audience-panel"
                style={{ ...cardStyle, marginBottom: 14,
                            display: "flex", justifyContent: "space-between",
                            alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 2 }}>
              Station audience
            </div>
            <div style={{ fontSize: 11, color: "#71717a", maxWidth: 480 }}>
              <strong style={{ color: "#e7e7ea" }}>
                {audience === "adult" ? "Adult (18+)" : "General"}
              </strong>
              {" — "}
              {audience === "adult"
                ? "Explicit tracks may be added to this station."
                : "Explicit tracks are blocked.  Switch to Adult to allow."}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => flipAudience("general")}
                        disabled={busy || audience === "general"}
                        data-testid="audience-general-btn"
                        style={{
                          ...chipStyle,
                          background: audience === "general" ? "#22c55e22" : "#0c0c10",
                          color: audience === "general" ? "#22c55e" : "#9aa3af",
                          borderColor: audience === "general" ? "#22c55e" : "rgba(255,255,255,0.10)",
                        }}>
              General
            </button>
            <button onClick={() => flipAudience("adult")}
                        disabled={busy || audience === "adult"}
                        data-testid="audience-adult-btn"
                        style={{
                          ...chipStyle,
                          background: audience === "adult" ? "#f9731622" : "#0c0c10",
                          color: audience === "adult" ? "#fb923c" : "#9aa3af",
                          borderColor: audience === "adult" ? "#fb923c" : "rgba(255,255,255,0.10)",
                        }}>
              Adult (18+)
            </button>
          </div>
        </div>

        {/* ─── Sub-tabs ───────────────────────── */}
        <div style={{ display: "flex", gap: 4, marginBottom: 16,
                            borderBottom: "1px solid rgba(255,255,255,0.08)" }}
                data-testid="tracks-subnav">
          {[
            { value: "my", label: `My tracks (${pool.length})`, testid: "subtab-my" },
            { value: "browse", label: "Browse catalog", testid: "subtab-browse" },
            { value: "upload", label: "Upload", testid: "subtab-upload" },
            // Phase 42-F.6 — Live Radio Sources tab.
            { value: "live", label: "Live source", testid: "subtab-live" },
          ].map((t) => (
            <button key={t.value}
                          onClick={() => setTab(t.value)}
                          data-testid={t.testid}
                          style={{ ...subtabBtnStyle,
                                      color: tab === t.value ? "#22d3ee" : "#9aa3af",
                                      borderBottomColor: tab === t.value
                                        ? "#22d3ee" : "transparent" }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ─── Tab body ───────────────────────── */}
        {tab === "my" && (
          <MyPool pool={pool} loading={poolLoading}
                          slug={slug} audience={audience}
                          onChange={refreshPool} />
        )}
        {tab === "browse" && (
          <CatalogBrowse slug={slug} audience={audience}
                                      poolIds={pool.map((p) => p.track_id)}
                                      onAdded={refreshPool} />
        )}
        {tab === "upload" && (
          <UploadPanel slug={slug} audience={audience}
                                  onUploaded={refreshPool} />
        )}
        {tab === "live" && (
          <LiveSourcePanel slug={slug}
                                              onAdded={() => { refreshPool(); refreshUsage(); }} />
        )}
      </div>
    </div>
  );
}


// ─── My pool sub-tab ─────────────────────────────────────────────────
function MyPool({ pool, loading, slug, audience, onChange }) {
  const [dragId, setDragId] = useState(null);
  const [order, setOrder] = useState(pool.map((p) => p.track_id));

  useEffect(() => {
    setOrder(pool.map((p) => p.track_id));
  }, [pool]);

  async function remove(track_id) {
    if (!window.confirm("Remove this track from your station?")) return;
    try {
      await api("DELETE", `${API}/api/stations/${slug}/tracks/${track_id}`);
      toast.success("Removed");
      onChange();
    } catch (e) { toast.error(e.message || "Remove failed"); }
  }

  async function persistReorder(nextIds) {
    try {
      await api("PATCH", `${API}/api/stations/${slug}/tracks/reorder`,
                          { ordered_track_ids: nextIds });
    } catch (e) { toast.error(e.message || "Reorder failed"); }
  }

  function dropOn(targetId) {
    if (!dragId || dragId === targetId) { setDragId(null); return; }
    const next = [...order];
    const from = next.indexOf(dragId);
    const to = next.indexOf(targetId);
    if (from < 0 || to < 0) { setDragId(null); return; }
    next.splice(from, 1);
    next.splice(to, 0, dragId);
    setOrder(next);
    persistReorder(next);
    setDragId(null);
  }

  if (loading) {
    return <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>;
  }
  if (pool.length === 0) {
    return (
      <div data-testid="pool-empty" style={emptyStyle}>
        <Music size={20} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: 13, color: "#9aa3af" }}>
          No tracks on this station yet.  Go to <strong>Browse catalog</strong> to
          pick existing tracks, or <strong>Upload</strong> to add your own.
        </div>
      </div>
    );
  }

  // Stable order display while drag is in progress.
  const indexed = order.map((id) => pool.find((p) => p.track_id === id))
                                                .filter(Boolean);

  return (
    <div data-testid="pool-list"
            style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 11, color: "#71717a", marginBottom: 4,
                          display: "flex", alignItems: "center", gap: 4 }}>
        <ArrowUpDown size={11} /> Drag the grip handle to re-order.  Audience:
        <strong style={{ color: "#e7e7ea", marginLeft: 4 }}>{audience}</strong>
      </div>
      {indexed.map((t) => {
        const isDrag = dragId === t.track_id;
        return (
          <div key={t.track_id}
                  draggable
                  onDragStart={() => setDragId(t.track_id)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => dropOn(t.track_id)}
                  data-testid={`pool-row-${t.track_id}`}
                  style={{ ...rowStyle, opacity: isDrag ? 0.6 : 1,
                              borderColor: isDrag ? "#22d3ee"
                                  : "rgba(255,255,255,0.06)" }}>
            <span style={{ color: "#71717a", cursor: "grab" }}>
              <GripVertical size={14} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center",
                                  flexWrap: "wrap" }}>
                <span style={{ color: "#e7e7ea", fontWeight: 600,
                                          fontSize: 13 }}>{t.title}</span>
                {t.artist && (
                  <span style={{ color: "#9aa3af", fontSize: 12 }}>
                    · {t.artist}
                  </span>
                )}
                {t.explicit_flag && (
                  <span style={explicitPillStyle}
                          data-testid={`pool-explicit-${t.track_id}`}>EXPLICIT</span>
                )}
              </div>
              <div style={{ fontSize: 10, color: "#71717a", marginTop: 2 }}>
                {[fmtDuration(t.duration_sec),
                    t.genre, t.mood, t.language, t.year, t.energy_level]
                  .filter(Boolean).join(" · ")}
              </div>
            </div>
            <button onClick={() => remove(t.track_id)}
                        data-testid={`pool-remove-${t.track_id}`}
                        style={iconBtnStyle}>
              <Trash2 size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}


// ─── Browse catalog sub-tab ──────────────────────────────────────────
function CatalogBrowse({ slug, audience, poolIds, onAdded }) {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState({
    genre: "", mood: "", language: "", era: "", explicit: false,
  });
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState(new Set());
  const debounceRef = useRef(null);
  const poolSet = useMemo(() => new Set(poolIds), [poolIds]);

  const search = useCallback(async (resetPage = true) => {
    const nextPage = resetPage ? 1 : page;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.append("q", q);
      if (filters.genre) params.append("genre", filters.genre);
      if (filters.mood) params.append("mood", filters.mood);
      if (filters.language) params.append("language", filters.language);
      if (filters.era) params.append("era", filters.era);
      if (filters.explicit) params.append("explicit", "true");
      params.append("page", String(nextPage));
      params.append("limit", "30");
      const r = await api("GET",
        `${API}/api/stations/${slug}/catalog/search?${params}`);
      setResults(r.tracks);
      setTotal(r.total);
      setHasMore(r.has_more);
      setPage(nextPage);
    } catch (e) {
      toast.error(e.message || "Search failed");
    } finally { setLoading(false); }
  }, [q, filters, page, slug]);

  // Debounce search by query change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { search(true); }, 250);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, filters.genre, filters.mood, filters.language, filters.era,
        filters.explicit]);

  function toggle(track_id) {
    setPicked((s) => {
      const next = new Set(s);
      if (next.has(track_id)) next.delete(track_id);
      else next.add(track_id);
      return next;
    });
  }

  async function addPicked() {
    if (picked.size === 0) return;
    setLoading(true);
    try {
      const r = await api("POST", `${API}/api/stations/${slug}/tracks/add`,
        { track_ids: Array.from(picked) });
      toast.success(`Added ${r.added?.length || 0} track(s).`);
      if (r.skipped_duplicates?.length) {
        toast.info(`${r.skipped_duplicates.length} already on station.`);
      }
      setPicked(new Set());
      onAdded();
    } catch (e) {
      if (e.detail?.code === "explicit_blocked") {
        toast.error(
          "Explicit tracks can only go on Adult stations.  " +
          "Toggle audience to Adult or unpick those tracks.");
      } else {
        toast.error(e.message || "Add failed");
      }
    } finally { setLoading(false); }
  }

  return (
    <div data-testid="catalog-browse">
      {/* Search bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <Search size={14} style={{ position: "absolute", left: 10,
                                                              top: 11, color: "#71717a" }} />
          <input value={q} onChange={(e) => setQ(e.target.value)}
                      placeholder="Search by title, artist, album…"
                      data-testid="catalog-search-input"
                      style={{ ...inputStyle, paddingLeft: 32 }} />
        </div>
        <button onClick={addPicked} disabled={picked.size === 0 || loading}
                    data-testid="catalog-add-btn"
                    style={{ ...btnPrimaryStyle, opacity: picked.size === 0 ? 0.5 : 1 }}>
          <Plus size={12} /> Add {picked.size > 0 ? `(${picked.size})` : ""}
        </button>
      </div>

      {/* Filters */}
      <div data-testid="catalog-filters"
              style={{ display: "flex", gap: 6, flexWrap: "wrap",
                          marginBottom: 12, fontSize: 11 }}>
        <Filter size={12} color="#9aa3af"
                      style={{ alignSelf: "center", marginRight: 2 }} />
        <input placeholder="genre" value={filters.genre}
                    data-testid="filter-genre"
                    onChange={(e) => setFilters({ ...filters, genre: e.target.value })}
                    style={filterInputStyle} />
        <input placeholder="mood" value={filters.mood}
                    data-testid="filter-mood"
                    onChange={(e) => setFilters({ ...filters, mood: e.target.value })}
                    style={filterInputStyle} />
        <input placeholder="language" value={filters.language}
                    data-testid="filter-language"
                    onChange={(e) => setFilters({ ...filters, language: e.target.value })}
                    style={filterInputStyle} />
        <input placeholder="era (1990s, 2010-2019)" value={filters.era}
                    data-testid="filter-era"
                    onChange={(e) => setFilters({ ...filters, era: e.target.value })}
                    style={filterInputStyle} />
        <label style={{ display: "flex", alignItems: "center", gap: 4,
                                color: "#9aa3af", cursor: "pointer" }}>
          <input type="checkbox" checked={filters.explicit}
                      data-testid="filter-explicit"
                      onChange={(e) => setFilters({ ...filters, explicit: e.target.checked })} />
          Include explicit
          {audience !== "adult" && filters.explicit && (
            <span style={{ color: "#fb923c", marginLeft: 4 }}>
              (station is General — these will be blocked on add)
            </span>
          )}
        </label>
      </div>

      {/* Results */}
      {loading ? (
        <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>
      ) : results.length === 0 ? (
        <div data-testid="catalog-empty" style={emptyStyle}>
          <div style={{ fontSize: 13, color: "#9aa3af" }}>
            No tracks match your search.  Try removing filters or upload your own.
          </div>
        </div>
      ) : (
        <>
          <div style={{ fontSize: 11, color: "#71717a", marginBottom: 6 }}>
            {results.length} of {total} matches
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {results.map((t) => {
              const onStation = poolSet.has(t.track_id);
              const isPicked = picked.has(t.track_id);
              const explicitBlock = t.explicit_flag && audience !== "adult";
              return (
                <button key={t.track_id}
                              onClick={() => !onStation && !explicitBlock && toggle(t.track_id)}
                              disabled={onStation || explicitBlock}
                              data-testid={`catalog-row-${t.track_id}`}
                              style={{ ...rowStyle, cursor: onStation ? "default" : "pointer",
                                          opacity: onStation ? 0.5 : 1,
                                          background: isPicked ? "rgba(34,211,238,0.10)" : "#0c0c10",
                                          borderColor: isPicked ? "#22d3ee" : "rgba(255,255,255,0.06)" }}>
                  <input type="checkbox" checked={isPicked}
                              readOnly disabled={onStation || explicitBlock}
                              data-testid={`catalog-pick-${t.track_id}`}
                              style={{ accentColor: "#22d3ee" }} />
                  <div style={{ flex: 1, textAlign: "left", minWidth: 0 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center",
                                        flexWrap: "wrap" }}>
                      <span style={{ color: "#e7e7ea", fontWeight: 600, fontSize: 13 }}>
                        {t.title}
                      </span>
                      {t.artist && (
                        <span style={{ color: "#9aa3af", fontSize: 12 }}>
                          · {t.artist}
                        </span>
                      )}
                      {t.explicit_flag && (
                        <span style={explicitPillStyle}>EXPLICIT</span>
                      )}
                      {onStation && (
                        <span style={{ ...explicitPillStyle, background: "#22c55e22",
                                              color: "#22c55e" }}>ON STATION</span>
                      )}
                    </div>
                    <div style={{ fontSize: 10, color: "#71717a", marginTop: 2 }}>
                      {[fmtDuration(t.duration_sec),
                          t.genre, t.mood, t.language, t.year]
                        .filter(Boolean).join(" · ")}
                    </div>
                    {explicitBlock && (
                      <div style={{ fontSize: 10, color: "#fb923c", marginTop: 2 }}>
                        Blocked: flip station audience to Adult to add.
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
          {hasMore && (
            <button onClick={() => { setPage(page + 1); search(false); }}
                        style={{ ...btnGhostStyle, width: "100%", marginTop: 10 }}
                        data-testid="catalog-load-more">
              Load more
            </button>
          )}
        </>
      )}
    </div>
  );
}


// ─── Upload sub-tab ──────────────────────────────────────────────────
function UploadPanel({ slug, audience, onUploaded }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [album, setAlbum] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState(null);
  const [dupConfirm, setDupConfirm] = useState(null);
  const fileInput = useRef(null);

  function pick(f) {
    if (!f) return;
    if (f.size > 50 * 1024 * 1024) {
      toast.error("File exceeds 50 MB."); return;
    }
    setFile(f);
    setTitle((t) => t || f.name.replace(/\.[^.]+$/, ""));
  }

  async function startUpload(confirmedDup = false) {
    if (!file) { toast.error("Pick a file first."); return; }
    setUploading(true);
    setJob(null);
    setDupConfirm(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (title) form.append("title", title);
      if (artist) form.append("artist", artist);
      if (album) form.append("album", album);
      if (lyrics) form.append("lyrics", lyrics);
      form.append("confirmed_duplicate", confirmedDup ? "true" : "false");
      const r = await api("POST",
        `${API}/api/stations/${slug}/tracks/upload`, form,
        { headers: { "Content-Type": "multipart/form-data" } });
      if (r.action === "already_in_catalog") {
        toast.success(
          r.added_to_station
            ? "Track already in catalog — added to your station."
            : `Track exists but not added: ${r.add_blocked_reason}`);
        onUploaded();
        resetForm();
      } else if (r.action === "possible_duplicate") {
        setDupConfirm(r);
        toast.info("Possible duplicate detected — confirm to proceed.");
      } else if (r.action === "moderation_queued") {
        setJob({ status: "pending", job_id: r.moderation_job_id });
        pollJob(r.moderation_job_id);
      }
    } catch (e) {
      if (e.detail?.code === "rate_limited") {
        toast.error(`Rate limited.  ${e.detail.message}`);
      } else if (e.detail?.code === "file_too_large") {
        toast.error("File exceeds 50 MB.");
      } else {
        toast.error(e.message || "Upload failed");
      }
    } finally { setUploading(false); }
  }

  function resetForm() {
    setFile(null); setTitle(""); setArtist(""); setAlbum(""); setLyrics("");
    if (fileInput.current) fileInput.current.value = "";
  }

  async function pollJob(jobId, attempts = 0) {
    if (attempts > 40) return; // ~2 minutes max
    try {
      const r = await api("GET",
        `${API}/api/stations/${slug}/moderation-jobs/${jobId}`);
      setJob(r);
      if (r.status === "pending") {
        setTimeout(() => pollJob(jobId, attempts + 1), 1500);
      } else {
        onUploaded();
      }
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div data-testid="upload-panel">
      {!file ? (
        <div data-testid="upload-dropzone"
                onClick={() => fileInput.current?.click()}
                onDrop={(e) => {
                  e.preventDefault();
                  pick(e.dataTransfer.files[0]);
                }}
                onDragOver={(e) => e.preventDefault()}
                style={dropzoneStyle}>
          <Upload size={28} color="#22d3ee" />
          <div style={{ marginTop: 12, fontSize: 14, color: "#e7e7ea" }}>
            Drop an audio file here or click to browse
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: "#9aa3af" }}>
            MP3 / WAV / M4A / FLAC · max 50 MB
          </div>
          <input ref={fileInput} type="file" hidden
                      accept=".mp3,.wav,.m4a,.flac,audio/*"
                      data-testid="upload-file-input"
                      onChange={(e) => pick(e.target.files?.[0])} />
        </div>
      ) : (
        <div style={cardStyle}>
          <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "center", marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 13, color: "#e7e7ea", fontWeight: 600 }}>
                {file.name}
              </div>
              <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </div>
            </div>
            <button onClick={resetForm} style={iconBtnStyle}
                        data-testid="upload-clear-btn">
              <X size={14} />
            </button>
          </div>
          <div style={{ display: "grid",
                              gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <Field label="Title">
              <input value={title} onChange={(e) => setTitle(e.target.value)}
                          data-testid="upload-title-input"
                          style={inputStyle} />
            </Field>
            <Field label="Artist">
              <input value={artist} onChange={(e) => setArtist(e.target.value)}
                          data-testid="upload-artist-input"
                          style={inputStyle} />
            </Field>
            <Field label="Album (optional)">
              <input value={album} onChange={(e) => setAlbum(e.target.value)}
                          data-testid="upload-album-input"
                          style={inputStyle} />
            </Field>
            <Field label="Lyrics (optional, helps moderation)">
              <textarea rows={2} value={lyrics}
                                onChange={(e) => setLyrics(e.target.value)}
                                data-testid="upload-lyrics-input"
                                style={{ ...inputStyle, minHeight: 38,
                                            resize: "vertical" }} />
            </Field>
          </div>
          {dupConfirm ? (
            <div data-testid="upload-dup-confirm"
                    style={{ marginTop: 14, background: "rgba(251,191,36,0.10)",
                                border: "1px solid rgba(251,191,36,0.30)",
                                borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600 }}>
                <AlertTriangle size={12}
                  style={{ verticalAlign: -1, marginRight: 4 }} />
                Possible duplicate detected
              </div>
              <div style={{ fontSize: 11, color: "#e7e7ea", marginTop: 6 }}>
                Catalog already has: <strong>{dupConfirm.candidate_title}</strong>
                {dupConfirm.candidate_artist
                  && ` by ${dupConfirm.candidate_artist}`}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <button onClick={() => startUpload(true)}
                            disabled={uploading}
                            data-testid="upload-dup-confirm-yes"
                            style={btnPrimaryStyle}>
                  Yes — use that track
                </button>
                <button onClick={() => setDupConfirm(null)}
                            style={btnGhostStyle}
                            data-testid="upload-dup-confirm-no">
                  No — change my title
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => startUpload(false)}
                        disabled={uploading || !file}
                        data-testid="upload-submit-btn"
                        style={{ ...btnPrimaryStyle, marginTop: 14 }}>
              {uploading ? (
                <><Loader2 size={12} className="spin" /> Uploading…</>
              ) : (
                <><Upload size={12} /> Upload + moderate</>
              )}
            </button>
          )}
          {job && (
            <ModerationStatus job={job} audience={audience} />
          )}
        </div>
      )}
    </div>
  );
}


function ModerationStatus({ job, audience }) {
  const meta = STATUS_META[job.status] || STATUS_META.pending;
  const Icon = meta.icon;
  return (
    <div data-testid={`mod-status-${job.status}`}
            style={{ marginTop: 14, background: `${meta.color}11`,
                        border: `1px solid ${meta.color}55`,
                        borderRadius: 6, padding: 10 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <Icon size={14} color={meta.color} />
        <span style={{ fontSize: 13, color: meta.color, fontWeight: 700 }}>
          {meta.label}
        </span>
      </div>
      {job.decision_reason && (
        <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 4 }}>
          {job.decision_reason}
        </div>
      )}
      {job.rejection_reason && (
        <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 4 }}>
          Reason: {job.rejection_reason}
        </div>
      )}
      {job.moderation_categories?.length > 0 && (
        <div style={{ fontSize: 10, color: "#71717a", marginTop: 4 }}>
          Categories: {job.moderation_categories.join(", ")}
        </div>
      )}
      {job.status === "explicit_auto_flagged" && audience !== "adult" && (
        <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 4 }}>
          Track is in the catalog but NOT on your station — switch
          audience to Adult to add it.
        </div>
      )}
    </div>
  );
}


// ─── Phase 42-F.6 — Live Radio Sources panel ────────────────────────
function LiveSourcePanel({ slug, onAdded }) {
  const [q, setQ] = useState("");
  const [imports, setImports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  // Reuse the existing imported-stations browse endpoint
  // (Phase 42-A1).  We page through the active list and let the owner
  // pick one to pin as a "live source" track.
  useEffect(() => {
    let cancel = false;
    setLoading(true);
    api("GET", `${API}/api/live-radio/stations`, null,
            { params: { query: q || undefined, limit: 24 } })
      .then((r) => { if (!cancel) setImports(r.stations || r.items || r || []); })
      .catch(() => { if (!cancel) setImports([]); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [q]);

  async function pin(stationRow) {
    setBusyId(stationRow.id);
    try {
      const r = await api("POST",
        `${API}/api/stations/${slug}/tracks/from-imported`,
        { imported_station_id: stationRow.id });
      if (r.already_on_station) {
        toast.info(`${stationRow.name} already added.`);
      } else {
        toast.success(`Added "${stationRow.name}" as a live source.`);
      }
      onAdded && onAdded();
    } catch (e) {
      if (e.detail && e.detail.code === "pool_cap_reached") {
        toast.error(`${e.detail.tier} cap reached: ${e.detail.current}/${e.detail.limit}`);
      } else {
        toast.error(e.message || "Failed to pin source");
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div data-testid="live-source-panel">
      <div style={{ display: "flex", gap: 8, marginBottom: 14,
                              alignItems: "center" }}>
        <Search size={14} color="#9aa3af" />
        <input
          type="text"
          placeholder="Search imported live stations..."
          value={q}
          data-testid="live-source-search"
          onChange={(e) => setQ(e.target.value)}
          style={{ ...inputStyle, marginTop: 0 }}
        />
      </div>
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 6,
                                color: "#9aa3af", padding: 20 }}>
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : imports.length === 0 ? (
        <div data-testid="live-source-empty"
                style={{ color: "#9aa3af", padding: 20, fontSize: 13 }}>
          No imported stations match. Try clearing the search box.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0,
                              display: "grid", gap: 6 }}>
          {imports.map((it) => (
            <li key={it.id}
                  data-testid={`live-source-${it.id}`}
                  style={{ ...rowStyle, justifyContent: "space-between" }}>
              <div style={{ overflow: "hidden", flex: 1 }}>
                <div style={{ color: "#e7e7ea", fontSize: 13,
                                          fontWeight: 500,
                                          whiteSpace: "nowrap",
                                          textOverflow: "ellipsis",
                                          overflow: "hidden" }}>
                  {it.name}
                </div>
                <div style={{ color: "#71717a", fontSize: 11 }}>
                  {it.country || "—"} · {it.language || "—"}
                  {it.bitrate ? ` · ${it.bitrate}kbps` : ""}
                </div>
              </div>
              <button
                onClick={() => pin(it)}
                disabled={busyId === it.id}
                data-testid={`live-source-pin-${it.id}`}
                style={{
                  ...chipStyle,
                  background: "#22d3ee22",
                  color: "#22d3ee",
                  borderColor: "rgba(34,211,238,0.4)",
                  cursor: busyId === it.id ? "wait" : "pointer",
                  opacity: busyId === it.id ? 0.5 : 1,
                }}>
                {busyId === it.id ? "…" : "Pin"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


// ─── Layout helpers ──────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <label style={{ fontSize: 11, color: "#9aa3af", display: "block" }}>
      {label}
      {children}
    </label>
  );
}


// ─── Style tokens ────────────────────────────────────────────────────
const pageStyle = { minHeight: "100vh", background: "#080809",
                                    padding: 24, color: "#e7e7ea" };
const maxWStyle = { maxWidth: 960, margin: "0 auto" };
const cardStyle = { background: "#0c0c10",
                                    border: "1px solid rgba(255,255,255,0.06)",
                                    borderRadius: 10, padding: 14 };
const rowStyle = {
  display: "flex", alignItems: "center", gap: 8,
  background: "#0c0c10", border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 6, padding: "8px 10px", fontFamily: "inherit",
  color: "inherit",
};
const inputStyle = {
  width: "100%", marginTop: 4, padding: "8px 10px",
  background: "#0a0a0c", border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 6, color: "#e7e7ea", fontSize: 12, outline: "none",
};
const filterInputStyle = {
  ...inputStyle, marginTop: 0, width: 120, padding: "5px 8px",
  fontSize: 11,
};
const btnPrimaryStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "7px 12px", background: "#22d3ee", border: "none",
  borderRadius: 6, color: "#0a0a0c", fontSize: 12, fontWeight: 700,
  cursor: "pointer", letterSpacing: 0.3,
};
const btnGhostStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "6px 10px", background: "transparent",
  border: "1px solid rgba(255,255,255,0.12)", borderRadius: 5,
  color: "#e7e7ea", fontSize: 12, cursor: "pointer",
};
const iconBtnStyle = {
  ...btnGhostStyle, padding: "5px 6px", minWidth: 28,
};
const subtabBtnStyle = {
  padding: "10px 14px", background: "transparent", border: "none",
  borderBottom: "2px solid transparent", fontSize: 13, fontWeight: 600,
  cursor: "pointer",
};
const chipStyle = {
  padding: "5px 12px", borderRadius: 999, border: "1px solid",
  fontSize: 11, fontWeight: 600, cursor: "pointer", letterSpacing: 0.4,
};
const emptyStyle = {
  padding: 32, textAlign: "center", color: "#9aa3af",
  border: "1px dashed rgba(255,255,255,0.10)", borderRadius: 8,
};
const explicitPillStyle = {
  fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
  padding: "2px 6px", borderRadius: 4,
  background: "#fb923c22", color: "#fb923c",
};
const dropzoneStyle = {
  border: "2px dashed rgba(34,211,238,0.30)",
  borderRadius: 12, padding: 48, textAlign: "center",
  cursor: "pointer", background: "rgba(34,211,238,0.04)",
};
