// Profile page — view + edit preferences, sign out, redo onboarding.

import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, LogOut, RefreshCw, Save, Loader2, Check, Shield, Crown, ExternalLink,
  Gamepad2, BarChart3, BadgeCheck, Newspaper, Share2, ChevronRight,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API, useAuth } from "./AuthContext";
import BigFmBrand from "@/components/BigFmBrand";

const LANGUAGES = ["hindi","punjabi","english","bollywood","tamil","arabic","malayalam","telugu"];
const GENRES = ["bollywood","hip_hop","pop","electronic","retro","indie","sufi","ghazal","devotional","rock","punjabi_pop","arabic_pop"];
const ERAS = ["80s","90s","2000s","2010s","2020s"];
const MOODS = ["energetic","chill","romantic","party","uplifting","melancholy","devotional","nostalgic"];
const ACTIVITIES = ["morning_commute","workday_focus","lunch_break","evening_commute","dinner","late_night_drive","workout","party","devotional_time"];
const DUBAI_AREAS = ["Karama","Bur Dubai","Deira","Al Nahda","JLT","Business Bay","Downtown","Marina","Sharjah","Other"];
const HOSTS = [
  { id: "auto",         label: "Auto (smart routing)" },
  { id: "veer_dubai",   label: "Veer — late-night charm" },
  { id: "monika_dubai", label: "Monika — warm & natural" },
  { id: "dj_dubai",     label: "DJ Charlie — club energy" },
];
const nice = (s) => (typeof s === "string" ? s.replace(/_/g, " ") : s);

