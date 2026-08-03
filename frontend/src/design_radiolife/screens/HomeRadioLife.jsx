// Phase R.1 — Home (RadioLife).  Points card + Continue Listening +
// Nearby Deals + brief tier callout.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Play, ChevronRight, Radio } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import { extractTier, RLCard } from "../DesignSystem";
import PointsBalanceCard from "../components/PointsBalanceCard";
import NearbyDealCard from "../components/NearbyDealCard";
import { coordsForMarket } from "../utils/market_coords";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function HomeRadioLife() {
  const { user } = useAuth();
  const market = useGeoStore((s) => s.market);
  const city = useGeoStore((s) => s.city);
  const [balance, setBalance] = useState(0);
  const [tier, setTier] = useState({ name: "Listener", nextName: "Regular",
                                                progress: 0, threshold: 100, points: 0 });
  const [featured, setFeatured] = useState(null);
  const [deals, setDeals] = useState([]);
  const [dealsLoading, setDealsLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const [ptsR, psR, chR] = await Promise.allSettled([
          axios.get(`${API}/me/points`, { withCredentials: true }),
          axios.get(`${API}/passport/me`, { withCredentials: true }),
          axios.get(`${API}/channels`),
        ]);
        if (ptsR.status === "fulfilled") setBalance(ptsR.value.data?.balance || 0);
        if (psR.status === "fulfilled") setTier(extractTier(psR.value.data));
        if (chR.status === "fulfilled") {
          setFeatured((chR.value.data?.channels || [])[0] || null);
        }
      } catch (_) { /* silent, empty states render */ }
      // Nearby deals via city coords + public businesses + first offer per biz.
      setDealsLoading(true);
      const coords = coordsForMarket(market) || { lat: 25.15, lng: 55.25 };
      try {
        const bizR = await axios.get(
          `${API}/public/businesses/nearby?lat=${coords.lat}&lng=${coords.lng}` +
          `&radius_m=30000&limit=8`);
        const bizItems = (bizR.data?.items || []).slice(0, 8);
        const enriched = await Promise.all(bizItems.map(async (biz) => {
          try {
            const off = await axios.get(
              `${API}/public/businesses/${biz.slug}/offers?limit=1`);
            const firstOffer = (off.data?.items || [])[0] || null;
            return { biz, offer: firstOffer };
          } catch {
            return { biz, offer: null };
          }
        }));
        // Only surface businesses that DO have an active offer.
        setDeals(enriched.filter((x) => x.offer));
      } catch (_) {
        setDeals([]);
      } finally {
        setDealsLoading(false);
      }
    })();
  }, [user, market]);

  const handleSave = async (offerId) => {
    try {
      await axios.post(`${API}/commute/v1/save-coupon/${offerId}`, {},
                              { withCredentials: true });
      toast.success("Coupon saved to wallet");
    } catch (e) {
      toast.error("Could not save coupon");
    }
  };

  return (
    <div className="px-4 pt-6 pb-6 space-y-5" data-testid="rl-home-page">
      {/* Greeting */}
      <header>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">
          Hey, {user?.display_name || user?.email?.split("@")[0] || "friend"} 👋
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Around <span className="text-purple-700 font-semibold">{city || "you"}</span>
          {" — "}here&apos;s your afternoon.
        </p>
      </header>

      <PointsBalanceCard balance={balance} tier={tier} />

      {/* Continue listening */}
      {featured && (
        <RLCard className="p-4" data-testid="rl-continue-listening">
          <div className="flex items-center gap-3">
            <div className="w-16 h-16 rounded-2xl overflow-hidden flex-shrink-0 bg-purple-100
                                    flex items-center justify-center relative">
              {featured.thumbnail_url ? (
                <img src={`${BACKEND_URL}${featured.thumbnail_url}`}
                        alt={featured.name}
                        loading="lazy"
                        onError={(e)=>{e.currentTarget.style.display="none";}}
                        className="absolute inset-0 w-full h-full object-cover" />
              ) : (
                <Radio size={26} className="text-purple-500" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-widest text-purple-600">
                Continue listening
              </div>
              <div className="font-bold text-slate-900 truncate">
                {featured.name || featured.slug}
              </div>
              {featured.tagline && (
                <div className="text-[11px] text-slate-500 truncate">{featured.tagline}</div>
              )}
            </div>
            <button
              type="button"
              onClick={() => navigate(`/radio?ch=${encodeURIComponent(featured.slug)}`)}
              data-testid="rl-continue-play-btn"
              className="w-11 h-11 rounded-full flex items-center justify-center
                                text-white shadow-md active:scale-95 transition-transform"
              style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
              <Play size={17} strokeWidth={2.5} fill="currentColor" />
            </button>
          </div>
        </RLCard>
      )}

      {/* Nearby deals */}
      <section data-testid="rl-nearby-deals">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-black tracking-tight text-slate-900">
            Nearby deals
          </h2>
          <Link to="/discover"
                    className="text-[11px] uppercase tracking-widest font-semibold
                                        text-purple-700 flex items-center gap-0.5">
            See all <ChevronRight size={13} />
          </Link>
        </div>
        {dealsLoading ? (
          <RLCard className="p-4 text-sm text-slate-500">Finding deals near you…</RLCard>
        ) : deals.length === 0 ? (
          <RLCard className="p-6 text-center" data-testid="rl-deals-empty">
            <div className="font-semibold text-slate-900">No deals in your area yet</div>
            <div className="text-sm text-slate-500 mt-1">Check back soon — we&apos;re onboarding new spots weekly.</div>
          </RLCard>
        ) : (
          <div className="flex gap-3 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
            {deals.slice(0, 6).map(({ biz, offer }) => (
              <div key={biz.business_id} className="snap-start">
                <NearbyDealCard
                  business={biz}
                  offer={offer}
                  distance_km={typeof biz.distance_m === "number"
                                        ? biz.distance_m / 1000 : null}
                  onSave={handleSave} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Phase SC.2 — Become a Partner card. */}
      <section data-testid="rl-home-merchant-cta"
                    className="mt-6">
        <Link to="/merchant/apply"
                  data-testid="rl-become-partner-link"
                  className="block rounded-3xl p-5 relative overflow-hidden text-white shadow-lg shadow-purple-500/25"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <div className="text-[10px] uppercase tracking-widest font-bold opacity-90">
            For business owners
          </div>
          <div className="mt-1 text-lg font-black tracking-tight">
            Become a BigFM Partner →
          </div>
          <div className="mt-1 text-sm opacity-95">
            List your business, mint coupons, and get on the map.
          </div>
        </Link>
      </section>
    </div>
  );
}
