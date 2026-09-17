// Admin — Radio language policy restore controls.
// Re-enable stations hidden by the Hindi/English/Indian/news/US-UAE-UK
// language policy: one-tap per station, or a whole country/language group.
import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, ArrowLeft, RotateCcw, Search, Globe2, Languages } from "lucide-react";
import { API } from "@/AuthContext";

const cfg = { withCredentials: true };

export default function AdminRadioLanguage() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [q, setQ] = useState("");
  const [list, setList] = useState({ items: [], total: 0 });
  const [listLoading, setListLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/radio-import/hidden-summary`, cfg);
      setSummary(r.data);
    } catch (e) {
      toast.error("Failed to load summary");
    } finally { setLoading(false); }
  }, []);

  const loadList = useCallback(async (query) => {
    setListLoading(true);
    try {
      const params = { limit: 30 };
      if (query) params.q = query;
      const r = await axios.get(`${API}/admin/radio-import/hidden-stations`, { ...cfg, params });
      setList({ items: r.data.items || [], total: r.data.total || 0 });
    } catch (e) {
      setList({ items: [], total: 0 });
    } finally { setListLoading(false); }
  }, []);

  useEffect(() => { loadSummary(); loadList(""); }, [loadSummary, loadList]);

  const restore = async (scope, value, label) => {
    setBusy(`${scope}:${value || "all"}`);
    try {
      const r = await axios.post(`${API}/admin/radio-import/restore`, { scope, value }, cfg);
      toast.success(`Re-enabled ${r.data.restored} station${r.data.restored === 1 ? "" : "s"}${label ? ` · ${label}` : ""}`);
      await loadSummary();
      await loadList(q);
    } catch (e) {
      toast.error("Restore failed");
    } finally { setBusy(""); }
  };

  const toggleStation = async (station, active) => {
    setBusy(`st:${station.id}`);
    try {
      await axios.post(`${API}/admin/radio-import/station/${station.id}/set-active`, { active }, cfg);
      toast.success(active ? `Enabled ${station.name}` : `Disabled ${station.name}`);
      await loadSummary();
      await loadList(q);
    } catch (e) {
      toast.error("Update failed");
    } finally { setBusy(""); }
  };

  const onSearch = (e) => { e.preventDefault(); loadList(q.trim()); };

  return (
    <div data-testid="admin-radio-language-page"
      className="min-h-screen bg-slate-950 text-white max-w-[1100px] mx-auto px-5 pt-6 pb-24">
      <Link to="/admin" data-testid="admin-radio-language-back"
        className="inline-flex items-center gap-1 text-xs text-white/50 hover:text-white mb-4">
        <ArrowLeft size={12} /> Back to Admin
      </Link>

      <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Radio language policy</h1>
          <p className="text-sm text-white/60 mt-1">
            Re-enable stations hidden by the Hindi / English / Indian / news / US-UAE-UK policy.
          </p>
        </div>
        <button
          type="button"
          onClick={() => restore("all", null, "everything")}
          disabled={!!busy}
          data-testid="admin-radio-restore-all"
          className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-amber-400 text-slate-950 font-bold text-sm hover:bg-amber-300 disabled:opacity-50">
          {busy === "all:all" ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
          Re-enable all hidden
        </button>
      </div>

      {loading ? (
        <div className="py-20 flex justify-center"><Loader2 className="animate-spin" size={28} /></div>
      ) : summary ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
            <div className="rounded-2xl bg-white/[0.04] border border-white/[0.08] p-4" data-testid="admin-radio-stat-hidden">
              <div className="text-3xl font-black">{summary.total_hidden.toLocaleString()}</div>
              <div className="text-xs text-white/50 mt-1 uppercase tracking-widest">Hidden</div>
            </div>
            <div className="rounded-2xl bg-white/[0.04] border border-white/[0.08] p-4" data-testid="admin-radio-stat-active">
              <div className="text-3xl font-black text-emerald-400">{summary.total_active.toLocaleString()}</div>
              <div className="text-xs text-white/50 mt-1 uppercase tracking-widest">Active</div>
            </div>
          </div>

          {/* By country */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-3 text-white/80">
              <Globe2 size={15} /> <span className="font-bold text-sm uppercase tracking-widest">By country</span>
            </div>
            <div className="flex flex-wrap gap-2" data-testid="admin-radio-country-groups">
              {summary.by_country.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => restore("country", c.value, c.value)}
                  disabled={!!busy}
                  data-testid={`admin-radio-restore-country-${c.value}`}
                  className="inline-flex items-center gap-2 px-3 h-9 rounded-full bg-white/[0.05] border border-white/[0.10] text-sm hover:bg-white/[0.10] disabled:opacity-40">
                  <span className="font-semibold">{c.value}</span>
                  <span className="text-white/40">{c.count}</span>
                  {busy === `country:${c.value}` ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} className="text-amber-400" />}
                </button>
              ))}
            </div>
          </div>

          {/* By language */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-3 text-white/80">
              <Languages size={15} /> <span className="font-bold text-sm uppercase tracking-widest">By language</span>
            </div>
            <div className="flex flex-wrap gap-2" data-testid="admin-radio-language-groups">
              {summary.by_language.slice(0, 24).map((l) => (
                <button
                  key={l.value}
                  type="button"
                  onClick={() => restore("language", l.value, l.value)}
                  disabled={!!busy}
                  data-testid={`admin-radio-restore-language-${l.value}`}
                  className="inline-flex items-center gap-2 px-3 h-9 rounded-full bg-white/[0.05] border border-white/[0.10] text-sm hover:bg-white/[0.10] disabled:opacity-40">
                  <span className="font-semibold capitalize">{l.value}</span>
                  <span className="text-white/40">{l.count}</span>
                  {busy === `language:${l.value}` ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} className="text-amber-400" />}
                </button>
              ))}
            </div>
          </div>
        </>
      ) : null}

      {/* Per-station search + toggle */}
      <div className="mb-3 flex items-center gap-2 text-white/80">
        <span className="font-bold text-sm uppercase tracking-widest">Hidden stations</span>
        <span className="text-white/40 text-sm">({list.total.toLocaleString()})</span>
      </div>
      <form onSubmit={onSearch} className="relative mb-4 max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search hidden stations by name…"
          data-testid="admin-radio-search"
          className="w-full pl-9 pr-3 h-10 rounded-lg bg-white/[0.05] border border-white/[0.10] text-sm text-white placeholder:text-white/30 outline-none focus:border-cyan-400/50" />
      </form>

      {listLoading ? (
        <div className="py-10 flex justify-center"><Loader2 className="animate-spin" size={22} /></div>
      ) : list.items.length === 0 ? (
        <div className="py-10 text-center text-white/40 text-sm" data-testid="admin-radio-empty">
          No hidden stations match.
        </div>
      ) : (
        <div className="space-y-2" data-testid="admin-radio-hidden-list">
          {list.items.map((s) => (
            <div key={s.id} data-testid={`admin-radio-hidden-${s.id}`}
              className="flex items-center gap-3 rounded-xl bg-white/[0.03] border border-white/[0.06] p-3">
              <div className="w-10 h-10 rounded-lg overflow-hidden bg-slate-800 shrink-0">
                {s.favicon ? <img src={s.favicon} alt="" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : null}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold truncate">{s.name}</div>
                <div className="text-xs text-white/40 truncate">
                  {[s.country_code, s.language].filter(Boolean).join(" · ") || "—"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => toggleStation(s, true)}
                disabled={!!busy}
                data-testid={`admin-radio-enable-${s.id}`}
                className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 text-xs font-bold hover:bg-emerald-500/30 disabled:opacity-40">
                {busy === `st:${s.id}` ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                Enable
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
