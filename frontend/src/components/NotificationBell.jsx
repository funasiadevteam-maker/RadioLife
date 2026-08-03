/**
 * Phase AD.12a — Unified notifications bell.
 *
 * Merges legacy station notifications (`station_notifications`) with
 * new AD.12 sponsored-ad deliveries into ONE feed.  Polls the merged
 * inbox count every 60s with visibility-aware pause.
 *
 * Sponsored rows show a "Sponsored" chip.  Row-visible fires
 * `/api/user/notifications/{delivery_id}/open` (advertiser is billed
 * per DELIVERY not per open — delivery billing happens when the
 * `/inbox` endpoint mints the row on the server side).  CTA click
 * fires `/click` and opens the target_url.  Dismiss X fires
 * `/dismiss`.
 *
 * Adblock resilient — all POSTs `.catch(() => {})`.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Bell, MessageCircle, Flame, X, Sparkles, CheckCheck, ExternalLink,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";

const POLL_INTERVAL_MS = 60 * 1000;
const NOTIF_LIMIT      = 20;

function relTime(iso) {
  if (!iso) return "";
  const sec = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60)    return `${Math.floor(sec)}s`;
  if (sec < 3600)  return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}


function NotifRow({ n, onDismiss, onOpen }) {
  const isSponsored = !!n.is_sponsored;
  const isUnread = !n.opened_at;
  const rowRef = useRef(null);
  const [openFired, setOpenFired] = useState(false);

  // IntersectionObserver → fire /open on visibility (mark read, not billed).
  useEffect(() => {
    if (!isSponsored || openFired || !rowRef.current) return;
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.intersectionRatio >= 0.5) {
          axios.post(`${API}/user/notifications/${n.id}/open`, {},
            { withCredentials: true }).catch(() => {});
          setOpenFired(true);
          io.disconnect();
        }
      }
    }, { threshold: [0.5] });
    io.observe(rowRef.current);
    return () => io.disconnect();
  }, [isSponsored, openFired, n.id]);

  const handleClick = (e) => {
    if (isSponsored) {
      e.preventDefault();
      axios.post(`${API}/user/notifications/${n.id}/click`, {},
        { withCredentials: true }).catch(() => {});
      if (onOpen) onOpen(n);
      try { window.open(n.target_url, "_blank", "noopener,noreferrer,sponsored"); }
      catch (_e) { /* pop-up blocked */ }
    }
  };

  const handleDismiss = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isSponsored) {
      axios.post(`${API}/user/notifications/${n.id}/dismiss`, {},
        { withCredentials: true }).catch(() => {});
    }
    if (onDismiss) onDismiss(n);
  };

  const Wrap = isSponsored ? "a" : Link;
  const wrapProps = isSponsored
    ? { href: n.target_url, onClick: handleClick,
          rel: "noopener noreferrer sponsored", target: "_blank" }
    : { to: n.target_url };

  return (
    <Wrap
      {...wrapProps}
      ref={rowRef}
      data-testid={`notification-inbox-row-${n.id}`}
      data-sponsored={isSponsored ? "true" : "false"}
      data-unread={isUnread ? "true" : "false"}
      className="block px-3 py-2.5 border-b border-white/[0.04]
                              hover:bg-white/[0.04] transition-colors duration-150
                              relative"
      style={{ background: isUnread ? "rgba(0,217,255,0.04)" : "transparent" }}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 shrink-0">
          {n.icon_url ? (
            <img src={`${process.env.REACT_APP_BACKEND_URL}${n.icon_url}`}
                        alt="" className="w-8 h-8 rounded-md object-cover bg-slate-800" />
          ) : n.type === "new_comment" ? (
            <MessageCircle size={16} className="text-accent-electric" />
          ) : n.type === "post_reaction_milestone" ? (
            <Flame size={16} className="text-amber-400" />
          ) : (
            <Sparkles size={16} className="text-accent-electric" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-text-primary truncate">
              {n.title}
            </span>
            {isSponsored && (
              <span data-testid={`notification-inbox-row-${n.id}-sponsored`}
                          className="text-[9px] font-mono uppercase tracking-widest
                                              px-1.5 py-0.5 rounded bg-amber-500/15
                                              text-amber-400 border border-amber-500/30
                                              shrink-0">
                Sponsored
              </span>
            )}
            <span className="text-[10px] text-text-secondary shrink-0 ml-auto">
              {relTime(n.delivered_at || n.created_at)}
            </span>
          </div>
          {n.body && (
            <div className="text-xs text-text-secondary mt-0.5 line-clamp-2">
              {n.body}
            </div>
          )}
          {isSponsored && n.cta_text && (
            <div data-testid={`notification-cta-${n.id}`}
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px]
                                            font-bold text-amber-400">
              {n.cta_text} <ExternalLink size={10} />
            </div>
          )}
        </div>
        {isSponsored && (
          <button type="button" onClick={handleDismiss}
                          data-testid={`notification-dismiss-${n.id}`}
                          aria-label="Dismiss"
                          className="shrink-0 p-1 rounded text-text-secondary/60
                                              hover:text-white hover:bg-white/[0.06]">
            <X size={12} />
          </button>
        )}
        {isUnread && !isSponsored && (
          <span className="w-1.5 h-1.5 rounded-full bg-accent-electric
                                        shrink-0 mt-1.5" />
        )}
      </div>
    </Wrap>
  );
}

