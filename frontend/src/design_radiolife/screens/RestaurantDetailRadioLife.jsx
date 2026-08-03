// Phase R.1 — Restaurant Detail.  Public business + offers, with Get Deal +
// Pay with App CTAs.
import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, Star, MapPin, Sparkles, Ticket, CreditCard,
              Utensils, Clock } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, RLButton, RLBadge } from "../DesignSystem";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function RestaurantDetailRadioLife() {
  // Overlay is mounted outside <Routes>, so useParams() returns {}.
  // Parse the slug from the pathname directly.
  const { pathname } = useLocation();
  const slug = pathname.startsWith("/business/")
    ? decodeURIComponent(pathname.slice("/business/".length).split("/")[0])
    : "";
  const navigate = useNavigate();
  const [biz, setBiz] = useState(null);
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [bR, oR] = await Promise.allSettled([
          axios.get(`${API}/public/businesses/${slug}`),
          axios.get(`${API}/public/businesses/${slug}/offers?limit=6`),
        ]);
        if (bR.status === "fulfilled") setBiz(bR.value.data);
        if (oR.status === "fulfilled") setOffers(oR.value.data?.items || []);
      } catch (_) { setBiz(null); }
      finally { setLoading(false); }
    })();
  }, [slug]);

  const handleGetDeal = async () => {
    const topOffer = offers[0];
    if (!topOffer) { toast.error("No deals available"); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/commute/v1/save-coupon/${topOffer.offer_id}`, {},
                              { withCredentials: true });
      toast.success("Coupon saved · check your wallet");
      navigate("/wallet");
    } catch (e) {
      toast.error("Couldn't save coupon");
    } finally { setSaving(false); }
  };

  const gmapsStatic = biz?.lat && biz?.lng && process.env.REACT_APP_GOOGLE_MAPS_API_KEY
    ? `https://maps.googleapis.com/maps/api/staticmap?center=${biz.lat},${biz.lng}` +
      `&zoom=15&size=560x180&scale=2&maptype=roadmap` +
      `&markers=color:0xA020F0%7C${biz.lat},${biz.lng}` +
      `&key=${process.env.REACT_APP_GOOGLE_MAPS_API_KEY}`
    : null;

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAF7FE] p-6" data-testid="rl-restaurant-loading">
        <div className="max-w-md mx-auto">
          <RLCard className="p-8 text-center text-sm text-slate-500">
            Loading restaurant…
          </RLCard>
        </div>
      </div>
    );
  }
  if (!biz) {
    return (
      <div className="min-h-screen bg-[#FAF7FE] p-6" data-testid="rl-restaurant-notfound">
        <div className="max-w-md mx-auto">
          <RLCard className="p-8 text-center">
            <div className="font-semibold text-slate-900">Restaurant not found</div>
            <RLButton className="mt-4" onClick={() => navigate("/discover")}>
              Back to Discover
            </RLButton>
          </RLCard>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAF7FE] pb-24"
              data-testid="rl-restaurant-detail">
      {/* Hero */}
      <div className="relative h-56 overflow-hidden"
                style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
        <div className="absolute inset-0 flex items-center justify-center opacity-25">
          <Utensils size={120} className="text-white" strokeWidth={1.25} />
        </div>
        <button
          type="button"
          onClick={() => navigate(-1)}
          data-testid="rl-restaurant-back"
          className="absolute top-4 left-4 w-10 h-10 rounded-full bg-white/30
                              backdrop-blur text-white flex items-center justify-center
                              hover:bg-white/45 transition-colors">
          <ArrowLeft size={18} />
        </button>
      </div>

      <div className="max-w-md mx-auto -mt-8 px-4">
        <RLCard className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-xl font-black text-slate-900 leading-tight">
                {biz.name}
              </h1>
              <div className="text-[11px] uppercase tracking-wider text-slate-500
                                        font-semibold mt-1 flex items-center gap-2 flex-wrap">
                <span className="capitalize">{(biz.category || "").replace("_", " ")}</span>
                {biz.address && (
                  <>
                    <span className="opacity-40">·</span>
                    <span className="flex items-center gap-0.5 min-w-0">
                      <MapPin size={11} /> <span className="truncate">{biz.address}</span>
                    </span>
                  </>
                )}
              </div>
            </div>
            {typeof biz.rating === "number" && (
              <div className="flex items-center gap-1 bg-purple-50 px-2.5 py-1.5
                                        rounded-full text-purple-800 font-semibold text-sm">
                <Star size={13} className="fill-amber-400 text-amber-400" />
                {biz.rating.toFixed(1)}
              </div>
            )}
          </div>
        </RLCard>

        {/* Offers */}
        <section className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-black text-slate-900">Available offers</h2>
            {offers.length > 0 && (
              <RLBadge tone="purple">{offers.length} live</RLBadge>
            )}
          </div>
          {offers.length === 0 ? (
            <RLCard className="p-5 text-center text-sm text-slate-500"
                          data-testid="rl-restaurant-no-offers">
              No active offers right now — earn points on every visit anyway.
            </RLCard>
          ) : (
            <div className="space-y-2">
              {offers.map((o) => (
                <RLCard key={o.offer_id} className="p-4"
                              data-testid={`rl-restaurant-offer-${o.offer_id}`}>
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-100 text-purple-700
                                              flex items-center justify-center flex-shrink-0">
                      <Ticket size={17} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-slate-900 truncate">{o.title}</div>
                      {o.description && (
                        <div className="text-xs text-slate-600 mt-1 line-clamp-2">
                          {o.description}
                        </div>
                      )}
                      <div className="mt-2 flex items-center gap-2">
                        {typeof o.discount_percent === "number" && (
                          <RLBadge tone="pink">-{o.discount_percent}%</RLBadge>
                        )}
                        <RLBadge tone="emerald">+20 pts on redeem</RLBadge>
                      </div>
                    </div>
                  </div>
                </RLCard>
              ))}
            </div>
          )}
        </section>

        {/* Mini-map */}
        {gmapsStatic && (
          <section className="mt-4" data-testid="rl-restaurant-map">
            <div className="rounded-2xl overflow-hidden border border-slate-100
                                    shadow-sm">
              <img src={gmapsStatic} alt="Location map"
                        className="w-full h-auto block"
                        onError={(e)=>{e.currentTarget.style.display="none";}} />
            </div>
            <div className="mt-2 text-[11px] uppercase tracking-widest text-slate-500
                                    font-semibold flex items-center gap-1.5">
              <MapPin size={12} /> {biz.address || `${biz.lat}, ${biz.lng}`}
            </div>
          </section>
        )}

        {/* CTAs */}
        <div className="mt-6 space-y-2">
          <RLButton
            size="lg"
            className="w-full"
            onClick={handleGetDeal}
            disabled={saving || offers.length === 0}
            data-testid="rl-restaurant-get-deal">
            <Sparkles size={16} />
            {offers.length === 0 ? "No deals available" : (saving ? "Saving…" : "Get deal")}
          </RLButton>
          <RLButton
            size="lg"
            variant="outline"
            className="w-full"
            onClick={() => navigate("/pay")}
            data-testid="rl-restaurant-pay">
            <CreditCard size={16} />
            Scan to pay
          </RLButton>
        </div>
      </div>
    </div>
  );
}
