// Phase 18a — Advertiser shell + 7 subroutes.  Replaces the Phase 4 file.
//   /advertiser                    → redirect to /overview (or /onboard)
//   /advertiser/onboard
//   /advertiser/overview
//   /advertiser/campaigns
//   /advertiser/campaigns/new      (handled by App.js route -> CampaignWizard)
//   /advertiser/campaigns/:id
//   /advertiser/creatives
//   /advertiser/billing
//   /advertiser/settings
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate, Routes, Route, Link, useLocation, Navigate } from "react-router-dom";
import { Loader2, Building2, Sparkles, Wallet, Image, Users, ChevronDown, Megaphone } from "lucide-react";

import AdvertiserOnboard      from "@/advertiser/Onboard";
import AdvertiserOverview     from "@/advertiser/Overview";
import AdvertiserCampaigns    from "@/advertiser/CampaignsList";
import AdvertiserCampaignDetail from "@/advertiser/CampaignDetail";
import AdvertiserCreatives    from "@/advertiser/Creatives";
import AdvertiserBilling      from "@/advertiser/Billing";
import AdvertiserSettings     from "@/advertiser/Settings";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

export default function Advertiser() {
  const [items, setItems]     = useState(null);
  const [active, setActive]   = useState(null);
  const navigate              = useNavigate();
  const loc                   = useLocation();

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/advertiser/me`);
        const list = r.data.items || [];
        setItems(list);
        if (list.length) {
          const stored = localStorage.getItem("bigfm_active_advertiser");
          const found  = list.find((x) => x.advertiser_id === stored);
          setActive((found || list[0]).advertiser_id);
        }
      } catch (e) {
        setItems([]);
      }
    })();
  }, []);

  useEffect(() => {
    if (active) localStorage.setItem("bigfm_active_advertiser", active);
  }, [active]);

  if (items === null) {
    return <div className="min-h-screen flex items-center justify-center text-text-secondary">
      <Loader2 className="animate-spin" size={28} />
    </div>;
  }

  // First-run: kick to /onboard if no advertiser AND not already on onboard.
  if (items.length === 0 && !loc.pathname.includes("onboard")) {
    return <Navigate to="/advertiser/onboard" replace />;
  }

  return (
    <div className="min-h-screen bg-bg-base text-text-primary" data-testid="advertiser-shell">
      <header className="border-b border-white/[0.06] px-6 py-4 flex items-center justify-between sticky top-0 bg-bg-base/90 backdrop-blur z-20">
        <div className="flex items-center gap-3">
          <Building2 size={20} className="text-accent-electric" />
          <h1 className="font-display font-bold text-xl tracking-display-tight">FUUSIC Advertiser</h1>
        </div>
        {items.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              value={active || ""}
              onChange={(e) => setActive(e.target.value)}
              className="bg-white/[0.04] border border-white/[0.10] rounded-lg px-3 py-1.5 text-sm"
              data-testid="advertiser-picker">
              {items.map((x) => (
                <option key={x.advertiser_id} value={x.advertiser_id}>
                  {x.name} · ${(x.account_balance_usd || 0).toFixed(2)}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="text-text-secondary -ml-7 pointer-events-none" />
          </div>
        )}
      </header>

      <div className="grid grid-cols-12 gap-6 max-w-screen-xl mx-auto p-6">
        <nav className="col-span-12 lg:col-span-2 space-y-1" data-testid="advertiser-nav">
          {[
            { to: "/advertiser/overview",    label: "Overview",      icon: Sparkles },
            { to: "/advertiser/campaigns",   label: "Campaigns",   icon: Building2 },
            { to: "/advertiser/banner/buy",  label: "Buy Banner",  icon: Megaphone },
            { to: "/advertiser/banner/campaigns", label: "My Banners", icon: Image },
            { to: "/advertiser/creatives",    label: "Creatives",     icon: Image },
            { to: "/advertiser/billing",         label: "Billing",          icon: Wallet },
            { to: "/advertiser/settings",      label: "Settings",       icon: Users },
          ].map((l) => {
            const Ico = l.icon;
            const on = loc.pathname.startsWith(l.to);
            return (
              <Link key={l.to} to={l.to}
                          data-testid={`nav-${l.label.toLowerCase()}`}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                                ${on ? "bg-accent-electric/[0.10] text-accent-electric"
                                       : "text-text-secondary hover:bg-white/[0.04]"}`}>
                <Ico size={14} /> {l.label}
              </Link>
            );
          })}
        </nav>

        <main className="col-span-12 lg:col-span-10 space-y-6" data-testid="advertiser-main">
          <Routes>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="onboard"            element={<AdvertiserOnboard onCreated={(aid) => { setActive(aid); navigate("/advertiser/overview"); }} />} />
            <Route path="overview"           element={<AdvertiserOverview advertiserId={active} />} />
            <Route path="campaigns"          element={<AdvertiserCampaigns  advertiserId={active} />} />
            <Route path="campaigns/:cid"     element={<AdvertiserCampaignDetail advertiserId={active} />} />
            <Route path="creatives"          element={<AdvertiserCreatives  advertiserId={active} />} />
            <Route path="billing"            element={<AdvertiserBilling     advertiserId={active} />} />
            <Route path="settings"           element={<AdvertiserSettings   advertiserId={active} />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