function Toggleable({ list, selected, onToggle, "data-testid": dt }) {
  return (
    <div className="chip-grid" data-testid={dt}>
      {list.map((id) => {
        const on = selected.includes(id);
        return (
          <button
            key={id}
            type="button"
            className={`chip-pill ${on ? "is-on" : ""}`}
            onClick={() => onToggle(id)}
            data-testid={`${dt}-${id}`}
            aria-pressed={on}
          >
            {on && <Check size={14} />}
            <span>{nice(id)}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function Profile() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [pv, setPv] = useState(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    if (user?.preference_vector) {
      setPv({ ...user.preference_vector });
    }
  }, [user]);

  if (!user) return null;
  if (!pv) {
    return (
      <div className="auth-loading"><Loader2 className="spin" size={28} /></div>
    );
  }

  const toggle = (key) => (id) => {
    setPv((p) => {
      const arr = p[key] || [];
      return { ...p, [key]: arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id] };
    });
  };

  const save = async () => {
    if (saving) return;
    if (pv.languages.length < 1)   return toast.warning("Pick at least 1 language");
    if (pv.genres.length < 2)      return toast.warning("Pick at least 2 genres");
    if (pv.eras.length < 1)        return toast.warning("Pick at least 1 era");
    if (pv.moods.length < 2)       return toast.warning("Pick at least 2 moods");
    if (pv.activities.length < 1)  return toast.warning("Pick at least 1 activity");
    setSaving(true);
    try {
      await axios.post(`${API}/users/preferences`, pv);
      await refresh();
      toast.success("Preferences updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const redoOnboarding = async () => {
    setResetting(true);
    try {
      await axios.post(`${API}/users/onboarding/reset`);
      await refresh();
      navigate("/onboarding");
    } catch (e) {
      toast.error("Could not reset");
    } finally {
      setResetting(false);
    }
  };

  const doLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="profile-shell" data-testid="profile-page">
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="profile-head">
        <Link to="/" className="back-link mono" data-testid="profile-back-link">
          <ArrowLeft size={14} /> BACK TO RADIO
        </Link>
        <div className="auth-brand">
          <span className="brand-dot" />
          <span className="brand-name"><BigFmBrand variant="inline" testId="profile-brand"/></span>
        </div>
      </header>

      <section className="profile-id-card" data-testid="profile-id-card">
        <div className="profile-avatar">
          {user.picture ? (
            <img src={user.picture} alt={user.name} />
          ) : (
            <span className="profile-initials">{user.name.slice(0, 1).toUpperCase()}</span>
          )}
        </div>
        <div className="profile-meta">
          <div className="profile-name" data-testid="profile-name">{user.name}</div>
          <div className="profile-email mono" data-testid="profile-email">{user.email}</div>
          <div className="profile-tags">
            <span className="profile-tag mono">{user.auth_provider.toUpperCase()}</span>
            {user.role === "admin" && (
              <span className="profile-tag admin-tag mono" data-testid="profile-admin-tag">
                <Shield size={11} /> ADMIN
              </span>
            )}
            {user.is_premium && (
              <span className="profile-tag vip-tag mono" data-testid="profile-vip-tag">
                <Crown size={11} /> VIP · {user.premium_tier?.toUpperCase()}
              </span>
            )}
          </div>
        </div>
        <div className="profile-actions">
          <button type="button" className="ghost-btn" onClick={redoOnboarding}
                  disabled={resetting} data-testid="redo-onboarding-btn">
            {resetting ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
            <span>Re-do onboarding</span>
          </button>
          <button type="button" className="ghost-btn danger" onClick={doLogout}
                  data-testid="signout-btn">
            <LogOut size={14} /> <span>Sign out</span>
          </button>
        </div>
      </section>

      <section className="pref-block" data-testid="pref-languages-block">
        <h2 className="pref-title">Languages</h2>
        <Toggleable list={LANGUAGES} selected={pv.languages} onToggle={toggle("languages")}
                    data-testid="pref-languages" />
      </section>

      {/* Phase 3 — Subscription tile (anchor #billing for menu links) */}
      <section
        id="billing"
        className={`pref-block billing-tile ${user.is_premium ? "is-premium" : ""}`}
        data-testid="billing-tile"
      >
        <h2 className="pref-title">
          {user.is_premium ? "Your Premium subscription" : "Subscription"}
        </h2>
        {user.is_premium ? (
          <div className="billing-active">
            <div className="billing-row">
              <span className="mono dim">PLAN</span>
              <span data-testid="billing-plan-name">FUUSIC Premium · Annual</span>
            </div>
            <div className="billing-row">
              <span className="mono dim">STATUS</span>
              <span className="billing-status-active" data-testid="billing-plan-status">
                {user.subscription_status?.toUpperCase() || "ACTIVE"}
              </span>
            </div>
            <div className="billing-row">
              <span className="mono dim">REWARD MULTIPLIER</span>
              <span data-testid="billing-multiplier">{user.reward_multiplier}× (Phase 4+)</span>
            </div>
            {user.subscription_period_end && (
              <div className="billing-row">
                <span className="mono dim">RENEWS / EXPIRES</span>
                <span data-testid="billing-period-end">
                  {new Date(user.subscription_period_end).toLocaleDateString()}
                </span>
              </div>
            )}
            {user.cancel_at_period_end && (
              <div className="billing-cancel-warning mono" data-testid="billing-cancel-warning">
                CANCELLATION SCHEDULED — premium continues until period end
              </div>
            )}
          </div>
        ) : (
          <div className="billing-upsell">
            <p>
              You're on the free tier. 1 skip/hr, standard channels, no VIP.
            </p>
            <Link
              to="/pricing"
              className="billing-cta mono"
              data-testid="profile-go-premium-btn"
            >
              <Crown size={14} /> GO PREMIUM · $12/YR <ExternalLink size={11} />
            </Link>
          </div>
        )}
      </section>

      {/* Phase 42-B-redux — Ad Preferences */}
      <AdPreferencesSection />

      <section className="pref-block" data-testid="pref-genres-block">
        <h2 className="pref-title">Genres</h2>
        <Toggleable list={GENRES} selected={pv.genres} onToggle={toggle("genres")}
                    data-testid="pref-genres" />
      </section>

      <section className="pref-block">
        <h2 className="pref-title">Eras</h2>
        <Toggleable list={ERAS} selected={pv.eras} onToggle={toggle("eras")}
                    data-testid="pref-eras" />
      </section>

      <section className="pref-block">
        <h2 className="pref-title">Moods</h2>
        <Toggleable list={MOODS} selected={pv.moods} onToggle={toggle("moods")}
                    data-testid="pref-moods" />
      </section>

      <section className="pref-block">
        <h2 className="pref-title">When you listen</h2>
        <Toggleable list={ACTIVITIES} selected={pv.activities} onToggle={toggle("activities")}
                    data-testid="pref-activities" />
      </section>

      <section className="pref-block">
        <h2 className="pref-title">Home area</h2>
        <div className="area-grid">
          {DUBAI_AREAS.map((a) => (
            <button
              key={a}
              type="button"
              className={`area-card ${pv.home_area === a ? "is-on" : ""}`}
              onClick={() => setPv((p) => ({ ...p, home_area: a }))}
              data-testid={`pref-area-${a.toLowerCase().replace(/ /g, "-")}`}
            >
              {pv.home_area === a && <Check size={14} />}
              <span>{a}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="pref-block">
        <h2 className="pref-title">RJ personality</h2>
        <div className="host-grid" data-testid="pref-hosts">
          {HOSTS.map((h) => (
            <button
              key={h.id}
              type="button"
              className={`host-card ${pv.host_personality === h.id ? "is-on" : ""}`}
              onClick={() => setPv((p) => ({ ...p, host_personality: h.id }))}
              data-testid={`pref-host-${h.id}`}
            >
              {pv.host_personality === h.id && <Check size={14} />}
              <span>{h.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="pref-block">
        <h2 className="pref-title">Explicit content</h2>
        <label className="big-toggle">
          <input
            type="checkbox"
            checked={pv.explicit_ok}
            onChange={(e) => setPv((p) => ({ ...p, explicit_ok: e.target.checked }))}
            data-testid="pref-explicit-checkbox"
          />
          <span className="toggle-track" />
          <span className="toggle-label">
            {pv.explicit_ok ? "Explicit ON" : "Explicit OFF"}
          </span>
        </label>
      </section>

      {/* Phase 15d.2 — bottom-of-account dashboard. 5 stacked cards that
            give the listener at-a-glance utility (games, stats, passport,
            local now, refer a friend) without leaving Account. Wires to
            existing routes only — no new endpoints required. */}
      <section className="pref-block account-cards-stack" data-testid="account-bottom-cards">
        <h2 className="pref-title">For you</h2>
        <div className="account-cards-grid">
          <Link to="/play" className="account-card" data-testid="account-card-games">
            <div className="ac-icon"><Gamepad2 size={18} /></div>
            <div className="ac-body">
              <div className="ac-eyebrow mono">FEATURED GAMES</div>
              <div className="ac-title">Karak Quiz · Spin · Pick</div>
              <div className="ac-meta">Play tonight to win karak, vouchers, tickets.</div>
            </div>
            <ChevronRight size={16} className="ac-chev" />
          </Link>

          <Link to="/passport" className="account-card" data-testid="account-card-stats">
            <div className="ac-icon"><BarChart3 size={18} /></div>
            <div className="ac-body">
              <div className="ac-eyebrow mono">LISTENING STATS</div>
              <div className="ac-title">
                {user?.preference_vector?.genres?.length || 0} genres ·{" "}
                {user?.preference_vector?.languages?.length || 0} languages
              </div>
              <div className="ac-meta">Your taste graph — built from every play.</div>
            </div>
            <ChevronRight size={16} className="ac-chev" />
          </Link>

          <Link to="/passport" className="account-card" data-testid="account-card-passport">
            <div className="ac-icon"><BadgeCheck size={18} /></div>
            <div className="ac-body">
              <div className="ac-eyebrow mono">SOCIAL PASSPORT</div>
              <div className="ac-title">Level up your listener identity</div>
              <div className="ac-meta">Earn badges, climb city leaderboards.</div>
            </div>
            <ChevronRight size={16} className="ac-chev" />
          </Link>

          <Link to="/" className="account-card" data-testid="account-card-local">
            <div className="ac-icon"><Newspaper size={18} /></div>
            <div className="ac-body">
              <div className="ac-eyebrow mono">LOCAL NOW</div>
              <div className="ac-title">Around your city, right now</div>
              <div className="ac-meta">Offers, headlines, and what's on tonight.</div>
            </div>
            <ChevronRight size={16} className="ac-chev" />
          </Link>

          <button
            type="button"
            className="account-card account-card-cta"
            data-testid="account-card-refer"
            onClick={async () => {
              const url = `${window.location.origin}/?ref=${user?.id || ""}`;
              try {
                if (navigator.share) {
                  await navigator.share({ title: "Join me on FUUSIC", url });
                } else {
                  await navigator.clipboard.writeText(url);
                  toast.success("Invite link copied");
                }
              } catch (_e) { /* user cancelled */ }
            }}
          >
            <div className="ac-icon"><Share2 size={18} /></div>
            <div className="ac-body">
              <div className="ac-eyebrow mono">REFER A FRIEND</div>
              <div className="ac-title">Share FUUSIC, earn BigPoints</div>
              <div className="ac-meta">Both of you get bonus coins on signup.</div>
            </div>
            <ChevronRight size={16} className="ac-chev" />
          </button>
        </div>
      </section>

      <div className="profile-save-row">
        <button type="button" className="save-btn" onClick={save} disabled={saving}
                data-testid="save-prefs-btn">
          {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
          <span>SAVE PREFERENCES</span>
        </button>
      </div>
    </div>
  );
}

// ─────────────── Phase 42-B-redux — Ad Preferences ─────────────────
function AdPreferencesSection() {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/users/me/ad-settings`,
                                                            { withCredentials: true });
        if (!cancelled) setSettings(r.data);
      } catch (_e) { /* swallow */ }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!settings) {
    return (
      <section className="pref-block" data-testid="ad-prefs-loading">
        <h2 className="pref-title">Ad Preferences</h2>
        <div style={{ color: "#9aa3af", fontSize: 13 }}>Loading…</div>
      </section>
    );
  }

  const onToggle = async () => {
    if (!settings.is_premium) {
      toast.error("Premium plan required", {
        description: "Upgrade to hide platform ads on imported stations.",
      });
      return;
    }
    setSaving(true);
    const next = !settings.ad_free_enabled;
    try {
      const r = await axios.patch(`${API}/users/me/ad-settings`,
        { ad_free_enabled: next, acknowledge_disclosure: true },
        { withCredentials: true });
      setSettings((s) => ({
        ...s,
        ad_free_enabled: r.data.ad_free_enabled,
        disclosure_acknowledged_at: r.data.disclosure_acknowledged_at,
      }));
      toast.success(next ? "Ad-free mode enabled" : "Platform ads turned on");
    } catch (_e) {
      toast.error("Couldn't update — please retry.");
    } finally { setSaving(false); }
  };

  return (
    <section className="pref-block" data-testid="ad-prefs-block">
      <h2 className="pref-title">Ad Preferences</h2>

      <div data-testid="ad-prefs-tier-row"
                style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 14, paddingBottom: 12,
                                  borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <span className="mono dim" style={{ fontSize: 11 }}>SUBSCRIPTION</span>
        <span data-testid="ad-prefs-tier-value"
                    style={{ fontSize: 13, fontWeight: 600,
                                      color: settings.is_premium ? "#00d9ff" : "#9aa3af" }}>
          {settings.is_premium ? "Premium" : "Free"}
        </span>
      </div>

      <div data-testid="ad-prefs-toggle-row"
                style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 14 }}>
        <div style={{ flexGrow: 1, paddingRight: 16 }}>
          <div style={{ fontSize: 14, color: "#fff", marginBottom: 4 }}>
            Hide platform ads
          </div>
          <div style={{ fontSize: 12, color: "#9aa3af" }}>
            Pre-roll ads on imported live radio stations.
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={settings.ad_free_enabled}
          onClick={onToggle}
          disabled={saving || !settings.is_premium}
          data-testid="ad-prefs-toggle"
          data-enabled={settings.ad_free_enabled}
          style={{
            width: 44, height: 24, borderRadius: 12,
            background: settings.ad_free_enabled ? "#00d9ff" : "rgba(255,255,255,0.10)",
            border: "1px solid rgba(255,255,255,0.10)",
            position: "relative", cursor: settings.is_premium ? "pointer" : "not-allowed",
            transition: "background 150ms ease", flexShrink: 0,
            opacity: settings.is_premium ? 1 : 0.5,
          }}>
          <span style={{
            position: "absolute", top: 1, left: settings.ad_free_enabled ? 21 : 1,
            width: 20, height: 20, borderRadius: "50%",
            background: settings.ad_free_enabled ? "#0a1828" : "#fff",
            transition: "left 150ms ease",
          }} />
        </button>
      </div>

      <div data-testid="ad-prefs-disclosure"
                style={{ fontSize: 12, color: "#9aa3af", lineHeight: 1.5,
                                  padding: "10px 12px", borderRadius: 8,
                                  background: "rgba(255,255,255,0.03)",
                                  border: "1px solid rgba(255,255,255,0.06)" }}>
        {settings.disclosure_text || (
          "Premium removes FUUSIC platform ads. Some third-party live "
          + "stations may still include ads within their original "
          + "broadcast stream."
        )}
      </div>

      {!settings.is_premium && (
        <Link to="/pricing" data-testid="ad-prefs-upgrade-cta"
                    style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                      marginTop: 12, color: "#ffc857", fontSize: 12,
                                      textDecoration: "none" }}>
          <Crown size={12} /> Upgrade to Premium →
        </Link>
      )}
    </section>
  );
}
