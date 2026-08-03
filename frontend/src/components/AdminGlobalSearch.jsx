// Phase T — Admin global search (Cmd/Ctrl-K palette).
// Registers a global keyboard listener at the App shell level.  Renders
// a modal overlay with a search input + typeahead grouped results.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { Search, Loader2, X, User, Building2, Store, Radio,
                 Megaphone } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TYPE_META = {
  user:       { Icon: User,       label: "Users",       tint: "text-cyan-400" },
  advertiser: { Icon: Megaphone, label: "Advertisers", tint: "text-amber-400" },
  business:  { Icon: Store,       label: "Businesses",  tint: "text-emerald-400" },
  station:    { Icon: Radio,       label: "Stations",    tint: "text-fuchsia-400" },
  campaign:  { Icon: Building2, label: "Campaigns",  tint: "text-purple-400" },
};

export default function AdminGlobalSearch() {
  const [open,    setOpen]    = useState(false);
  const [q,       setQ]       = useState("");
  const [busy,    setBusy]    = useState(false);
  const [results, setResults] = useState(null);
  const [err,     setErr]     = useState(null);
  const inputRef = useRef(null);
  const nav = useNavigate();
  const { pathname } = useLocation();

  // Only mount the listener + overlay when on an /admin/* route.
  const isAdmin = pathname.startsWith("/admin");

  // Cmd/Ctrl + K global shortcut + programmatic open via custom event.
  useEffect(() => {
    if (!isAdmin) return undefined;
    const isTyping = () => {
      const el = document.activeElement;
      if (!el) return false;
      const tag = (el.tagName || "").toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      if (el.getAttribute && el.getAttribute("contenteditable") === "true") return true;
      return false;
    };
    const handler = (e) => {
      const modKey = e.metaKey || e.ctrlKey;
      if (modKey && (e.key === "k" || e.key === "K")) {
        if (!open && isTyping()) return;
        e.preventDefault();
        setOpen(true);
        setTimeout(() => inputRef.current?.focus(), 20);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    const openEvt = () => {
      setOpen(true);
      setTimeout(() => inputRef.current?.focus(), 20);
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("bigfm:admin-search-open", openEvt);
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("bigfm:admin-search-open", openEvt);
    };
  }, [isAdmin, open]);

  // Debounced search.
  useEffect(() => {
    if (!open) return undefined;
    if (!q || q.trim().length < 2) {
      setResults(null); return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setBusy(true); setErr(null);
      try {
        const { data } = await axios.get(
          `${API}/admin/search?q=${encodeURIComponent(q)}&limit=25`,
          { withCredentials: true });
        if (!cancelled) setResults(data);
      } catch (e) {
        if (!cancelled)
          setErr(e?.response?.data?.detail?.code
                  || e?.response?.data?.detail
                  || e.message);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 220);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q, open]);

  const flatResults = useMemo(() => {
    if (!results) return [];
    const buckets = [
      ["users",       results.users],
      ["advertisers", results.advertisers],
      ["businesses",  results.businesses],
      ["stations",    results.stations],
      ["campaigns",   results.campaigns],
    ];
    const out = [];
    for (const [bucket, list] of buckets) {
      if (list && list.length) out.push({ bucket, list });
    }
    return out;
  }, [results]);

  const jumpTo = (r) => {
    setOpen(false);
    if (r?.deep_link_path) nav(r.deep_link_path);
  };

  if (!isAdmin) return null;

  return (
    <>
      {/* Trigger button on the AdminSidebar / Home renders separately;
          the palette also opens via Cmd-K anywhere. */}
      {open && (
        <div className="fixed inset-0 z-[500] bg-slate-950/85 backdrop-blur-sm
                                  flex items-start justify-center pt-24 px-4"
                  data-testid="admin-global-search-overlay"
                  onClick={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="w-full max-w-2xl rounded-2xl bg-slate-900 border border-slate-800
                                    shadow-2xl overflow-hidden"
                    data-testid="admin-global-search">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-800">
              {busy ? <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                          : <Search className="w-4 h-4 text-purple-400" />}
              <input ref={inputRef} type="text" value={q}
                          onChange={(e) => setQ(e.target.value)}
                          data-testid="admin-global-search-input"
                          placeholder="Search users, advertisers, businesses, stations, campaigns…"
                          className="flex-1 bg-transparent outline-none text-sm placeholder:text-slate-500" />
              <button onClick={() => setOpen(false)}
                              data-testid="admin-global-search-close"
                              className="text-slate-500 hover:text-slate-300">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto">
              {err ? (
                <div className="p-4 text-sm text-red-400"
                          data-testid="admin-global-search-error">
                  {String(err)}
                </div>
              ) : !results && q.trim().length >= 2 && busy ? (
                <div className="p-4 text-xs text-slate-500">Searching …</div>
              ) : !results && !q ? (
                <div className="p-6 text-center text-xs text-slate-500"
                          data-testid="admin-global-search-empty-prompt">
                  Type at least 2 characters.  Cmd/Ctrl + K to reopen.
                </div>
              ) : results && flatResults.length === 0 ? (
                <div className="p-4 text-xs text-slate-500"
                          data-testid="admin-global-search-nohits">
                  No hits for &ldquo;{q}&rdquo;.
                </div>
              ) : (
                flatResults.map(({ bucket, list }) => {
                  const meta = TYPE_META[
                    bucket === "advertisers" ? "advertiser"
                      : bucket === "users" ? "user"
                      : bucket === "businesses" ? "business"
                      : bucket === "stations" ? "station"
                      : "campaign"];
                  const Icon = meta.Icon;
                  return (
                    <div key={bucket} className="border-b border-slate-800/70 last:border-0"
                              data-testid={`admin-global-search-bucket-${bucket}`}>
                      <div className="px-4 pt-3 pb-1 text-[10px] font-mono uppercase tracking-widest text-slate-500 flex items-center gap-2">
                        <Icon className={`w-3 h-3 ${meta.tint}`} /> {meta.label} · {list.length}
                      </div>
                      {list.map((r) => (
                        <button key={`${r.type}-${r.id}`}
                                        type="button" onClick={() => jumpTo(r)}
                                        data-testid={`admin-global-search-hit-${r.type}-${r.id}`}
                                        className="w-full text-left px-4 py-2 hover:bg-slate-800/60
                                                          border-t border-slate-800/40 first:border-0
                                                          focus:outline-none focus-visible:bg-slate-800/60">
                          <div className="text-sm font-medium truncate">{r.label}</div>
                          {r.subtitle && (
                            <div className="text-[10px] font-mono text-slate-500 truncate">
                              {r.subtitle}
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  );
                })
              )}
            </div>
            <div className="px-4 py-2 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-500">
              <span>Cmd/Ctrl + K · ESC to close</span>
              <span>{results?.total ?? 0} hits</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