export default function NotificationBell() {
  const { user } = useAuth();
  const [open, setOpen]       = useState(false);
  const [unread, setUnread]   = useState(0);
  const [items, setItems]     = useState(null);
  const dropdownRef = useRef(null);

  // Unread polling (60s, visibility-aware)
  const refreshUnread = useCallback(async () => {
    if (!user) return;
    try {
      const r = await axios.get(`${API}/user/notifications/unread_count`,
        { withCredentials: true });
      setUnread(r.data?.count ?? 0);
    } catch { /* ignore */ }
  }, [user]);

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;
    let timer = null;
    const tick = () => {
      if (cancelled) return;
      if (document.visibilityState === "visible") refreshUnread();
    };
    Promise.resolve().then(() => { if (!cancelled) refreshUnread(); });
    timer = setInterval(tick, POLL_INTERVAL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") refreshUnread();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [user, refreshUnread]);

  // Load merged inbox when dropdown opens.
  const loadList = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/user/notifications/inbox?limit=${NOTIF_LIMIT}`,
        { withCredentials: true });
      setItems(r.data?.items || []);
      // The /inbox call mints deliveries + fires billing on the server;
      // refresh unread badge immediately.
      refreshUnread();
    } catch {
      setItems([]);
    }
  }, [refreshUnread]);

  const toggleOpen = () => {
    if (!user) return;
    setOpen((v) => {
      const next = !v;
      if (next) loadList();
      return next;
    });
  };

  const markAllRead = async () => {
    try {
      await axios.post(`${API}/me/notifications/read_all`, {},
        { withCredentials: true });
      setUnread(0);
      setItems((arr) => (arr || []).map((n) =>
        ({ ...n, opened_at: n.opened_at || new Date().toISOString(),
                      read_at: n.read_at || new Date().toISOString() })));
    } catch { /* */ }
  };

  const dismissLocal = (n) => {
    setItems((arr) => (arr || []).filter((x) => x.id !== n.id));
    refreshUnread();
  };

  // Click-outside close
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!user) return null;

  return (
    <div ref={dropdownRef} style={{ position: "relative" }}>
      <button type="button"
                      data-testid="notification-bell"
                      aria-label="Notifications"
                      onClick={toggleOpen}
                      className="relative w-10 h-10 grid place-items-center rounded-full
                                          text-text-secondary hover:text-white
                                          hover:bg-white/5 transition-colors duration-150">
        <Bell size={18} />
        {unread > 0 && (
          <span data-testid="notification-badge-count"
                      className="absolute top-1 right-1 min-w-[16px] h-[16px]
                                          px-1 rounded-full bg-accent-electric text-bg-base
                                          text-[10px] font-semibold flex items-center
                                          justify-center">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div data-testid="notification-dropdown"
                  className="absolute right-0 top-full mt-2 w-[380px]
                                          max-h-[520px] overflow-y-auto z-50
                                          rounded-xl border border-white/[0.08]
                                          bg-bg-elevated shadow-2xl">
          <header className="flex items-center justify-between px-3 py-2.5
                                                      border-b border-white/[0.06] sticky top-0
                                                      bg-bg-elevated z-10">
            <h4 className="text-sm font-semibold text-text-primary">
              Notifications
            </h4>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button type="button"
                                onClick={markAllRead}
                                data-testid="notification-mark-all-read"
                                className="text-xs text-accent-electric inline-flex
                                                          items-center gap-1 hover:underline">
                  <CheckCheck size={12} /> Mark all read
                </button>
              )}
              <Link to="/notifications" onClick={() => setOpen(false)}
                          data-testid="notification-view-all"
                          className="text-xs text-accent-electric hover:underline">
                View all
              </Link>
              <button type="button" onClick={() => setOpen(false)}
                              aria-label="Close notifications"
                              className="text-text-secondary hover:text-white">
                <X size={14} />
              </button>
            </div>
          </header>
          {items === null && (
            <div data-testid="notification-loading"
                        className="p-4 text-sm text-text-secondary">
              Loading…
            </div>
          )}
          {items && items.length === 0 && (
            <div data-testid="notification-empty"
                        className="p-6 text-center text-sm text-text-secondary">
              You&rsquo;re all caught up.
            </div>
          )}
          {items && items.length > 0 && (
            <div data-testid="notification-list">
              {items.map((n) => (
                <NotifRow key={n.id} n={n}
                                        onDismiss={dismissLocal} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
