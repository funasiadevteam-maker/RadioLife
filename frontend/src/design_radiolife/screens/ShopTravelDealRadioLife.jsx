// FUUSIC Shop — Travel deal detail + BigPoints demo booking.
// Rendered via screenFor() inside ShopInShell; reads the deal id from the path.
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Star, Coins, Check, Minus, Plus, MapPin, Clock } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${Math.round((c || 0) / 100)}`;

const TYPE_LABEL = {
  flight: "Flight", hotel: "Hotel", package: "Package",
  experience: "Experience", cruise: "Cruise",
};

export default function ShopTravelDealRadioLife() {
  const loc = useLocation();
  const navigate = useNavigate();
  const dealId = loc.pathname.split("/shop/travel/")[1]?.split("/")[0] || "";
  const [deal, setDeal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [travelers, setTravelers] = useState(1);
  const [booking, setBooking] = useState(false);
  const [confirmed, setConfirmed] = useState(null);

  useEffect(() => {
    if (!dealId) return;
    setLoading(true);
    axios.get(`${API}/travel/deals/${dealId}`)
      .then((r) => setDeal(r.data?.deal || null))
      .catch(() => setDeal(null))
      .finally(() => setLoading(false));
  }, [dealId]);

  const book = async () => {
    setBooking(true);
    try {
      const r = await axios.post(`${API}/travel/deals/${dealId}/book`, { travelers });
      setConfirmed(r.data);
    } catch (_e) { /* surfaced inline below */ }
    finally { setBooking(false); }
  };

  if (loading) return <div className="px-4 pt-10 text-center fz-muted">Loading deal…</div>;
  if (!deal) return (
    <div className="px-4 pt-10 text-center fz-muted" data-testid="travel-detail-missing">
      Deal not found. <Link to="/shop/travel" className="fz-brand font-bold">Back to Travel</Link>
    </div>
  );

  const total = (deal.price_cents || 0) * travelers;

  return (
    <div className="pb-10 fz-text" data-testid="rl-travel-detail">
      <div className="relative h-64" style={{ background: "var(--surface-2)" }}>
        {deal.image_url && <img src={deal.image_url} alt={deal.title} className="w-full h-full object-cover" />}
        <button onClick={() => navigate("/shop/travel")} data-testid="travel-detail-back"
          className="absolute top-4 left-4 w-10 h-10 rounded-full bg-black/55 text-white flex items-center justify-center">
          <ArrowLeft size={20} />
        </button>
        <span className="absolute bottom-4 left-4 text-[11px] font-black text-white px-3 py-1 rounded-full" style={{ background: "var(--brand-solid)" }}>
          {TYPE_LABEL[deal.deal_type] || "Travel"}
        </span>
      </div>

      <div className="px-4 pt-4 space-y-3">
        <div>
          <h1 className="text-2xl font-black fz-text leading-tight">{deal.title}</h1>
          <div className="flex items-center gap-3 mt-1 fz-muted text-sm">
            <span className="flex items-center gap-1"><MapPin size={14} />{deal.destination}</span>
            {deal.duration && <span className="flex items-center gap-1"><Clock size={14} />{deal.duration}</span>}
            {deal.rating ? <span className="flex items-center gap-1 font-bold fz-sub">
              <Star size={13} style={{ color: "var(--bigpoints-gold)", fill: "var(--bigpoints-gold)" }} />{deal.rating.toFixed(1)}</span> : null}
          </div>
        </div>

        {deal.blurb && <p className="fz-sub text-sm leading-relaxed">{deal.blurb}</p>}

        {deal.tags?.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {deal.tags.map((tg) => (
              <span key={tg} className="fz-chip rounded-full px-3 py-1 text-xs font-bold capitalize">{tg}</span>
            ))}
          </div>
        )}

        <div className="fz-brand-soft rounded-2xl p-4 flex items-center gap-2">
          <Coins size={18} className="fz-brand" />
          <span className="text-sm font-bold fz-text">Earn <b>+{deal.bigpoints}</b> BigPoints on this booking</span>
        </div>

        {confirmed ? (
          <div className="fz-card rounded-2xl p-5 text-center" data-testid="travel-booking-confirmed">
            <span className="inline-flex w-14 h-14 rounded-full items-center justify-center mb-2" style={{ background: "var(--brand-soft-bg, rgba(168,85,247,0.15))" }}>
              <Check size={28} className="fz-brand" />
            </span>
            <div className="font-black text-lg fz-text">Booking confirmed!</div>
            <div className="fz-muted text-sm mt-1">Confirmation <b className="fz-text">{confirmed.confirmation}</b></div>
            <div className="fz-muted text-xs mt-0.5">Total paid {money(confirmed.total_cents)} · demo BigPoints checkout</div>
            <button onClick={() => navigate("/shop/travel")} data-testid="travel-booking-done"
              className="fz-grad mt-4 w-full font-black rounded-full py-3">Explore more deals</button>
          </div>
        ) : (
          <>
            <div className="fz-card rounded-2xl p-4 flex items-center justify-between">
              <span className="font-bold fz-text">Travelers</span>
              <div className="flex items-center gap-3">
                <button onClick={() => setTravelers((n) => Math.max(1, n - 1))} data-testid="travel-travelers-dec"
                  className="w-9 h-9 rounded-full fz-chip flex items-center justify-center"><Minus size={16} /></button>
                <span className="font-black text-lg w-6 text-center" data-testid="travel-travelers">{travelers}</span>
                <button onClick={() => setTravelers((n) => Math.min(9, n + 1))} data-testid="travel-travelers-inc"
                  className="w-9 h-9 rounded-full fz-chip flex items-center justify-center"><Plus size={16} /></button>
              </div>
            </div>

            <div className="sticky bottom-24 fz-card rounded-2xl p-4 flex items-center gap-3" style={{ boxShadow: "var(--card-shadow)" }}>
              <div className="flex-1">
                <div className="fz-muted text-xs">Total</div>
                <div className="font-black text-xl fz-text">{money(total)}</div>
              </div>
              <button onClick={book} disabled={booking} data-testid="travel-book-btn"
                className="fz-grad font-black rounded-full px-6 py-3 disabled:opacity-60">
                {booking ? "Booking…" : "Book with BigPoints"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
