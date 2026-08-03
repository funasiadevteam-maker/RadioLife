// Phase R — Admin /admin/news page (legacy dark only).
// Tabs: Headlines (add, bulk, promote, delete) / Channels (add, list) / Bulletins (generate, publish).
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Loader2, Plus, ArrowLeft, Zap, ListPlus, Archive,
                 Radio, Play, ShieldCheck, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TABS = [
  { key: "headlines", label: "Headlines" },
  { key: "channels",  label: "Channels" },
  { key: "bulletins", label: "Bulletins" },
];

export default function AdminNews() {
  const [tab, setTab] = useState("headlines");

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-news-page">
      <div className="max-w-7xl xl:max-w-[1600px] mx-auto p-6 sm:p-8">
        <AdminPageHeader
          title="News Admin"
          subtitle="Curate headlines, channels, and TTS bulletins across regions."
          Icon={ShieldCheck}
          tint="text-red-500"
          pinLabel="News Radio"
          breadcrumbs={[{ label: "Content" },
                                          { label: "News Radio" }]} />

        <div className="mt-5 mb-6 border-b border-slate-800 flex gap-1">
          {TABS.map((t) => (
            <button key={t.key}
                            data-testid={`admin-news-tab-${t.key}`}
                            onClick={() => setTab(t.key)}
                            className={`px-4 py-2 text-sm font-bold border-b-2 -mb-px transition
                                        focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 ${
                              tab === t.key
                                ? "border-red-500 text-red-400"
                                : "border-transparent text-slate-400 hover:text-white"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "headlines"  && <HeadlinesTab />}
        {tab === "channels"   && <ChannelsTab />}
        {tab === "bulletins" && <BulletinsTab />}
      </div>
    </div>
  );
}

// ── Headlines tab ──────────────────────────────────────────
function HeadlinesTab() {
  const [rows, setRows]     = useState([]);
  const [busy, setBusy]     = useState(true);
  const [err, setErr]       = useState(null);
  const [region, setRegion] = useState("");
  const [status, setStatus] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [showBulk, setShowBulk] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const q = new URLSearchParams({ limit: "100" });
      if (region) q.set("region_code", region);
      if (status) q.set("status", status);
      const { data } = await axios.get(
        `${API}/admin/news/headlines?${q}`, { withCredentials: true });
      setRows(data?.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  }, [region, status]);

  useEffect(() => { load(); }, [load]);

  const promote = async (id) => {
    if (!window.confirm("Promote this headline to breaking news? This will notify region-matching listeners.")) return;
    try {
      await axios.post(
        `${API}/admin/news/headlines/${id}/promote-breaking`,
        {}, { withCredentials: true });
      load();
    } catch (e) {
      alert(e?.response?.data?.detail?.code || e.message);
    }
  };

  const del = async (id) => {
    if (!window.confirm("Archive this headline?")) return;
    try {
      await axios.delete(
        `${API}/admin/news/headlines/${id}`, { withCredentials: true });
      load();
    } catch (e) {
      alert(e?.response?.data?.detail?.code || e.message);
    }
  };

  return (
    <div data-testid="admin-news-headlines">
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <input type="text" value={region}
                    onChange={(e) => setRegion(e.target.value.toUpperCase())}
                    placeholder="Region code"
                    data-testid="admin-news-hl-region"
                    className="px-3 py-1.5 rounded-full text-xs font-mono bg-slate-900
                                    border border-slate-800 w-40 focus:outline-none
                                    focus-visible:ring-2 focus-visible:ring-red-500" />
        <select value={status}
                        onChange={(e) => setStatus(e.target.value)}
                        data-testid="admin-news-hl-status"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-900 border border-slate-800
                                      focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
          <option value="">All statuses</option>
          <option value="live">Live</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>
        <button onClick={() => setShowAdd(true)}
                        data-testid="admin-news-hl-add-btn"
                        className="ml-auto px-4 py-1.5 rounded-full bg-red-500 text-white
                                      text-xs font-bold inline-flex items-center gap-2 hover:bg-red-400">
          <Plus className="w-3 h-3" /> Add headline
        </button>
        <button onClick={() => setShowBulk(true)}
                        data-testid="admin-news-hl-bulk-btn"
                        className="px-4 py-1.5 rounded-full bg-slate-800 text-slate-200
                                      text-xs font-bold inline-flex items-center gap-2 hover:bg-slate-700">
          <ListPlus className="w-3 h-3" /> Bulk paste
        </button>
      </div>

      {showAdd && <AddHeadlineForm onClose={() => setShowAdd(false)} onSaved={load} />}
      {showBulk && <BulkHeadlineForm onClose={() => setShowBulk(false)} onSaved={load} />}

      {busy ? (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : err ? (
        <div className="text-sm text-red-400">Failed: {String(err)}</div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 p-8 text-center text-sm text-slate-500">
          No headlines match the filter. Click &quot;Add headline&quot; or &quot;Bulk paste&quot;.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-xs" data-testid="admin-news-hl-table">
            <thead className="bg-slate-900">
              <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                <th className="text-left px-3 py-2">Headline</th>
                <th className="text-left px-3 py-2">Category</th>
                <th className="text-left px-3 py-2">Region</th>
                <th className="text-left px-3 py-2">Priority</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Summary</th>
                <th className="text-right px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.id} className="border-t border-slate-800 hover:bg-slate-900/40"
                        data-testid={`admin-news-hl-row-${h.id}`}>
                  <td className="px-3 py-2 max-w-md">
                    <div className="text-sm font-medium truncate">{h.headline_text}</div>
                    {h.source_url && (
                      <a href={h.source_url} target="_blank" rel="noreferrer"
                          className="text-[10px] font-mono text-slate-500 hover:text-red-400 inline-flex items-center gap-1">
                        <ExternalLink className="w-3 h-3" /> {h.source_name || "source"}
                      </a>
                    )}
                  </td>
                  <td className="px-3 py-2">{h.category}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{h.region_code || "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{h.priority}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-mono uppercase tracking-widest ${
                        h.is_breaking ? "text-red-400 font-bold"
                                            : h.status === "live" ? "text-emerald-400"
                                            : h.status === "archived" ? "text-slate-500"
                                            : "text-amber-400"}`}>
                      {h.is_breaking ? "BREAKING" : h.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-400 max-w-xs truncate">
                    {h.curated_by_llm && (
                      <span className="text-[9px] font-mono text-fuchsia-400 mr-1">AI</span>
                    )}
                    {h.summary_text || "—"}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {!h.is_breaking && h.status === "live" && (
                      <button onClick={() => promote(h.id)}
                                      data-testid={`admin-news-hl-promote-${h.id}`}
                                      className="text-xs px-2 py-1 rounded-full bg-red-500 text-white
                                                        hover:bg-red-400 inline-flex items-center gap-1">
                        <Zap className="w-3 h-3" /> Promote
                      </button>
                    )}
                    {h.status !== "archived" && (
                      <button onClick={() => del(h.id)}
                                      data-testid={`admin-news-hl-delete-${h.id}`}
                                      className="ml-1 text-xs px-2 py-1 rounded-full bg-slate-800 text-slate-300
                                                        hover:bg-slate-700 inline-flex items-center gap-1">
                        <Archive className="w-3 h-3" /> Archive
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddHeadlineForm({ onClose, onSaved }) {
  const [f, setF] = useState({
    headline_text: "", summary_text: "", category: "features",
    region_code: "", source_name: "", source_url: "", priority: 5,
    auto_summarize: true,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    if (!f.headline_text.trim()) return setErr("Headline text is required.");
    setBusy(true);
    setErr(null);
    try {
      await axios.post(`${API}/admin/news/headlines`, f,
                                    { withCredentials: true });
      onSaved && onSaved();
      onClose();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 rounded-2xl border border-red-500/40 bg-red-500/5 p-4 space-y-3"
              data-testid="admin-news-hl-add-form">
      <div className="font-bold text-sm">Add a headline</div>
      <textarea rows={2} value={f.headline_text}
                          onChange={(e) => setF({ ...f, headline_text: e.target.value })}
                          placeholder="Headline text (max 200 chars)"
                          maxLength={200}
                          data-testid="admin-news-hl-add-headline"
                          className="w-full px-3 py-2 rounded-lg text-sm bg-slate-950 border border-slate-800
                                            focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500" />
      <div className="grid grid-cols-2 gap-2">
        <select value={f.category}
                        onChange={(e) => setF({ ...f, category: e.target.value })}
                        data-testid="admin-news-hl-add-category"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-950 border border-slate-800">
          {["breaking","local","politics","business","sports","weather","traffic","features","world","tech","entertainment"]
            .map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input value={f.region_code}
                    onChange={(e) => setF({ ...f, region_code: e.target.value.toUpperCase() })}
                    placeholder="Region code"
                    data-testid="admin-news-hl-add-region"
                    className="px-3 py-1.5 rounded-full text-xs font-mono bg-slate-950 border border-slate-800" />
        <input value={f.source_name}
                    onChange={(e) => setF({ ...f, source_name: e.target.value })}
                    placeholder="Source name"
                    data-testid="admin-news-hl-add-source-name"
                    className="px-3 py-1.5 rounded-full text-xs bg-slate-950 border border-slate-800" />
        <input value={f.source_url}
                    onChange={(e) => setF({ ...f, source_url: e.target.value })}
                    placeholder="Source URL"
                    data-testid="admin-news-hl-add-source-url"
                    className="px-3 py-1.5 rounded-full text-xs bg-slate-950 border border-slate-800" />
        <input type="number" min="1" max="10" value={f.priority}
                    onChange={(e) => setF({ ...f, priority: parseInt(e.target.value || "5", 10) })}
                    placeholder="Priority (1-10)"
                    data-testid="admin-news-hl-add-priority"
                    className="px-3 py-1.5 rounded-full text-xs bg-slate-950 border border-slate-800" />
        <label className="inline-flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={f.auto_summarize}
                          data-testid="admin-news-hl-add-autosum"
                          onChange={(e) => setF({ ...f, auto_summarize: e.target.checked })} />
          Auto-summarize via LLM
        </label>
      </div>
      <textarea rows={2} value={f.summary_text}
                          onChange={(e) => setF({ ...f, summary_text: e.target.value })}
                          placeholder="Summary text (optional — leave blank for AI to fill)"
                          maxLength={500}
                          data-testid="admin-news-hl-add-summary"
                          className="w-full px-3 py-2 rounded-lg text-sm bg-slate-950 border border-slate-800
                                            focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500" />
      {err && <div className="text-xs text-red-400">Error: {String(err)}</div>}
      <div className="flex gap-2 justify-end">
        <button onClick={onClose}
                        data-testid="admin-news-hl-add-cancel"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-800 hover:bg-slate-700">
          Cancel
        </button>
        <button onClick={submit} disabled={busy}
                        data-testid="admin-news-hl-add-submit"
                        className="px-4 py-1.5 rounded-full bg-red-500 text-white text-xs font-bold
                                      inline-flex items-center gap-1 hover:bg-red-400 disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Create
        </button>
      </div>
    </div>
  );
}

function BulkHeadlineForm({ onClose, onSaved }) {
  const [text, setText] = useState("");
  const [region, setRegion] = useState("");
  const [category, setCategory] = useState("features");
  const [autoSum, setAutoSum] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);

  const submit = async () => {
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return setErr("Paste at least one line.");
    setBusy(true);
    setErr(null);
    try {
      const rows = lines.map((line) => {
        const [headline, url] = line.split("\t");
        return {
          headline_text: (headline || "").trim(),
          source_url:    (url || "").trim() || undefined,
          category,
          region_code:   region || undefined,
        };
      });
      const { data } = await axios.post(
        `${API}/admin/news/headlines/bulk`,
        { rows, auto_summarize: autoSum },
        { withCredentials: true });
      setResult(data);
      onSaved && onSaved();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 rounded-2xl border border-red-500/40 bg-red-500/5 p-4 space-y-3"
              data-testid="admin-news-hl-bulk-form">
      <div className="font-bold text-sm">Bulk paste</div>
      <div className="text-xs text-slate-400">
        One headline per line.  Optionally add a source URL after a TAB.
      </div>
      <textarea rows={6} value={text}
                          onChange={(e) => setText(e.target.value)}
                          placeholder="Emirates adds new route&#9;https://example.com/story-a\nUAE stocks close up 1.2%\nTraffic slow on E11"
                          data-testid="admin-news-hl-bulk-text"
                          className="w-full px-3 py-2 rounded-lg text-xs font-mono bg-slate-950 border border-slate-800
                                          focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500" />
      <div className="grid grid-cols-2 gap-2">
        <input value={region}
                    onChange={(e) => setRegion(e.target.value.toUpperCase())}
                    placeholder="Region code (applied to all)"
                    data-testid="admin-news-hl-bulk-region"
                    className="px-3 py-1.5 rounded-full text-xs font-mono bg-slate-950 border border-slate-800" />
        <select value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        data-testid="admin-news-hl-bulk-category"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-950 border border-slate-800">
          {["breaking","local","politics","business","sports","weather","traffic","features","world","tech","entertainment"]
            .map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <label className="inline-flex items-center gap-2 text-xs text-slate-400">
        <input type="checkbox" checked={autoSum}
                        data-testid="admin-news-hl-bulk-autosum"
                        onChange={(e) => setAutoSum(e.target.checked)} />
        Auto-summarize each headline via LLM
      </label>
      {err && <div className="text-xs text-red-400">Error: {String(err)}</div>}
      {result && (
        <div className="text-xs" data-testid="admin-news-hl-bulk-result">
          <span className="text-emerald-400 font-bold">Created:</span> {result.created_count}
          {" · "}
          <span className={result.error_count ? "text-red-400" : "text-slate-500"}>
            Errors: {result.error_count}
          </span>
        </div>
      )}
      <div className="flex gap-2 justify-end">
        <button onClick={onClose}
                        data-testid="admin-news-hl-bulk-close"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-800 hover:bg-slate-700">
          Close
        </button>
        <button onClick={submit} disabled={busy}
                        data-testid="admin-news-hl-bulk-submit"
                        className="px-4 py-1.5 rounded-full bg-red-500 text-white text-xs font-bold
                                      inline-flex items-center gap-1 hover:bg-red-400 disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <ListPlus className="w-3 h-3" />}
          Ingest
        </button>
      </div>
    </div>
  );
}

// ── Channels tab ────────────────────────────────────────────
function ChannelsTab() {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(true);
  const [err, setErr]   = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const { data } = await axios.get(
        `${API}/admin/news/channels`, { withCredentials: true });
      setRows(data?.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="admin-news-channels">
      <div className="flex justify-end mb-3">
        <button onClick={() => setShowAdd(true)}
                        data-testid="admin-news-ch-add-btn"
                        className="px-4 py-1.5 rounded-full bg-red-500 text-white text-xs font-bold
                                      inline-flex items-center gap-2 hover:bg-red-400">
          <Plus className="w-3 h-3" /> New channel
        </button>
      </div>
      {showAdd && <AddChannelForm onClose={() => setShowAdd(false)} onSaved={load} />}
      {busy ? (
        <div className="text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin inline" /> Loading…</div>
      ) : err ? (
        <div className="text-sm text-red-400">{String(err)}</div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 p-8 text-center text-sm text-slate-500">
          No channels yet.  Create one to enable bulletin generation.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {rows.map((c) => (
            <div key={c.id}
                      data-testid={`admin-news-ch-card-${c.id}`}
                      className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Radio className="w-4 h-4 text-red-400" />
                <div className="text-sm font-bold truncate">{c.name}</div>
                <span className={`ml-auto text-[10px] font-mono uppercase tracking-widest ${
                    c.status === "active" && c.live ? "text-emerald-400" : "text-slate-500"}`}>
                  {c.status === "active" && c.live ? "LIVE" : "OFF"}
                </span>
              </div>
              {c.tagline && (
                <div className="text-xs text-slate-400 line-clamp-2">{c.tagline}</div>
              )}
              <div className="text-[10px] font-mono text-slate-500 mt-2">
                {c.city || c.region_code || "Global"} · {c.language} · {(c.program_schedule || []).length} slots
              </div>
              <div className="mt-2 text-[10px] font-mono text-slate-600 truncate">
                ID: {c.id}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddChannelForm({ onClose, onSaved }) {
  const [f, setF] = useState({
    name: "", region_code: "", city: "", language: "en", tagline: "",
    cover_image_url: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    if (!f.name.trim()) return setErr("Name required.");
    setBusy(true);
    setErr(null);
    try {
      await axios.post(`${API}/admin/news/channels`, f,
                                    { withCredentials: true });
      onSaved && onSaved();
      onClose();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 rounded-2xl border border-red-500/40 bg-red-500/5 p-4 space-y-3"
              data-testid="admin-news-ch-add-form">
      <div className="font-bold text-sm">New channel</div>
      <input value={f.name}
                  onChange={(e) => setF({ ...f, name: e.target.value })}
                  placeholder="Channel name"
                  data-testid="admin-news-ch-add-name"
                  className="w-full px-3 py-2 rounded-lg text-sm bg-slate-950 border border-slate-800
                                    focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500" />
      <div className="grid grid-cols-2 gap-2">
        <input value={f.region_code}
                    onChange={(e) => setF({ ...f, region_code: e.target.value.toUpperCase() })}
                    placeholder="Region code"
                    data-testid="admin-news-ch-add-region"
                    className="px-3 py-2 rounded-lg text-xs font-mono bg-slate-950 border border-slate-800" />
        <input value={f.city}
                    onChange={(e) => setF({ ...f, city: e.target.value })}
                    placeholder="City"
                    data-testid="admin-news-ch-add-city"
                    className="px-3 py-2 rounded-lg text-xs bg-slate-950 border border-slate-800" />
        <input value={f.language}
                    onChange={(e) => setF({ ...f, language: e.target.value })}
                    placeholder="Language"
                    data-testid="admin-news-ch-add-language"
                    className="px-3 py-2 rounded-lg text-xs bg-slate-950 border border-slate-800" />
        <input value={f.tagline}
                    onChange={(e) => setF({ ...f, tagline: e.target.value })}
                    placeholder="Tagline"
                    data-testid="admin-news-ch-add-tagline"
                    className="px-3 py-2 rounded-lg text-xs bg-slate-950 border border-slate-800" />
      </div>
      {err && <div className="text-xs text-red-400">{String(err)}</div>}
      <div className="flex gap-2 justify-end">
        <button onClick={onClose}
                        data-testid="admin-news-ch-add-cancel"
                        className="px-3 py-1.5 rounded-full text-xs bg-slate-800 hover:bg-slate-700">
          Cancel
        </button>
        <button onClick={submit} disabled={busy}
                        data-testid="admin-news-ch-add-submit"
                        className="px-4 py-1.5 rounded-full bg-red-500 text-white text-xs font-bold
                                      inline-flex items-center gap-1 hover:bg-red-400 disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Create
        </button>
      </div>
    </div>
  );
}

// ── Bulletins tab ────────────────────────────────────────
function BulletinsTab() {
  const [rows, setRows]       = useState([]);
  const [chans, setChans]     = useState([]);
  const [busy, setBusy]       = useState(true);
  const [err, setErr]         = useState(null);
  const [genFor, setGenFor]   = useState("");    // channel_id currently generating
  const [genErr, setGenErr]   = useState(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [b, c] = await Promise.all([
        axios.get(`${API}/admin/news/bulletins?limit=50`,
                          { withCredentials: true }),
        axios.get(`${API}/admin/news/channels`, { withCredentials: true }),
      ]);
      setRows(b.data?.items || []);
      setChans(c.data?.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async (cid) => {
    setGenFor(cid);
    setGenErr(null);
    try {
      await axios.post(
        `${API}/admin/news/channels/${cid}/bulletins/generate`,
        { top_n: 5 }, { withCredentials: true });
      load();
    } catch (e) {
      setGenErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setGenFor("");
    }
  };

  const publish = async (bid) => {
    try {
      await axios.post(
        `${API}/admin/news/bulletins/${bid}/publish`,
        {}, { withCredentials: true });
      load();
    } catch (e) {
      alert(e?.response?.data?.detail?.code || e.message);
    }
  };

  return (
    <div data-testid="admin-news-bulletins">
      {/* Generate row */}
      <div className="mb-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4"
                data-testid="admin-news-bul-generate">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">
          Generate a bulletin
        </div>
        {chans.length === 0 ? (
          <div className="text-xs text-slate-500">Create a channel first.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {chans.map((c) => (
              <button key={c.id}
                              disabled={genFor === c.id}
                              onClick={() => generate(c.id)}
                              data-testid={`admin-news-bul-gen-${c.id}`}
                              className="px-3 py-1.5 rounded-full text-xs bg-slate-800 text-slate-100
                                                hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-1.5">
                {genFor === c.id
                  ? <Loader2 className="w-3 h-3 animate-spin" />
                  : <Play className="w-3 h-3" />}
                {c.name}
              </button>
            ))}
          </div>
        )}
        {genErr && <div className="mt-2 text-xs text-red-400">{String(genErr)}</div>}
      </div>

      {busy ? (
        <div className="text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin inline" /> Loading…</div>
      ) : err ? (
        <div className="text-sm text-red-400">{String(err)}</div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 p-8 text-center text-sm text-slate-500">
          No bulletins yet.  Generate one above.
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((b) => (
            <div key={b.id}
                      data-testid={`admin-news-bul-card-${b.id}`}
                      className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <div className="text-sm font-bold">{b.channel_id}</div>
                <span className="text-[10px] font-mono text-slate-500">
                  · {b.bulletin_type} · {(b.headline_ids || []).length} headlines · {b.duration_seconds || 0}s · {b.tts_source || "text_only"}
                </span>
                <span className={`ml-auto text-[10px] font-mono uppercase tracking-widest ${
                    b.status === "live" ? "text-emerald-400"
                                              : b.status === "draft" ? "text-amber-400"
                                              : "text-slate-500"}`}>
                  {b.status}
                </span>
              </div>
              {b.script_text && (
                <div className="text-xs text-slate-300 line-clamp-3">{b.script_text}</div>
              )}
              {b.tts_error && (
                <div className="mt-1 text-[10px] font-mono text-amber-400">
                  TTS: {b.tts_error}
                </div>
              )}
              {b.audio_url && (
                <audio controls src={b.audio_url}
                              data-testid={`admin-news-bul-audio-${b.id}`}
                              className="w-full mt-2" />
              )}
              <div className="mt-2 flex gap-2">
                {b.status === "draft" && (
                  <button onClick={() => publish(b.id)}
                                  data-testid={`admin-news-bul-publish-${b.id}`}
                                  className="px-3 py-1 rounded-full bg-emerald-500 text-white text-xs font-bold
                                                    hover:bg-emerald-400">
                    Publish
                  </button>
                )}
                <div className="text-[10px] font-mono text-slate-600 self-center">
                  ID: {b.id}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
