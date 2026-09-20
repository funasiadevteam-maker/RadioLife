/**
 * Phase 16c — Venue Staff dashboard.
 *
 * Provides named exports for each sub-route, registered in `App.js`:
 *   VenueDashboard  → /venue
 *   VenueTVs         → /venue/tvs
 *   VenueTrivia     → /venue/trivia
 *   VenueAnnounce  → /venue/announcements
 *   VenueRedeem    → /venue/redeem
 *   VenuePlayers   → /venue/players
 *   VenueSettings  → /venue/settings
 *   VenueOnboard   → /venue/onboard
 *
 * All routes lazily fetch the user's first venue from `/api/venue/me`
 * and gate access to staff only.  Multi-venue switching is parked for
 * 16d (most QA venues will have 1 site).
 */
import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useNavigate, NavLink } from "react-router-dom";
import { toast } from "sonner";
import {
  Tv, Megaphone, Ticket, Users, Settings, BarChart3, Plus, X,
  Copy, CheckCircle2, Trash2, ShieldCheck, Sparkles, Hash,
} from "lucide-react";
import { Card } from "@/shell/primitives";
import { Button } from "@/shell/primitives";

const API = process.env.REACT_APP_BACKEND_URL + "/api";
axios.defaults.withCredentials = true;

// ─── Shared sidebar nav ──────────────────────────────────────────────
const NAV = [
  { to: "/venue",                 label: "Overview",          icon: BarChart3 },
  { to: "/venue/tvs",             label: "TVs",                icon: Tv },
  { to: "/venue/trivia",          label: "Start trivia",    icon: Sparkles },
  { to: "/venue/announcements", label: "Announcements", icon: Megaphone },
  { to: "/venue/redeem",         label: "Redeem coupon", icon: Ticket },
  { to: "/venue/players",        label: "Live players",    icon: Users },
  { to: "/venue/settings",       label: "Settings",          icon: Settings },
];

function Shell({ venue, children, title }) {
  return (
    <div className="min-h-screen px-6 sm:px-10 lg:px-14 pb-24 pt-6">
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-10 max-w-7xl mx-auto">
        <aside className="space-y-1" data-testid="venue-nav">
          <div className="px-3 pb-4">
            <div className="text-[10px] tracking-[0.3em] uppercase text-text-secondary font-mono">
              Venue HQ
            </div>
            <div className="font-display font-bold text-2xl tracking-display-tight mt-1">
              {venue?.name || "—"}
            </div>
            <div className="text-xs text-text-secondary mt-1 capitalize">
              {venue?.plan_tier || "starter"} · {venue?.market}
            </div>
          </div>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/venue"}
                          className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2 rounded-xl text-sm
                              ${isActive ? "bg-accent-magenta/15 text-accent-magenta"
                                              : "text-text-secondary hover:text-text-primary hover:bg-white/[0.04]"}`}
                          data-testid={`venue-nav-${to === "/venue" ? "home" : to.split("/").pop()}`}>
              <Icon size={14} /> {label}
            </NavLink>
          ))}
        </aside>
        <main className="space-y-6 min-w-0">
          {title && (
            <h1 className="font-display font-bold text-4xl tracking-display-tight">
              {title}
            </h1>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

function useVenueOrRedirect() {
  const navigate = useNavigate();
  const [venue, setVenue] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/venue/me`)
          .then(({ data }) => {
            if (!alive) return;
            if (!data.venues || data.venues.length === 0) {
              navigate("/venue/onboard", { replace: true });
              return;
            }
            setVenue(data.venues[0]);
            setLoading(false);
          })
          .catch(() => { if (alive) { navigate("/login", { replace: true }); } });
    return () => { alive = false; };
  }, [navigate]);
  return { venue, loading };
}

