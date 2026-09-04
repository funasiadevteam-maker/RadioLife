// Phase FUN.1 → FLAGADMIN.1 — Admin flagship-station management.
// Route: /admin/flagship-stations  ·  admin only.
//
// Phase FLAGADMIN.1 additions:
//   • Full CRUD (Add / Edit / Delete) via modals
//   • Per-station Pre-roll toggle (default ON — parity with community stations)
//   • Stream-URL curl validate button (warn-only, does NOT reject)
//   • Type-slug-to-confirm hard-delete guard
import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import {
  Star, RefreshCw, Loader2, AlertCircle, CheckCircle2, XCircle,
  ExternalLink, Upload, Plus, Pencil, Trash2, ShieldAlert,
  Radio, ChevronDown, Sparkles, ImagePlus,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useEffectivePageVariant } from "@/hooks/useDesignVariant";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_STYLES = {
  healthy:         "bg-emerald-500/15 text-emerald-500",
  pending:         "bg-amber-500/15 text-amber-500",
  unreachable: "bg-red-500/15 text-red-400",
};

const EMPTY_FORM = {
  name: "",
  homepage: "",
  frequency: "",
  stream_url: "",
  logo_url: "",
  country: "",
  country_code: "",
  city: "",
  flagship_region: "",
  flagship_priority: 150,
  flagship_categories_csv: "home,music",
  languages_csv: "english",
  description: "",
  preroll_enabled: true,
};

