import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Trophy, MapPin, ChevronDown, User as UserIcon,
            Clock, Award, TicketCheck, Ticket, Car, Sparkles } from "lucide-react";
import "@/Passport.css";
import "@/Leaderboards.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const METRICS = [
  {key: "listening_minutes_7d",   label: "Listening (7d)",   icon: Clock,
    suffix: " min"},
  {key: "badges_earned_7d",       label: "Badges (7d)",      icon: Award,
    suffix: ""},
  {key: "ambassador_points_alltime", label: "Ambassador",   icon: Sparkles,
    suffix: " pts"},
  {key: "referrals_engaged_30d",  label: "Referrals (30d)",  icon: UserIcon,
    suffix: ""},
  {key: "coupons_redeemed_30d",   label: "Coupons (30d)",    icon: Ticket,
    suffix: ""},
  {key: "commutes_completed_30d", label: "Commutes (30d)",   icon: Car,
    suffix: ""},
];


function Row({ row, isMe }) {
  const initial = (row.display_name || "?").charAt(0).toUpperCase();
  const anon = !!row.is_anonymous;
  const TierColors = ["#ffd75e", "#cfd6df", "#d29c6c"];
  const rankColor = row.rank <= 3 ? TierColors[row.rank - 1] : "#6c7888";
  const content = (
    <>
      <div className="lb-rank" style={{color: rankColor}}>
        #{row.rank}
      </div>
      <div className={"lb-avatar" + (anon ? " is-anon" : "")}>
        {!anon && row.avatar_url
            ? <img src={row.avatar_url} alt=""/>
            : <span>{anon ? "?" : initial}</span>}
      </div>
      <div className="lb-meta">
        <div className={"lb-name" + (anon ? " is-anon" : "")}>
          {row.display_name}
        </div>
        {row.handle && !anon && (
          <div className="lb-handle">@{row.handle}</div>
        )}
      </div>
      <div className="lb-value">{row.value.toLocaleString()}</div>
    </>
  );
  if (anon || !row.user_id) {
    return (
      <div className={"lb-row" + (anon ? " is-anon-row" : "")
                          + (isMe ? " is-me" : "")}
            data-testid={`lb-row-${row.rank}`}>
        {content}
      </div>
    );
  }
  return (
    <a className={"lb-row is-link" + (isMe ? " is-me" : "")}
        href={`/passport/${row.user_id}`}
        data-testid={`lb-row-${row.rank}`}>
      {content}
    </a>
  );
}


export default function Leaderboards() {
  const { city: cityParam } = useParams();
  const nav = useNavigate();
  const [cities, setCities] = useState([]);
  const [city, setCity] = useState(cityParam || "Dubai");
  const [metric, setMetric] = useState("ambassador_points_alltime");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cityPickerOpen, setCityPickerOpen] = useState(false);

  const loadCities = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/leaderboards/cities`);
      setCities(r.data.items || []);
    } catch (_e) {/* non-fatal */}
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/leaderboards/${encodeURIComponent(city)}?metric=${metric}`);
      setData(r.data);
    } catch (e) {
      toast.error("Could not load leaderboard");
    } finally {
      setLoading(false);
    }
  }, [city, metric]);

  useEffect(() => { loadCities(); }, [loadCities]);
  useEffect(() => { load(); }, [load]);

  const cityClick = (c) => {
    setCity(c);
    setCityPickerOpen(false);
    nav(`/leaderboards/${encodeURIComponent(c)}`, { replace: true });
  };
  const myMe = data?.your_rank
                      ? {rank: data.your_rank, value: data.your_value || 0,
                          display_name: "You", is_anonymous: false}
                      : null;
  const myInTop = data?.top_n?.some(r => r.rank === data?.your_rank
                                                          && r.value === data?.your_value);

  return (
    <div className="lb-page" data-testid="lb-page">
      <div className="lb-header">
        <div className="lb-title">
          <Trophy size={20}/> City Leaderboards
        </div>
        <button className="lb-city-picker"
                  data-testid="lb-city-picker"
                  onClick={() => setCityPickerOpen(o => !o)}>
          <MapPin size={14}/> {city}
          <ChevronDown size={12}/>
        </button>
        {cityPickerOpen && (
          <div className="lb-city-menu">
            {cities.length === 0 && (
              <div className="lb-city-empty">No cities online yet.</div>
            )}
            {cities.map(c => (
              <button key={c.city}
                        data-testid={`lb-city-opt-${c.city}`}
                        onClick={() => cityClick(c.city)}>
                {c.city}
                <span className="lb-city-pop">{c.active_user_count}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <nav className="lb-tabs" data-testid="lb-metric-tabs">
        {METRICS.map(m => {
          const Icon = m.icon;
          return (
            <button key={m.key}
                      className={"lb-tab" + (metric === m.key ? " is-active" : "")}
                      data-testid={`lb-tab-${m.key}`}
                      onClick={() => setMetric(m.key)}>
              <Icon size={12}/> {m.label}
            </button>
          );
        })}
      </nav>

      {loading && (
        <div className="psp-loading" data-testid="lb-loading">
          Loading {city} {metric}…
        </div>
      )}

      {!loading && data && !data.available && (
        <div className="psp-empty">
          <Trophy size={28}/>
          <div className="psp-empty-title">No leaderboard yet</div>
          <div className="psp-empty-sub">
            {city} needs at least a few active listeners for a board to populate.
          </div>
        </div>
      )}

      {!loading && data && data.available && (
        <>
          {myMe && !myInTop && data.your_rank > 50 && (
            <div className="lb-your-rank-pin" data-testid="lb-your-rank-pin">
              You&apos;re ranked <strong>#{data.your_rank}</strong> ({data.your_value})
              — keep going!
            </div>
          )}
          <div className="lb-rows">
            {(data.top_n || []).slice(0, 50).map(r => (
              <Row key={`${r.rank}-${r.user_id || r.display_name}`}
                    row={r}
                    isMe={data?.your_rank === r.rank}/>
            ))}
            {(data.top_n || []).length === 0 && (
              <div className="psp-empty-small">No entries yet.</div>
            )}
          </div>
          <div className="lb-meta-line">
            {data.active_user_count} active listeners ·
            last computed {data.computed_at
              ? new Date(data.computed_at).toLocaleString()
              : "never"}
          </div>
        </>
      )}
    </div>
  );
}