// ─── /venue — overview ───────────────────────────────────────────────
export function VenueDashboard() {
  const { venue, loading } = useVenueOrRedirect();
  const [stats, setStats] = useState(null);
  useEffect(() => {
    if (!venue) return;
    axios.get(`${API}/venue/${venue.id}/stats?period=today`)
          .then(({ data }) => setStats(data))
          .catch(() => {});
  }, [venue]);
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Overview">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="venue-overview-stats">
        <Stat label="Live players" value={stats?.live_players ?? "—"} />
        <Stat label="Live rooms"   value={stats?.live_rooms ?? "—"} />
        <Stat label="Rooms today"  value={stats?.rooms ?? "—"} />
        <Stat label="Coupons today" value={stats?.coupons ?? "—"} />
      </div>
      <Card className="p-6">
        <div className="font-display font-bold text-xl tracking-display-tight mb-2">
          Welcome, staff.
        </div>
        <p className="text-text-secondary text-sm max-w-xl">
          Pair a TV, start a live trivia round, push an announcement to
          tonight's players, or redeem a winning coupon — all from this
          dashboard.
        </p>
      </Card>
    </Shell>
  );
}

function Stat({ label, value }) {
  return (
    <Card className="p-4">
      <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
        {label}
      </div>
      <div className="font-display font-bold text-3xl tracking-display-tight mt-1">
        {value}
      </div>
    </Card>
  );
}

// ─── /venue/tvs — pair + revoke ─────────────────────────────────────
export function VenueTVs() {
  const { venue, loading } = useVenueOrRedirect();
  const [tvs, setTvs]     = useState([]);
  const [pair, setPair]    = useState(null); // {pairing_code, expires_at}

  const refresh = async () => {
    if (!venue) return;
    try {
      const { data } = await axios.get(`${API}/venue/${venue.id}/tvs`);
      setTvs(data.tvs || []);
    } catch (e) { /* */ }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [venue]);

  const issue = async () => {
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/tvs/pair`);
      setPair(data);
      refresh();
    } catch (e) { toast.error("Couldn't generate a pairing code."); }
  };

  const revoke = async (tv) => {
    try {
      await axios.post(`${API}/venue/${venue.id}/tvs/${tv.id}/revoke`);
      toast.success("TV revoked.");
      refresh();
    } catch (e) { toast.error("Couldn't revoke."); }
  };

  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Paired TVs">
      <Card className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display font-bold text-xl tracking-display-tight">Pair a new TV</div>
            <div className="text-text-secondary text-sm">
              Type <span className="font-mono text-text-primary">bigfm.app/tv</span> on the
              venue TV, then enter the code we generate.
            </div>
          </div>
          <Button variant="primary" onClick={issue} data-testid="venue-tv-pair-btn">
            <Plus size={14} /> Generate code
          </Button>
        </div>
        {pair && (
          <div className="px-6 py-5 rounded-2xl bg-accent-electric/[0.08] border border-accent-electric/30
                                flex items-center gap-6"
                data-testid="venue-tv-pair-code">
            <div className="font-mono text-4xl tracking-widest text-accent-electric">
              {pair.pairing_code}
            </div>
            <div className="text-xs text-text-secondary">
              Expires in 10&nbsp;min · share verbally or as a QR.
            </div>
          </div>
        )}
      </Card>
      <Card className="p-6">
        <div className="font-display font-bold text-xl tracking-display-tight mb-4">
          All TVs
        </div>
        {tvs.length === 0 && (
          <div className="text-text-secondary text-sm" data-testid="venue-tv-empty">
            No TVs paired yet.
          </div>
        )}
        <div className="space-y-2">
          {tvs.map((t) => (
            <div key={t.id}
                  className="flex items-center justify-between px-4 py-3 rounded-xl bg-white/[0.03]"
                  data-testid={`venue-tv-row-${t.id}`}>
              <div className="flex items-center gap-4 min-w-0">
                <Tv size={16} className="text-accent-electric flex-shrink-0" />
                <div className="min-w-0">
                  <div className="font-mono text-sm truncate">{t.id}</div>
                  <div className="text-xs text-text-secondary">
                    <span className="uppercase">{t.status}</span>
                    {t.last_seen && <> · last seen {new Date(t.last_seen).toLocaleString()}</>}
                  </div>
                </div>
              </div>
              {t.status === "active" && (
                <button className="text-text-secondary hover:text-accent-magenta px-2"
                              onClick={() => revoke(t)}
                              data-testid={`venue-tv-revoke-${t.id}`}>
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      </Card>
    </Shell>
  );
}

// ─── /venue/trivia — start a venue-branded room ─────────────────────
export function VenueTrivia() {
  const { venue, loading } = useVenueOrRedirect();
  const [cats, setCats]      = useState([]);
  const [picked, setPicked] = useState(null);
  const navigate              = useNavigate();
  useEffect(() => {
    axios.get(`${API}/trivia/categories`).then(({ data }) => setCats(data.categories || []));
  }, []);
  const start = async () => {
    if (!picked) return;
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/trivia/start`,
                                                          { category_id: picked });
      toast.success(`Room ${data.room_code} started.`);
      navigate(`/trivia/rooms/${data.room_code}`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((d && typeof d === "object" && d.message) || d || "Couldn't start room.");
    }
  };
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Start a trivia round">
      <Card className="p-6 space-y-5">
        <div className="text-text-secondary text-sm">
          Pick a category — the room appears on every paired TV automatically.
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="venue-trivia-cats">
          {cats.map((c) => (
            <button key={c.id}
                          onClick={() => setPicked(c.id)}
                          className={`px-4 py-4 rounded-2xl border text-left transition
                                        ${picked === c.id
                                            ? "border-accent-magenta bg-accent-magenta/[0.08]"
                                            : "border-white/[0.08] hover:border-white/[0.18]"}`}
                          data-testid={`venue-trivia-cat-${c.slug}`}>
              <div className="font-display font-bold text-base">{c.name}</div>
              <div className="text-xs text-text-secondary mt-1">{c.market || "global"}</div>
            </button>
          ))}
        </div>
        <Button variant="primary" onClick={start} disabled={!picked}
                    data-testid="venue-trivia-start-btn">
          Start room <Sparkles size={14} />
        </Button>
      </Card>
    </Shell>
  );
}

