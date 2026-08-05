// Phase I — Business Redemption Portal: ad buy entry point.
// POSTs /api/business/campaigns/buy/start to mint a buy_session row,
// then redirects to the existing /advertiser flow with the session as
// a query param so the advertiser dashboard can pre-fill the business
// context.  No POS integrations are needed; this just bridges the two
// surfaces.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Megaphone, Loader2, MapPin, Headphones, BarChart3,
          ChevronRight } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { API } from "@/AuthContext";

const PLACEMENTS = [
  { id: "miniplayer",            icon: Headphones,
      title: "MiniPlayer",         tag: "Every active listener",
      blurb: "Persistent banner above the player. Highest visibility, " +
                  "shown to every logged-in listener in your market." },
  { id: "commute_map",          icon: MapPin,
      title: "Commute map",      tag: "Lunch & commute peaks",
      blurb: "Banner on the maps surface. Targeted by route patterns " +
                  "and proximity to your storefront." },
  { id: "predict_win_list", icon: BarChart3,
      title: "Predict & Win", tag: "High-engagement game traffic",
      blurb: "Banner on the daily prediction feed. Listeners who play " +
                  "convert higher on local offers." },
];

export default function BusinessAdsBuy() {
  const navigate = useNavigate();
  const [biz, setBiz] = useState(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/business/me`);
        if (!cancelled) setBiz(r.data);
      } catch (e) {
        if (e?.response?.status === 403) {
          navigate("/business/register", { replace: true });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  const startBuy = async () => {
    if (starting) return;
    setStarting(true);
    try {
      const r = await axios.post(
        `${API}/business/campaigns/buy/start`, {});
      if (r.data?.deep_link) {
        navigate(r.data.deep_link);
      } else {
        navigate("/advertiser/banner/buy");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail
                          || "Couldn't start the ad-buy flow.");
    } finally { setStarting(false); }
  };

  return (
    <div data-testid="business-ads-buy-page"
            className="min-h-screen bg-bg-base px-4 py-8 pb-24
                                      max-w-3xl mx-auto space-y-6">
      <Toaster richColors theme="dark" position="bottom-right" />

      <header className="space-y-2">
        <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary flex items-center gap-2">
          <Megaphone size={11} /> Buy ad inventory
        </div>
        <h1 className="font-display font-bold text-4xl sm:text-5xl
                                tracking-display-tight">
          Reach <span className="text-accent-magenta">your neighbourhood</span>.
        </h1>
        <p className="text-text-secondary text-sm max-w-xl">
          Direct-sold placements across RadioLife&apos;s listening surfaces.
          Budget, creative, and targeting are configured in the advertiser
          console — this just hands the keys over.
        </p>
        {biz && (
          <Chip tone="gold" data-testid="business-ads-biz-chip">
            Buying as · {biz.name}
          </Chip>
        )}
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3"
              data-testid="business-ads-placement-grid">
        {PLACEMENTS.map((p) => (
          <Card key={p.id} className="p-4 space-y-3"
                      data-testid={`business-ads-placement-${p.id}`}>
            <div className="w-10 h-10 rounded-token-md grid place-items-center
                                    bg-accent-magenta/15 text-accent-magenta">
              <p.icon size={18} />
            </div>
            <div>
              <h3 className="font-display font-bold text-base
                                          tracking-display-tight">{p.title}</h3>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary mt-0.5">{p.tag}</div>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">{p.blurb}</p>
          </Card>
        ))}
      </div>

      <Card className="p-6 sm:p-8 text-center space-y-4 border-accent-magenta/30"
                  data-testid="business-ads-cta-card">
        <h2 className="font-display font-bold text-2xl tracking-display-tight">
          Ready to launch?
        </h2>
        <p className="text-sm text-text-secondary max-w-md mx-auto">
          We&apos;ll open the advertiser console with your business pre-filled.
          You&apos;ll pick a placement, set budget + dates, upload creative,
          and submit for review.
        </p>
        <Button variant="magenta" onClick={startBuy} disabled={starting}
                        data-testid="business-ads-start-buy">
          {starting
            ? <><Loader2 size={14} className="animate-spin" /> Opening console…</>
            : <>Continue to advertiser console <ChevronRight size={14} /></>}
        </Button>
        <div className="text-xs">
          <Link to="/business/campaigns"
                  className="text-text-secondary hover:text-white"
                  data-testid="business-ads-view-existing">
            See my existing campaigns →
          </Link>
        </div>
      </Card>

      <div className="text-center">
        <Link to="/business" className="text-xs text-accent-electric hover:underline"
                data-testid="business-ads-back">
          ← Back to dashboard
        </Link>
      </div>
    </div>
  );
}
