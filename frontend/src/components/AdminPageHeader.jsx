// Phase T — shared admin page header.  Breadcrumb + title + right-aligned
// action slot.  Also renders the pin-this-page toggle so every admin
// page participates in the sidebar Pinned list.
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import axios from "axios";
import { ChevronRight, Pin, PinOff } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function AdminPageHeader({
  title, subtitle, breadcrumbs = [], actions = null,
  Icon = null, tint = "text-purple-500", pinLabel = null,
}) {
  const { pathname } = useLocation();
  const [pinned, setPinned] = useState(null);   // null = unknown yet.
  const [busy, setBusy] = useState(false);

  const loadPins = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/nav/pins`,
                                                    { withCredentials: true });
      const isPinned = (data?.items || []).some((p) => p.route === pathname);
      setPinned(isPinned);
    } catch {
      setPinned(false);
    }
  }, [pathname]);

  useEffect(() => { loadPins(); }, [loadPins]);

  const togglePin = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (pinned) {
        await axios.delete(
          `${API}/admin/nav/pin${pathname}`, { withCredentials: true });
        setPinned(false);
      } else {
        await axios.post(`${API}/admin/nav/pin`,
                                    { route: pathname, label: pinLabel || title },
                                    { withCredentials: true });
        setPinned(true);
      }
      // Notify sidebar to reload.
      window.dispatchEvent(new CustomEvent("bigfm:admin-pins-changed"));
    } finally {
      setBusy(false);
    }
  };

  const trail = [{ label: "Admin", to: "/admin" }, ...(breadcrumbs || [])];

  return (
    <div className="mb-6" data-testid="admin-page-header">
      <nav className="flex items-center flex-wrap gap-1 text-[11px] font-mono text-slate-500 mb-1"
                aria-label="Breadcrumb" data-testid="admin-page-breadcrumb">
        {trail.map((c, i) => (
          <span key={i} className="inline-flex items-center gap-1">
            {i > 0 && <ChevronRight className="w-3 h-3 text-slate-600" />}
            {c.to && i < trail.length - 1 ? (
              <Link to={c.to} className="hover:text-slate-300"
                          data-testid={`admin-page-crumb-${i}`}>{c.label}</Link>
            ) : (
              <span className={i === trail.length - 1 ? "text-slate-300" : ""}
                          data-testid={`admin-page-crumb-${i}`}>{c.label}</span>
            )}
          </span>
        ))}
      </nav>
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="min-w-0">
          <h1 className="text-3xl md:text-4xl xl:text-5xl font-black tracking-tight
                                    inline-flex items-center gap-3"
                    data-testid="admin-page-title">
            {Icon && <Icon className={`w-8 h-8 xl:w-10 xl:h-10 ${tint}`} />}
            {title}
          </h1>
          {subtitle && (
            <div className="mt-1 text-sm text-slate-400"
                      data-testid="admin-page-subtitle">
              {subtitle}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap" data-testid="admin-page-actions">
          <button type="button" onClick={togglePin} disabled={busy || pinned === null}
                          data-testid="admin-page-pin-toggle"
                          data-pinned={String(!!pinned)}
                          title={pinned ? "Unpin from sidebar" : "Pin to sidebar"}
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                                          text-xs font-bold transition
                                          focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500
                                          disabled:opacity-50 ${
                              pinned
                                ? "bg-amber-500/15 text-amber-400 border border-amber-500/40"
                                : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-transparent"}`}>
            {pinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
            {pinned ? "Unpin" : "Pin"}
          </button>
          {actions}
        </div>
      </div>
    </div>
  );
}