// ─── /venue/announcements — broadcast a banner ──────────────────────
export function VenueAnnounce() {
  const { venue, loading } = useVenueOrRedirect();
  const [message, setMessage] = useState("");
  const [emoji, setEmoji]      = useState("");
  const QUICK_EMOJI = ["🍰", "🍕", "🥤", "🎁", "🍻", "🏆"];
  const send = async () => {
    if (!message.trim()) { toast.error("Message is empty."); return; }
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/announcement`,
                                                          { message, emoji: emoji || null,
                                                            target: "all_rooms" });
      toast.success(`Announcement sent to ${data.rooms.length} room(s) + ${data.tvs.length} TV(s).`);
      setMessage(""); setEmoji("");
    } catch (e) { toast.error("Couldn't broadcast."); }
  };
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Push an announcement">
      <Card className="p-6 space-y-5">
        <div className="text-text-secondary text-sm">
          Lands as a giant overlay on every paired TV AND every player's phone
          in your venue rooms.  Use sparingly.
        </div>
        <div className="space-y-3">
          <label className="block text-xs text-text-secondary uppercase tracking-widest font-mono">
            Emoji (optional)
          </label>
          <div className="flex gap-2">
            {QUICK_EMOJI.map((e) => (
              <button key={e}
                            onClick={() => setEmoji(e)}
                            className={`h-12 w-12 rounded-xl text-2xl ${emoji === e
                              ? "bg-accent-magenta/15 border-2 border-accent-magenta"
                              : "bg-white/[0.04] border-2 border-transparent hover:border-white/20"}`}
                            data-testid={`venue-ann-emoji-${e}`}>
                {e}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <label className="block text-xs text-text-secondary uppercase tracking-widest font-mono">
            Message
          </label>
          <textarea
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Free dessert for top 3 tonight!"
            className="w-full px-4 py-3 rounded-2xl bg-bg-glass border border-white/[0.10]
                              outline-none focus:border-accent-electric/60 resize-none"
            data-testid="venue-ann-textarea"
          />
        </div>
        <Button variant="primary" onClick={send} data-testid="venue-ann-send-btn">
          <Megaphone size={14} /> Broadcast
        </Button>
      </Card>
    </Shell>
  );
}

// ─── /venue/redeem — coupon redeem ──────────────────────────────────
export function VenueRedeem() {
  const { venue, loading } = useVenueOrRedirect();
  const [code, setCode]      = useState("");
  const [last, setLast]      = useState(null);
  const redeem = async () => {
    const c = code.trim();
    if (!c) return;
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/coupons/redeem`, { code: c });
      setLast({ ok: true, ...data });
      try { new Audio("/sfx/ok_chime.mp3").play().catch(()=>{}); } catch (_) {/* */ }
      setCode("");
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = (d && typeof d === "object" && d.message) || d || "Couldn't redeem.";
      setLast({ ok: false, message: msg });
    }
  };
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Redeem a coupon">
      <Card className="p-6 space-y-5">
        <div className="text-text-secondary text-sm">
          Scan the player's QR or type the code below.  Verified server-side
          against this venue's offer book.
        </div>
        <form onSubmit={(e) => { e.preventDefault(); redeem(); }} className="flex gap-3">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="cpn_xxxxxxxxxxxx"
            className="flex-1 px-4 py-3 rounded-2xl bg-bg-glass border border-white/[0.10]
                              font-mono outline-none focus:border-accent-electric/60"
            data-testid="venue-redeem-input"
          />
          <Button variant="primary" type="submit" data-testid="venue-redeem-btn">
            <Ticket size={14} /> Redeem
          </Button>
        </form>
        {last && (
          last.ok ? (
            <div className="rounded-2xl border border-green-500/40 bg-green-500/[0.06] p-5
                                    flex items-center gap-4"
                  data-testid="venue-redeem-ok">
              <CheckCircle2 size={28} className="text-green-400" />
              <div>
                <div className="font-display font-bold text-lg">Redeemed</div>
                <div className="text-xs text-text-secondary font-mono">
                  {last.coupon_id} · {last.redeemed_at}
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-accent-magenta/40 bg-accent-magenta/[0.06] p-5"
                  data-testid="venue-redeem-err">
              <div className="font-display font-bold text-base">Couldn't redeem</div>
              <div className="text-xs text-text-secondary">{last.message}</div>
            </div>
          )
        )}
      </Card>
    </Shell>
  );
}

