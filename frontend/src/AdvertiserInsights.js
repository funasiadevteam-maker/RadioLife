// Phase 8c — Top-level advertiser insights page combining tabs:
// Leads, Webhooks, Top campaigns leaderboard.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Webhook, Trophy, Users, Loader2 } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { LeadsPanel, WebhooksPanel, LeaderboardWidget } from "@/AdvertiserPhase8c";
import "./PlayAndWin.css";


export default function AdvertiserInsights() {
  const { user } = useAuth();
  const [tab, setTab] = useState("leaderboard");
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCid, setSelectedCid] = useState(null);
  const [loadingC, setLoadingC] = useState(true);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/games_v2/advertiser/campaigns`)
        .then((r) => {
          const items = r.data?.items || [];
          setCampaigns(items);
          if (items.length > 0) setSelectedCid(items[0].campaign_id);
        })
        .catch(() => {})
        .finally(() => setLoadingC(false));
  }, [user]);

  if (!user) return null;

  return (
    <div className="advgames-wrap" data-testid="advertiser-insights-page">
      <header className="paw-header">
        <div>
          <Link to="/advertiser/games" className="paw-back">
            <ChevronLeft size={14} /> back to campaigns
          </Link>
          <h1>Insights & integrations</h1>
          <p className="sub">Top performers, leads, partner webhooks.</p>
        </div>
      </header>
      <div className="advinsights-tabs" data-testid="advinsights-tabs">
        <button className="advinsights-tab"
                  data-active={tab === "leaderboard"}
                  onClick={() => setTab("leaderboard")}
                  data-testid="tab-leaderboard">
          <Trophy size={13} /> Top campaigns
        </button>
        <button className="advinsights-tab"
                  data-active={tab === "leads"}
                  onClick={() => setTab("leads")}
                  data-testid="tab-leads">
          <Users size={13} /> Leads
        </button>
        <button className="advinsights-tab"
                  data-active={tab === "webhooks"}
                  onClick={() => setTab("webhooks")}
                  data-testid="tab-webhooks">
          <Webhook size={13} /> Webhooks & CRM
        </button>
      </div>
      <div className="advinsights-body">
        {tab === "leaderboard" && <LeaderboardWidget />}
        {tab === "webhooks" && <WebhooksPanel />}
        {tab === "leads" && (
          <div>
            <div className="campaign-picker-row" data-testid="leads-campaign-picker">
              <label className="mono dim">CAMPAIGN</label>
              {loadingC ? <Loader2 size={14} className="spin" />
                : campaigns.length === 0
                ? <span className="dim">No campaigns yet</span>
                : <select className="leads-filter"
                              value={selectedCid || ""}
                              onChange={(e) => setSelectedCid(e.target.value)}
                              data-testid="leads-campaign-select">
                    {campaigns.map((c) => (
                      <option key={c.campaign_id} value={c.campaign_id}>
                        {c.title}
                      </option>
                    ))}
                  </select>}
            </div>
            {selectedCid && <LeadsPanel campaignId={selectedCid} />}
          </div>
        )}
      </div>
    </div>
  );
}