export default function AdminFlagshipStations() {
  const variant = useEffectivePageVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refresher, setRefresher] = useState(0);
  const [busy, setBusy] = useState(false);
  const [genIds, setGenIds] = useState(() => new Set());   // stations mid AI-generation
  const [toast, setToast] = useState(null);   // { kind, message }

  // Modal state.
  const [addOpen, setAddOpen] = useState(false);
  const [editRow, setEditRow] = useState(null);
  const [deleteRow, setDeleteRow] = useState(null);

  const showToast = useCallback((kind, message) => {
    setToast({ kind, message });
    window.setTimeout(() => setToast(null), 4500);
  }, []);

  useEffect(() => {
    if (authLoading || user?.role !== "admin") return;
    setLoading(true);
    (async () => {
      try {
        const { data } = await axios.get(`${API}/admin/stations/flagship`);
        setItems(data.items || []);
      } catch (_) { /* empty — non-admin routes silently rejected upstream */ }
      finally { setLoading(false); }
    })();
  }, [refresher, user, authLoading]);

  if (authLoading) return null;
  if (user?.role !== "admin") {
    return (
      <div className={`${light ? "bg-white text-slate-900" : "bg-slate-950 text-white"} min-h-screen p-8 flex items-center justify-center`}
                data-testid="admin-flagship-forbidden">
        <div className="text-center">
          <AlertCircle className="w-10 h-10 text-red-500 mx-auto" />
          <div className="mt-3 font-bold text-lg">Admin access required</div>
        </div>
      </div>
    );
  }

  async function runHealthCheck() {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/stations/flagship/health-check`);
      setRefresher((n) => n + 1);
      showToast("success", "Health check complete");
    } catch (e) {
      showToast("error", "Health check failed");
    } finally { setBusy(false); }
  }
  async function reseed() {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/stations/flagship/seed`);
      setRefresher((n) => n + 1);
      showToast("success", "Manifest re-seeded");
    } finally { setBusy(false); }
  }
  async function healArt() {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/imported-stations/ensure-flagship-art`);
      const n = data?.queued || 0;
      showToast("success", n
        ? `Regenerating art for ${n} station${n > 1 ? "s" : ""}… tiles refresh shortly`
        : "All flagship artwork is healthy");
      if (n) window.setTimeout(() => setRefresher((x) => x + 1), 20000);
    } catch (_) {
      showToast("error", "Heal artwork failed");
    } finally { setBusy(false); }
  }
  async function togglePreroll(row) {
    setBusy(true);
    try {
      const next = !(row.preroll_enabled !== false);   // default true
      await axios.patch(`${API}/admin/stations/flagship/${row.id}`,
                                        { preroll_enabled: next });
      setRefresher((n) => n + 1);
      showToast("success",
        `Pre-roll ${next ? "enabled" : "disabled"} for ${row.name}`);
    } catch (_) {
      showToast("error", "Toggle failed");
    } finally { setBusy(false); }
  }

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"}`;

  // Phase FUN.1.3 — per-row logo upload.
  async function uploadLogo(stationId, file) {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(`${API}/admin/stations/${stationId}/logo`, fd);
      setRefresher((n) => n + 1);
      showToast("success", "Logo uploaded");
    } catch (err) {
      const msg = err?.response?.data?.detail?.code || err.message
                              || "upload_failed";
      showToast("error", `Logo upload failed: ${msg}`);
    } finally { setBusy(false); }
  }

  // Best-available cover art for the admin preview.
  const artOf = (s) => s.art_url || s.flagship_art || s.favicon || s.logo_url;

  // Poll artwork status until it settles (complete/failed) or times out.
  async function pollArt(stationId) {
    for (let i = 0; i < 28; i += 1) {
      await new Promise((r) => window.setTimeout(r, 2500));
      try {
        const { data } = await axios.get(
          `${API}/imported-stations/${stationId}/artwork/status`);
        if (data.status === "complete" || data.status === "failed") return data;
      } catch (_) { /* transient — keep polling */ }
    }
    return null;
  }

  // Auto-generate AI cover art (station name + dial rendered in the art).
  async function genArt(s) {
    setGenIds((prev) => new Set(prev).add(s.id));
    try {
      await axios.post(`${API}/imported-stations/${s.id}/artwork/generate`, {});
      showToast("success", `Generating art for ${s.name}…`);
      const res = await pollArt(s.id);
      if (res?.status === "complete") {
        showToast("success", `Art ready for ${s.name}`);
      } else if (res?.status === "failed") {
        showToast("error", `Art failed: ${res.error || "unknown"}`);
      }
      setRefresher((n) => n + 1);
    } catch (err) {
      const d = err?.response?.data?.detail;
      const msg = (d && (d.error || d.code || d.message)) || err.message || "gen_failed";
      showToast("error", `Generate failed: ${typeof msg === "string" ? msg : JSON.stringify(msg)}`);
    } finally {
      setGenIds((prev) => { const n = new Set(prev); n.delete(s.id); return n; });
    }
  }

  // Manual cover-art upload — a true alternative to AI generation.
  async function uploadArt(stationId, file) {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(`${API}/imported-stations/${stationId}/artwork/upload`, fd);
      setRefresher((n) => n + 1);
      showToast("success", "Artwork uploaded");
    } catch (err) {
      const d = err?.response?.data?.detail;
      const msg = (d && (d.error || d.code)) || err.message || "upload_failed";
      showToast("error", `Artwork upload failed: ${msg}`);
    } finally { setBusy(false); }
  }

  const counts = items.reduce((acc, s) => {
    acc[s.playable_status || "pending"] = (acc[s.playable_status || "pending"] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className={`${light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white"} min-h-screen`}
              data-testid="admin-flagship-page">
      <div className="max-w-7xl mx-auto p-6 sm:p-8">
        <AdminPageHeader
          title="Flagship Stations"
          subtitle="Full lifecycle · pre-roll parity enforced with community stations."
          Icon={Star}
          tint="text-purple-500 fill-purple-500"
          pinLabel="Flagship Stations"
          breadcrumbs={[{ label: "Content" },
                                          { label: "Flagship Stations" }]}
          actions={
            <button onClick={() => setAddOpen(true)}
                            data-testid="admin-flagship-add-button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500 text-white text-xs font-semibold hover:bg-purple-400 transition shadow-lg shadow-purple-500/20">
              <Plus className="w-3 h-3" /> Add flagship
            </button>
          } />

        {/* Overview widget */}
        <div className={`${cardCls} mt-6 rounded-2xl p-6`}
                    data-testid="admin-flagship-overview">
          <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Fleet health</div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Total" value={items.length} light={light} />
            <Stat label="Healthy" value={counts.healthy || 0} color="emerald" light={light} />
            <Stat label="Pending" value={counts.pending || 0} color="amber" light={light} />
            <Stat label="Unreachable" value={counts.unreachable || 0} color="red" light={light} />
          </div>
          <div className="mt-4 flex gap-2 flex-wrap">
            <button onClick={runHealthCheck} disabled={busy}
                            data-testid="admin-flagship-run-healthcheck"
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500 text-white text-sm font-semibold hover:bg-purple-400 disabled:opacity-50 transition">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Run health check
            </button>
            <button onClick={reseed} disabled={busy}
                            data-testid="admin-flagship-reseed"
                            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition ${
                                light ? "border border-slate-300 text-slate-700 hover:bg-slate-100"
                                              : "border border-slate-700 text-slate-300 hover:bg-slate-800"
                            } disabled:opacity-50`}>
              <RefreshCw className="w-4 h-4" /> Re-seed manifest
            </button>
            <button onClick={healArt} disabled={busy}
                            data-testid="admin-flagship-heal-art"
                            title="Regenerate any flagship cover whose art is missing or broken (saved durably)"
                            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition ${
                                light ? "border border-purple-300 text-purple-700 hover:bg-purple-50"
                                              : "border border-purple-700 text-purple-300 hover:bg-purple-500/10"
                            } disabled:opacity-50`}>
              <Sparkles className="w-4 h-4" /> Heal artwork
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <Loader2 className="w-6 h-6 animate-spin text-amber-500 mx-auto mt-8" />
        ) : (
          <div className={`${cardCls} mt-6 rounded-2xl overflow-hidden`}
                      data-testid="admin-flagship-table">
            <div className={`hidden md:grid grid-cols-[1fr,80px,96px,96px,76px,244px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                  light ? "border-b border-slate-200 text-slate-500 bg-slate-50" :
                                                "border-b border-slate-800 text-slate-500 bg-slate-950"
                              }`}>
              <div>Station</div><div>Priority</div><div>Categories</div><div>Health</div><div>Pre-roll</div><div>Artwork · Actions</div>
            </div>
            {items.map((s) => {
              const slug = s.flagship_slug || s.id;
              const prerollOn = s.preroll_enabled !== false;
              return (
                <div key={s.id} className={`grid md:grid-cols-[1fr,80px,96px,96px,76px,244px] gap-3 px-5 py-4 items-center ${
                                          light ? "border-b border-slate-100" : "border-b border-slate-800"
                                      }`}
                            data-testid={`admin-flagship-row-${slug}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <img src={artOf(s)} alt=""
                              onError={(e) => { if (s.favicon && e.currentTarget.src !== s.favicon) e.currentTarget.src = s.favicon; }}
                              data-testid={`admin-flagship-${slug}-logo-preview`}
                              className="w-10 h-10 rounded-lg object-cover flex-shrink-0 bg-slate-800/40" />
                    <div className="min-w-0">
                      <div className="font-semibold truncate">{s.name}</div>
                      <div className={`text-[10px] ${light ? "text-slate-500" : "text-slate-500"} truncate`}>
                        {s.frequency} · {s.country} · <span className="font-mono">{s.flagship_region || "—"}</span>
                        {s.needs_stream_review && (
                          <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-500 font-semibold uppercase text-[8px]"
                                        data-testid={`admin-flagship-${slug}-needs-review-badge`}>
                            Needs review
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm font-mono">{s.flagship_priority}</div>
                  <div className={`text-[10px] ${light ? "text-slate-500" : "text-slate-500"} truncate`}>
                    {(s.flagship_categories || []).slice(0, 3).join(" · ")}
                  </div>
                  <div className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                                              STATUS_STYLES[s.playable_status] || STATUS_STYLES.pending
                                          }`}
                            data-testid={`admin-flagship-health-${slug}`}>
                    {s.playable_status || "pending"}
                  </div>
                  <div>
                    <PrerollToggle enabled={prerollOn} slug={slug}
                                                  onClick={() => togglePreroll(s)}
                                                  disabled={busy} light={light} />
                  </div>
                  <div className="text-right flex items-center justify-end gap-1">
                    <GenArtButton slug={slug}
                                              generating={genIds.has(s.id)}
                                              onClick={() => genArt(s)}
                                              disabled={busy} light={light} />
                    <UploadArtButton stationId={s.id} slug={slug}
                                                        onUpload={uploadArt}
                                                        disabled={busy || genIds.has(s.id)} light={light} />
                    <UploadLogoButton stationId={s.id} slug={slug}
                                                            onUpload={uploadLogo} disabled={busy} light={light} />
                    <a href={s.homepage || s.url_resolved} target="_blank" rel="noreferrer"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800/60"}`}
                          title="Homepage"
                          data-testid={`admin-flagship-${slug}-homepage-link`}>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <button onClick={() => setEditRow(s)} disabled={busy}
                                    data-testid={`admin-flagship-edit-button-${slug}`}
                                    className={`p-1.5 rounded-md ${light ? "text-slate-700 hover:bg-slate-100" : "text-slate-300 hover:bg-slate-800/60"}`}
                                    title="Edit">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setDeleteRow(s)} disabled={busy}
                                    data-testid={`admin-flagship-delete-button-${slug}`}
                                    className="p-1.5 rounded-md text-red-400 hover:bg-red-500/10"
                                    title="Delete">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="admin-flagship-toast">
          <div className={`${toast.kind === "error"
                                                  ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                                  : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>
            {toast.message}
          </div>
        </div>
      )}

      {addOpen && (
        <FlagshipFormModal
          mode="create"
          light={light}
          onClose={() => setAddOpen(false)}
          onSuccess={(msg) => { setRefresher((n) => n + 1); showToast("success", msg); }}
          onError={(msg) => showToast("error", msg)}
        />
      )}
      {editRow && (
        <FlagshipFormModal
          mode="edit"
          initial={editRow}
          light={light}
          onClose={() => setEditRow(null)}
          onSuccess={(msg) => { setRefresher((n) => n + 1); showToast("success", msg); }}
          onError={(msg) => showToast("error", msg)}
        />
      )}
      {deleteRow && (
        <FlagshipDeleteModal
          row={deleteRow}
          light={light}
          onClose={() => setDeleteRow(null)}
          onSuccess={(msg) => { setRefresher((n) => n + 1); showToast("success", msg); }}
          onError={(msg) => showToast("error", msg)}
        />
      )}
    </div>
  );
}

function Stat({ label, value, color, light }) {
  const cMap = {
    emerald: "text-emerald-500",
    amber:      "text-amber-500",
    red:          "text-red-400",
  };
  return (
    <div>
      <div className={`text-[10px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`mt-1 text-2xl font-bold ${color ? cMap[color] : ""}`}>{value}</div>
    </div>
  );
}

function PrerollToggle({ enabled, slug, onClick, disabled, light }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
                    data-testid={`admin-flagship-preroll-toggle-${slug}`}
                    role="switch"
                    aria-checked={enabled ? "true" : "false"}
                    aria-pressed={enabled}
                    title={enabled ? "Pre-roll enabled — click to disable"
                                                          : "Pre-roll disabled — click to enable"}
                    className={`relative inline-flex items-center h-5 w-9 rounded-full transition
                                              ${enabled ? "bg-emerald-500" : (light ? "bg-slate-300" : "bg-slate-700")}
                                              disabled:opacity-50`}>
      <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition transform
                                              ${enabled ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}

// Phase FUN.1.3 — per-row logo upload trigger.
function UploadLogoButton({ stationId, slug, onUpload, disabled, light }) {
  const inputRef = useRef(null);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/webp,image/jpeg,image/svg+xml,.png,.webp,.jpg,.jpeg,.svg"
        className="hidden"
        data-testid={`admin-flagship-${slug}-upload-input`}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(stationId, f);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        data-testid={`admin-flagship-${slug}-upload-logo`}
        title="Upload logo (small station icon)"
        className={`p-1.5 rounded-md ${light ? "text-slate-600 hover:bg-slate-100"
                                                                    : "text-slate-300 hover:bg-slate-800/60"} disabled:opacity-40`}
      >
        <Upload className="w-3.5 h-3.5" />
      </button>
    </>
  );
}

// AI cover-art generation — bakes station name + dial into the artwork.
function GenArtButton({ slug, generating, onClick, disabled, light }) {
  return (
    <button
      type="button"
      disabled={disabled || generating}
      onClick={onClick}
      data-testid={`admin-flagship-${slug}-gen-art`}
      title="Generate AI cover art (station name + dial baked in)"
      className={`p-1.5 rounded-md ${light ? "text-purple-600 hover:bg-purple-50"
                                                                  : "text-purple-300 hover:bg-purple-500/10"} disabled:opacity-40`}
    >
      {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <Sparkles className="w-3.5 h-3.5" />}
    </button>
  );
}

// Manual cover-art upload — a true alternative to AI generation.
function UploadArtButton({ stationId, slug, onUpload, disabled, light }) {
  const inputRef = useRef(null);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/webp,image/jpeg,.png,.webp,.jpg,.jpeg"
        className="hidden"
        data-testid={`admin-flagship-${slug}-art-input`}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(stationId, f);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        data-testid={`admin-flagship-${slug}-upload-art`}
        title="Upload cover art manually (skip AI)"
        className={`p-1.5 rounded-md ${light ? "text-slate-600 hover:bg-slate-100"
                                                                    : "text-slate-300 hover:bg-slate-800/60"} disabled:opacity-40`}
      >
        <ImagePlus className="w-3.5 h-3.5" />
      </button>
    </>
  );
}

// ═════════════════════════════════════════════════════════════════
// FlagshipFormModal — Add or Edit modal.
// ═════════════════════════════════════════════════════════════════
function FlagshipFormModal({ mode, initial, light, onClose, onSuccess, onError }) {
  const isEdit = mode === "edit";
  const [form, setForm] = useState(() => {
    if (!isEdit) return { ...EMPTY_FORM };
    return {
      name: initial.name || "",
      homepage: initial.homepage || "",
      frequency: initial.frequency || "",
      stream_url: initial.url_resolved || initial.url || "",
      logo_url: initial.logo_url || "",
      country: initial.country || "",
      country_code: initial.country_code || "",
      city: initial.city || "",
      flagship_region: initial.flagship_region || "",
      flagship_priority: initial.flagship_priority || 150,
      flagship_categories_csv: (initial.flagship_categories || []).join(","),
      languages_csv: (initial.language_codes || []).join(","),
      description: initial.description || "",
      preroll_enabled: initial.preroll_enabled !== false,
    };
  });
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function validateStream() {
    if (!form.stream_url) return;
    setProbing(true);
    setProbeResult(null);
    try {
      const { data } = await axios.post(
        `${API}/admin/stations/flagship/validate-stream`,
        { stream_url: form.stream_url });
      setProbeResult(data);
    } catch (_) {
      setProbeResult({ ok: false, status_code: 0, error: "network_error" });
    } finally { setProbing(false); }
  }

  async function submit() {
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        homepage: form.homepage || undefined,
        frequency: form.frequency || undefined,
        stream_url: form.stream_url,
        logo_url: form.logo_url || undefined,
        country: form.country || undefined,
        country_code: form.country_code || undefined,
        city: form.city || undefined,
        flagship_region: form.flagship_region || undefined,
        flagship_priority: Number(form.flagship_priority) || 150,
        flagship_categories: (form.flagship_categories_csv || "")
                                            .split(",").map((x) => x.trim()).filter(Boolean),
        languages: (form.languages_csv || "")
                                            .split(",").map((x) => x.trim()).filter(Boolean),
        description: form.description || undefined,
        preroll_enabled: !!form.preroll_enabled,
      };
      let resp;
      if (isEdit) {
        // Don't re-send stream_url if unchanged, to avoid needless re-probe.
        const originalStream = initial.url_resolved || initial.url || "";
        if (payload.stream_url === originalStream) delete payload.stream_url;
        resp = await axios.patch(
          `${API}/admin/stations/flagship/${initial.id}`, payload);
      } else {
        if (!payload.name || !payload.stream_url) {
          onError("Name and stream URL are required.");
          setSaving(false);
          return;
        }
        resp = await axios.post(`${API}/admin/stations/flagship`, payload);
      }
      const warnings = resp?.data?.warnings || [];
      const warnMsg = warnings.length
        ? ` (warnings: ${warnings.join(", ")})` : "";
      onSuccess(`${isEdit ? "Updated" : "Created"} “${form.name}”${warnMsg}`);
      onClose();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = (detail && (detail.code || detail.message))
                              || err?.response?.data?.detail
                              || err?.message
                              || "save_failed";
      onError(`Save failed: ${typeof msg === "string" ? msg : JSON.stringify(msg)}`);
    } finally { setSaving(false); }
  }

  const bg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";
  const inputCls = `w-full px-3 py-2 rounded-lg border text-sm
                                        ${light ? "bg-white border-slate-300 text-slate-900 placeholder-slate-400"
                                                        : "bg-slate-950 border-slate-800 text-white placeholder-slate-500"}
                                        focus:outline-none focus:ring-2 focus:ring-purple-500`;
  const labelCls = `text-xs uppercase tracking-wider font-mono ${light ? "text-slate-500" : "text-slate-400"} mb-1 block`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="admin-flagship-form-modal"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${bg} border ${border} rounded-2xl shadow-2xl max-w-2xl w-full my-8`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div className="flex items-center gap-2">
            <Radio className={`w-5 h-5 ${light ? "text-purple-600" : "text-purple-400"}`} />
            <h2 className="text-lg font-bold">{isEdit ? "Edit flagship station" : "Add flagship station"}</h2>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}
                          data-testid="admin-flagship-form-close">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className={labelCls}>Name *</label>
            <input value={form.name} onChange={(e) => set("name", e.target.value)}
                          className={inputCls} placeholder="Luv 107.1 UAE"
                          data-testid="admin-flagship-form-name" />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>Stream URL *</label>
            <div className="flex gap-2">
              <input value={form.stream_url}
                            onChange={(e) => set("stream_url", e.target.value)}
                            className={inputCls}
                            placeholder="https://funasia.streamguys1.com/live-1"
                            data-testid="admin-flagship-form-stream-url" />
              <button type="button" onClick={validateStream} disabled={probing || !form.stream_url}
                              data-testid="admin-flagship-form-validate-stream"
                              className={`px-3 py-2 rounded-lg text-xs font-semibold whitespace-nowrap
                                                    ${light ? "bg-slate-100 hover:bg-slate-200 text-slate-700"
                                                                    : "bg-slate-800 hover:bg-slate-700 text-slate-100"}
                                                    disabled:opacity-40`}>
                {probing ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : "Validate"}
              </button>
            </div>
            {probeResult && (
              <div className={`mt-1.5 text-xs inline-flex items-center gap-1 font-mono
                                                    ${probeResult.ok ? "text-emerald-500" : "text-amber-500"}`}
                          data-testid="admin-flagship-form-probe-result">
                {probeResult.ok
                  ? <><CheckCircle2 className="w-3.5 h-3.5" /> {probeResult.status_code} · OK</>
                  : <><ShieldAlert className="w-3.5 h-3.5" /> {probeResult.error || `status ${probeResult.status_code}`} · save is still allowed (needs_stream_review will be set)</>}
              </div>
            )}
          </div>
          <div>
            <label className={labelCls}>Homepage</label>
            <input value={form.homepage} onChange={(e) => set("homepage", e.target.value)}
                          className={inputCls} placeholder="https://luv1071.com"
                          data-testid="admin-flagship-form-homepage" />
          </div>
          <div>
            <label className={labelCls}>Frequency</label>
            <input value={form.frequency} onChange={(e) => set("frequency", e.target.value)}
                          className={inputCls} placeholder="107.1 FM Dubai"
                          data-testid="admin-flagship-form-frequency" />
          </div>
          <div>
            <label className={labelCls}>Country</label>
            <input value={form.country} onChange={(e) => set("country", e.target.value)}
                          className={inputCls} placeholder="United Arab Emirates"
                          data-testid="admin-flagship-form-country" />
          </div>
          <div>
            <label className={labelCls}>Country code (ISO-2)</label>
            <input value={form.country_code}
                          onChange={(e) => set("country_code", e.target.value.toUpperCase())}
                          className={inputCls} placeholder="AE" maxLength={2}
                          data-testid="admin-flagship-form-country-code" />
          </div>
          <div>
            <label className={labelCls}>City</label>
            <input value={form.city} onChange={(e) => set("city", e.target.value)}
                          className={inputCls} placeholder="Dubai"
                          data-testid="admin-flagship-form-city" />
          </div>
          <div>
            <label className={labelCls}>Region (AE · US · custom)</label>
            <input value={form.flagship_region}
                          onChange={(e) => set("flagship_region", e.target.value.toUpperCase())}
                          className={inputCls} placeholder="AE"
                          data-testid="admin-flagship-form-region" />
          </div>
          <div>
            <label className={labelCls}>Priority (higher = first)</label>
            <input type="number" value={form.flagship_priority}
                          onChange={(e) => set("flagship_priority", e.target.value)}
                          className={inputCls} placeholder="150"
                          data-testid="admin-flagship-form-priority" />
          </div>
          <div>
            <label className={labelCls}>Logo URL</label>
            <input value={form.logo_url} onChange={(e) => set("logo_url", e.target.value)}
                          className={inputCls}
                          placeholder="Paste URL or upload after saving"
                          data-testid="admin-flagship-form-logo-url" />
            {form.logo_url && (
              <img src={form.logo_url} alt="" className="mt-2 w-14 h-14 rounded-lg object-cover bg-slate-800/40"
                        data-testid="admin-flagship-form-logo-preview" />
            )}
            {!isEdit && !form.logo_url && (
              <div className={`mt-1.5 text-[10px] ${light ? "text-slate-500" : "text-slate-500"}`}>
                Leave empty — a placeholder is generated. Upload the real logo from the row after save.
              </div>
            )}
          </div>
          <div className="col-span-2">
            <label className={labelCls}>Categories (comma-separated)</label>
            <input value={form.flagship_categories_csv}
                          onChange={(e) => set("flagship_categories_csv", e.target.value)}
                          className={inputCls} placeholder="home, music, pop, top_40"
                          data-testid="admin-flagship-form-categories" />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>Languages (comma-separated)</label>
            <input value={form.languages_csv}
                          onChange={(e) => set("languages_csv", e.target.value)}
                          className={inputCls} placeholder="english, hindi"
                          data-testid="admin-flagship-form-languages" />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>Description</label>
            <textarea value={form.description}
                                onChange={(e) => set("description", e.target.value)}
                                rows={2} className={inputCls}
                                placeholder="Dubai's #1 hit music station."
                                data-testid="admin-flagship-form-description" />
          </div>

          <div className={`col-span-2 mt-1 flex items-center gap-3 rounded-lg p-3
                                        ${light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950 border border-slate-800"}`}>
            <PrerollToggle enabled={!!form.preroll_enabled}
                                            slug="form" light={light}
                                            onClick={() => set("preroll_enabled", !form.preroll_enabled)} />
            <div className="min-w-0">
              <div className="text-sm font-semibold">Pre-roll ads {form.preroll_enabled ? "enabled" : "disabled"}</div>
              <div className={`text-[10px] ${light ? "text-slate-500" : "text-slate-400"}`}>
                When ON, this flagship plays pre-roll ads on tune-in — same as every community station.
              </div>
            </div>
          </div>
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-end gap-2`}>
          <button onClick={onClose}
                          data-testid="admin-flagship-form-cancel"
                          className={`px-4 py-2 rounded-full text-sm font-semibold
                                                    ${light ? "text-slate-700 hover:bg-slate-100"
                                                                    : "text-slate-300 hover:bg-slate-800"}`}>
            Cancel
          </button>
          <button onClick={submit} disabled={saving || !form.name || !form.stream_url}
                          data-testid="admin-flagship-form-submit"
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500 text-white text-sm font-semibold hover:bg-purple-400 disabled:opacity-50 transition">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            {isEdit ? "Save changes" : "Create flagship"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════
// FlagshipDeleteModal — soft or hard delete with typed confirmation.
// ═════════════════════════════════════════════════════════════════
function FlagshipDeleteModal({ row, light, onClose, onSuccess, onError }) {
  const [hard, setHard] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const slug = row.flagship_slug || row.id;
  const requiredType = row.name;
  const confirmMatches = !hard || (typed.trim() === requiredType);

  async function submit() {
    if (!confirmMatches) return;
    setBusy(true);
    try {
      const url = hard
        ? `${API}/admin/stations/flagship/${row.id}?hard=true`
        : `${API}/admin/stations/flagship/${row.id}`;
      await axios.delete(url);
      onSuccess(`${hard ? "Permanently removed" : "Retired"} “${row.name}”`);
      onClose();
    } catch (err) {
      const msg = err?.response?.data?.detail?.code || err?.message || "delete_failed";
      onError(`Delete failed: ${msg}`);
    } finally { setBusy(false); }
  }

  const bg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";
  const inputCls = `w-full px-3 py-2 rounded-lg border text-sm
                                        ${light ? "bg-white border-slate-300 text-slate-900 placeholder-slate-400"
                                                        : "bg-slate-950 border-slate-800 text-white placeholder-slate-500"}
                                        focus:outline-none focus:ring-2 focus:ring-red-500`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
              data-testid="admin-flagship-delete-modal"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${bg} border ${border} rounded-2xl shadow-2xl max-w-md w-full`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center gap-2`}>
          <Trash2 className="w-5 h-5 text-red-500" />
          <h2 className="text-lg font-bold">Delete flagship</h2>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3">
            <img src={row.favicon} alt="" className="w-12 h-12 rounded-lg object-cover bg-slate-800/40" />
            <div>
              <div className="font-semibold">{row.name}</div>
              <div className={`text-xs ${light ? "text-slate-500" : "text-slate-400"} font-mono`}>{slug}</div>
            </div>
          </div>

          <div className={`space-y-2 rounded-lg p-3 ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800"}`}>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="radio" checked={!hard} onChange={() => setHard(false)}
                            className="mt-1 accent-purple-500"
                            data-testid="admin-flagship-delete-soft-radio" />
              <div>
                <div className="text-sm font-semibold">Retire (soft delete)</div>
                <div className={`text-xs ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Row remains for auditability. Sets <code>active=false</code> and <code>is_flagship=false</code>.
                  Reversible from the DB.
                </div>
              </div>
            </label>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="radio" checked={hard} onChange={() => setHard(true)}
                            className="mt-1 accent-red-500"
                            data-testid="admin-flagship-delete-hard-radio" />
              <div>
                <div className="text-sm font-semibold text-red-400">Permanently remove (hard delete)</div>
                <div className={`text-xs ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Erases the row + logo files. Irreversible.
                </div>
              </div>
            </label>
          </div>

          {hard && (
            <div>
              <label className={`text-xs uppercase tracking-wider font-mono block mb-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                Type <span className="font-bold text-red-400">{requiredType}</span> to confirm
              </label>
              <input value={typed} onChange={(e) => setTyped(e.target.value)}
                            className={inputCls} placeholder={requiredType}
                            data-testid="admin-flagship-delete-confirm-input" autoFocus />
            </div>
          )}
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-end gap-2`}>
          <button onClick={onClose}
                          data-testid="admin-flagship-delete-cancel"
                          className={`px-4 py-2 rounded-full text-sm font-semibold
                                                    ${light ? "text-slate-700 hover:bg-slate-100"
                                                                    : "text-slate-300 hover:bg-slate-800"}`}>
            Cancel
          </button>
          <button onClick={submit}
                          disabled={busy || !confirmMatches}
                          data-testid="admin-flagship-delete-confirm"
                          className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold text-white disabled:opacity-50 transition
                                                    ${hard ? "bg-red-500 hover:bg-red-400"
                                                                    : "bg-amber-500 hover:bg-amber-400"}`}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                          : hard ? <Trash2 className="w-4 h-4" />
                                          : <ChevronDown className="w-4 h-4" />}
            {hard ? "Permanently delete" : "Retire station"}
          </button>
        </div>
      </div>
    </div>
  );
}