// ─── /venue/players — live roster + kick ────────────────────────────
export function VenuePlayers() {
  const { venue, loading } = useVenueOrRedirect();
  const [players, setPlayers] = useState([]);
  const refresh = async () => {
    if (!venue) return;
    try {
      const { data } = await axios.get(`${API}/venue/${venue.id}/players`);
      setPlayers(data.players || []);
    } catch (_) {/* */}
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [venue]);
  const kick = async (p) => {
    try {
      await axios.delete(`${API}/venue/${venue.id}/rooms/${p.room_code}/players/${p.user_id}`);
      toast.success(`Kicked ${p.name}`);
      refresh();
    } catch (e) { toast.error("Couldn't kick."); }
  };
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Live players">
      <Card className="p-6">
        {players.length === 0 && (
          <div className="text-text-secondary text-sm" data-testid="venue-players-empty">
            No players in venue rooms right now.
          </div>
        )}
        <div className="space-y-2" data-testid="venue-players-list">
          {players.map((p) => (
            <div key={`${p.room_code}-${p.user_id}`}
                  className="flex items-center justify-between px-4 py-3 rounded-xl bg-white/[0.03]"
                  data-testid={`venue-player-row-${p.user_id}`}>
              <div className="min-w-0">
                <div className="font-display font-bold text-sm">{p.name}</div>
                <div className="text-xs text-text-secondary font-mono">
                  {p.room_code} · {p.score} pts · {p.connected ? "online" : "offline"}
                </div>
              </div>
              <button className="px-3 py-1 rounded-lg bg-accent-magenta/15 text-accent-magenta text-xs"
                            onClick={() => kick(p)}
                            data-testid={`venue-player-kick-${p.user_id}`}>
                Kick
              </button>
            </div>
          ))}
        </div>
      </Card>
    </Shell>
  );
}

