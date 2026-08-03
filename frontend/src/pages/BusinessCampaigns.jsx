// Phase I — Business Redemption Portal: campaigns list.
// Lists the advertiser_campaigns rows tagged with this business_id.  The
// "buy ads" CTA hops to /business/ads/buy which mints a buy-session and
// deep-links into the existing /advertiser flow.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Megaphone, Loader2, Plus, ChevronRight } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { API } from "@/AuthContext";

const STATUS_TONES = {
  live: "emerald", running: "emerald", active: "emerald",
  paused: "neutral", scheduled: "electric", draft: "neutral",
  pending: "gold", rejected: "danger", ended: "neutral",
};

export default function BusinessCampaigns() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/business/campaigns`);
        if (!cancelled) setItems(r.data.items || []);
      } catch (e) {
        if (e?.response?.status === 403) {
          navigate("/business/register", { replace: true });
          return;
        }
        toast.error(e?.response?.data?.detail || "Couldn't load campaigns.");
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  return (
    <div data-testid="business-campaigns-page"
            className="min-h-screen bg-bg-base px-4 py-8 pb-24
                                      max-w-4xl mx-auto space-y-5">
      <Toaster richColors theme="dark" position="bottom-right" />
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2">
            <Megaphone size={11} /> Your ad spend
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl
                                  tracking-display-tight">
            <span className="text-accent-magenta">Campaigns</span>
          </h1>
        </div>
        <div className="flex gap-2">
          <Link to="/business" className="text-xs text-accent-electric
                                              hover:underline self-center"
                  data-testid="business-campaigns-back">
            ← Dashboard
          </Link>
          <Button variant="magenta"
                          onClick={() => navigate("/business/ads/buy")}
                          data-testid="business-campaigns-new">
            <Plus size={14} /> Buy ad placement
          </Button>
        </div>
      </header>

      {loading && (
        <Card className="p-8 text-center text-text-secondary"
                    data-testid="business-campaigns-loading">
          <Loader2 size={22} className="animate-spin inline" />
        </Card>
      )}

      {!loading && items.length === 0 && (
        <Card className="p-8 text-center space-y-3" data-testid="business-campaigns-empty">
          <Megaphone size={28} className="mx-auto text-accent-magenta/60" />
          <h3 className="font-display font-bold text-lg">No campaigns yet</h3>
          <p className="text-sm text-text-secondary max-w-sm mx-auto">
            Reach the listeners who already love your neighbourhood.
            Pick a placement, set a budget, and launch in minutes.
          </p>
          <Button variant="magenta"
                          onClick={() => navigate("/business/ads/buy")}
                          data-testid="business-campaigns-empty-cta">
            <Plus size={14} /> Buy your first placement
          </Button>
        </Card>
      )}

      {!loading && items.length > 0 && (
        <div className="space-y-2" data-testid="business-campaigns-list">
          {items.map((c) => {
            const tone = STATUS_TONES[String(c.status).toLowerCase()] || "neutral";
            return (
              <Card key={c._id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center
                                    gap-3 sm:gap-4"
                    data-testid={`business-campaign-${c._id}`}>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm truncate">
                    {c.name || "Untitled campaign"}
                  </div>
                  <div className="text-[11px] text-text-secondary font-mono mt-0.5">
                    {c._id} · {c.campaign_type || "—"}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {c.budget != null && (
                    <span className="text-sm font-semibold text-accent-electric">
                      ${Number(c.budget).toLocaleString()}
                    </span>
                  )}
                  <Chip tone={tone} data-testid={`business-campaign-${c._id}-status`}>
                    {c.status || "—"}
                  </Chip>
                  <ChevronRight size={14} className="text-text-secondary" />
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
