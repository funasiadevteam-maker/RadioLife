// Phase AD.12a — Full-page notifications feed at /notifications.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Bell, ExternalLink, X, Sparkles,
                Loader2, Inbox } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

export default function Notifications() {
  const { user } = useAuth();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/user/notifications/inbox?limit=50`,
        { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_e) { setItems([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

  if (!user) {
    return (
      <div className="min-h-screen p-8 text-slate-400 text-sm"
                data-testid="notifications-anon">
        Sign in to view your notifications.
        <Link to="/login" className="ml-2 text-accent-electric">Sign in →</Link>
      </div>
    );
  }

  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const cardBg = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`${bg} min-h-screen`} data-testid="notifications-page">
      <div className="max-w-4xl xl:max-w-5xl mx-auto px-4 py-6 sm:py-10">
        <Link to="/" data-testid="notifications-back"
                    className={`inline-flex items-center gap-1 text-xs ${muted}
                                      hover:opacity-80 mb-4`}>
          <ArrowLeft size={12} /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl grid place-items-center
                                      bg-gradient-to-br from-fuchsia-500 to-amber-500">
            <Bell size={22} className="text-white" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Your inbox
            </div>
            <h1 className="text-3xl md:text-4xl xl:text-5xl font-black">Notifications</h1>
          </div>
        </div>

        {loading ? (
          <div className={`inline-flex items-center gap-2 ${muted}`}
                        data-testid="notifications-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : (items || []).length === 0 ? (
          <div className={`${cardBg} rounded-2xl p-10 text-center`}
                        data-testid="notifications-empty">
            <Inbox className={`w-10 h-10 mx-auto mb-3 ${muted}`} />
            <div className="font-semibold">Your inbox is empty.</div>
            <p className={`text-sm mt-1 ${muted}`}>
              We&rsquo;ll drop new activity and offers here.
            </p>
          </div>
        ) : (
          <div className={`${cardBg} rounded-2xl overflow-hidden`}
                        data-testid="notifications-list">
            {items.map((n) => (
              <FullRow key={n.id} n={n} light={light}
                                onDismiss={() => setItems((arr) =>
                                                              (arr || []).filter((x) => x.id !== n.id))} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


function FullRow({ n, light, onDismiss }) {
  const isSponsored = !!n.is_sponsored;

  const handleClick = (e) => {
    if (!isSponsored) return;
    e.preventDefault();
    axios.post(`${API}/user/notifications/${n.id}/click`, {},
      { withCredentials: true }).catch(() => {});
    try { window.open(n.target_url, "_blank",
                                        "noopener,noreferrer,sponsored"); }
    catch (_e) { /* */ }
  };

  const handleDismiss = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isSponsored) {
      axios.post(`${API}/user/notifications/${n.id}/dismiss`, {},
        { withCredentials: true }).catch(() => {});
    }
    onDismiss();
  };

  const Wrap = isSponsored ? "a" : Link;
  const wrapProps = isSponsored
    ? { href: n.target_url, onClick: handleClick,
          rel: "noopener noreferrer sponsored", target: "_blank" }
    : { to: n.target_url };

  return (
    <Wrap {...wrapProps}
                data-testid={`notification-inbox-row-${n.id}`}
                data-sponsored={isSponsored ? "true" : "false"}
                className={`block px-5 py-4 ${light ? "border-b border-slate-100 last:border-0" : "border-b border-slate-800 last:border-0"} hover:opacity-95 transition`}>
      <div className="flex items-start gap-3">
        <div className="shrink-0">
          {n.icon_url ? (
            <img src={`${process.env.REACT_APP_BACKEND_URL}${n.icon_url}`}
                        alt="" className="w-12 h-12 rounded-lg object-cover
                                                                      bg-slate-800/40" />
          ) : (
            <div className="w-12 h-12 rounded-lg grid place-items-center
                                        bg-gradient-to-br from-fuchsia-500 to-amber-500">
              <Sparkles size={18} className="text-white" />
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-black">{n.title}</span>
            {isSponsored && (
              <span data-testid={`notification-inbox-row-${n.id}-sponsored`}
                          className="text-[9px] font-mono uppercase tracking-widest
                                              px-1.5 py-0.5 rounded bg-amber-500/15
                                              text-amber-400 border border-amber-500/30">
                Sponsored
              </span>
            )}
          </div>
          <div className={`text-xs mt-1 ${light ? "text-slate-600" : "text-slate-300"}`}>
            {n.body}
          </div>
          {isSponsored && n.cta_text && (
            <div data-testid={`notification-cta-${n.id}`}
                        className="mt-2 inline-flex items-center gap-1 px-3 py-1.5
                                              rounded-full text-xs font-black
                                              bg-amber-500 text-slate-900">
              {n.cta_text} <ExternalLink size={11} />
            </div>
          )}
        </div>
        {isSponsored && (
          <button type="button" onClick={handleDismiss}
                          data-testid={`notification-dismiss-${n.id}`}
                          aria-label="Dismiss"
                          className={`shrink-0 p-1.5 rounded-md
                                                ${light ? "hover:bg-slate-100 text-slate-500"
                                                              : "hover:bg-slate-800 text-slate-400"}`}>
            <X size={14} />
          </button>
        )}
      </div>
    </Wrap>
  );
}