// ─── /venue/settings — profile + staff ──────────────────────────────
export function VenueSettings() {
  const { venue, loading } = useVenueOrRedirect();
  const [staff, setStaff] = useState([]);
  const [email, setEmail] = useState("");
  const [role,  setRole]   = useState("staff");
  const refresh = async () => {
    if (!venue) return;
    try {
      const { data } = await axios.get(`${API}/venue/${venue.id}`);
      setStaff(data.staff || []);
    } catch (_) {/* */}
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [venue]);
  const invite = async () => {
    if (!email.trim()) return;
    try {
      await axios.post(`${API}/venue/${venue.id}/staff`, { email, role });
      setEmail("");
      toast.success("Staff added.");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't invite.");
    }
  };
  const remove = async (s) => {
    try {
      await axios.delete(`${API}/venue/${venue.id}/staff/${s.user_id}`);
      refresh();
    } catch (e) { toast.error("Couldn't remove."); }
  };
  if (loading) return <Shell venue={null} title="Loading…"><div /></Shell>;
  return (
    <Shell venue={venue} title="Settings">
      <Card className="p-6 space-y-4">
        <div className="font-display font-bold text-xl tracking-display-tight">Profile</div>
        <Field label="Name" value={venue?.name} />
        <Field label="Address" value={venue?.address} />
        <Field label="Phone" value={venue?.phone} />
        <Field label="Website" value={venue?.website} />
      </Card>
      <Card className="p-6 space-y-4">
        <div className="font-display font-bold text-xl tracking-display-tight">Staff</div>
        <div className="space-y-2" data-testid="venue-staff-list">
          {staff.map((s) => (
            <div key={s.user_id}
                  className="flex items-center justify-between px-4 py-3 rounded-xl bg-white/[0.03]"
                  data-testid={`venue-staff-row-${s.user_id}`}>
              <div>
                <div className="font-display font-bold text-sm">{s.name}</div>
                <div className="text-xs text-text-secondary font-mono uppercase">
                  {s.role} · {s.email}
                </div>
              </div>
              {s.role !== "owner" && (
                <button className="text-text-secondary hover:text-accent-magenta"
                              onClick={() => remove(s)}
                              data-testid={`venue-staff-remove-${s.user_id}`}>
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2 pt-2 border-t border-white/[0.06]">
          <input value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="invitee@example.com"
                    className="flex-1 px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10]
                                      outline-none text-sm"
                    data-testid="venue-staff-email" />
          <select value={role} onChange={(e) => setRole(e.target.value)}
                      className="px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10] text-sm">
            <option value="staff">staff</option>
            <option value="manager">manager</option>
          </select>
          <Button variant="primary" onClick={invite} data-testid="venue-staff-add">
            <Plus size={12} /> Add
          </Button>
        </div>
      </Card>
    </Shell>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
        {label}
      </div>
      <div className="text-base mt-1">{value || "—"}</div>
    </div>
  );
}

// ─── /venue/onboard — create venue ─────────────────────────────────
export function VenueOnboard() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", address: "", market: "dubai" });
  const submit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/venue`, form);
      toast.success("Venue created.");
      navigate("/venue", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't create venue.");
    }
  };
  return (
    <div className="min-h-screen px-6 pt-10 pb-24">
      <form onSubmit={submit} className="max-w-xl mx-auto space-y-6"
              data-testid="venue-onboard">
        <h1 className="font-display font-bold text-4xl tracking-display-tight">
          Become a <span className="text-accent-magenta">FUUSIC venue</span>.
        </h1>
        <p className="text-text-secondary text-sm">
          Hook up a TV, host live trivia, push tonight's specials to every phone
          in your room.  Takes 60 seconds.
        </p>
        <input placeholder="Venue name" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-4 py-3 rounded-2xl bg-bg-glass border border-white/[0.10]"
                  data-testid="venue-onboard-name" required />
        <input placeholder="Address" value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                  className="w-full px-4 py-3 rounded-2xl bg-bg-glass border border-white/[0.10]"
                  data-testid="venue-onboard-address" />
        <Button variant="primary" type="submit" data-testid="venue-onboard-submit">
          Create venue
        </Button>
      </form>
    </div>
  );
}
