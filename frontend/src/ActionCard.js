// ActionCard.js — Phase 4 overlay rendered on Radio player while an ad is playing.
// Polls /api/ads/current?session_id=X. When has_ad=true, slides up from bottom
// 1s after ad starts and persists 30s after ad ends.
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, MapPin, Bookmark, ShoppingBag, Calendar, Gift, Share2, Loader2, Info } from "lucide-react";
import "./ActionCard.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const ICON = {
  save_coupon: <Bookmark size={14} />,
  get_directions: <MapPin size={14} />,
  buy_now: <ShoppingBag size={14} />,
  book_appointment: <Calendar size={14} />,
  reserve_table: <Calendar size={14} />,
  buy_tickets: <Calendar size={14} />,
  join_giveaway: <Gift size={14} />,
  share: <Share2 size={14} />,
  buy_prepaid_lunch: <ShoppingBag size={14} />,
  buy_prepaid_dinner: <ShoppingBag size={14} />,
  add_to_wallet: <Bookmark size={14} />,
  remind_me_later: <Calendar size={14} />,
  request_callback: <Calendar size={14} />,
  clip_ad: <Bookmark size={14} />,
};

export default function ActionCard({ sessionId, currentSegmentId, isPremium }) {
  const [adData, setAdData] = useState(null);
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  // Phase 9b — "Why this ad?" modal (route-targeted explainability)
  const [whyOpen, setWhyOpen] = useState(false);
  const [whyData, setWhyData] = useState(null);
  const [whyLoading, setWhyLoading] = useState(false);

  const openWhy = useCallback(async () => {
    const oppId = adData?.ad_pod?.route_opp_id;
    if (!oppId) return;
    setWhyOpen(true); setWhyLoading(true);
    try {
      const r = await axios.get(`${API}/route_ads/${oppId}/reason_codes`);
      setWhyData(r.data);
    } catch (e) {
      toast.error("Couldn't load reasons");
    } finally { setWhyLoading(false); }
  }, [adData]);

  const fetchAd = useCallback(async () => {
    if (!sessionId || isPremium) {
      setAdData(null); setVisible(false); return;
    }
    try {
      const r = await axios.get(`${API}/ads/current?session_id=${sessionId}`);
      if (r.data?.has_ad) {
        setAdData(r.data);
        setDismissed(false);
        setTimeout(() => setVisible(true), 800);
      } else {
        setVisible(false);
      }
    } catch (e) { /* silent */ }
  }, [sessionId, isPremium]);

  useEffect(() => {
    fetchAd();
  }, [fetchAd, currentSegmentId]);

  if (!adData || !adData.has_ad || isPremium || dismissed) return null;
  const camp = adData.campaign || {};
  const biz = adData.business || {};
  const brand = (biz.brand_colors_json) || {};
  const accent = brand.primary || "#ff2d95";

  const handleAction = async (action) => {
    setBusy(action.action_type);
    const payload = {
      ad_pod_id: adData.ad_pod?.id,
      campaign_id: camp.campaign_id,
      business_id: biz.business_id,
      offer_id: action.offer_id || _findOfferId(camp),
      product_id: action.product_id || _findProductId(camp),
      giveaway_id: action.giveaway_id || _findGiveawayId(camp),
    };
    try {
      const r = await axios.post(`${API}/ads/action/${action.action_type}`, payload);
      const d = r.data || {};
      if (action.action_type === "get_directions" && d.maps_url) {
        window.open(d.maps_url, "_blank");
        toast.success(`Directions to ${biz.name} opened`);
      } else if (action.action_type === "save_coupon") {
        toast.success(`Coupon saved: ${d.code}`);
      } else if (action.action_type === "buy_now") {
        toast.success(`Order intent created`);
      } else if (action.action_type === "reserve_table") {
        toast.success(`Reservation requested at ${biz.name}`);
      } else if (action.action_type === "share") {
        if (navigator.share) {
          try { await navigator.share({ title: camp.name, url: d.share_url }); } catch (e) {}
        } else {
          navigator.clipboard?.writeText(d.share_url || "");
          toast.success("Share link copied");
        }
      } else if (action.action_type === "join_giveaway") {
        toast.success(d.already_entered ? "Already entered" : "You're in the giveaway!");
      } else {
        toast.success(d.note || "Saved");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    } finally { setBusy(null); }
  };

  return (
    <div
      className={`action-card ${visible ? "visible" : ""}`}
      data-testid="ad-action-card"
      style={{
        borderTop: `3px solid ${accent}`,
        boxShadow: `0 -8px 28px ${accent}33`,
      }}
    >
      <button
        type="button"
        className="action-close"
        onClick={() => { setDismissed(true); setVisible(false); }}
        aria-label="Dismiss"
        data-testid="ad-card-close"
      >
        <X size={14} />
      </button>
      <div className="action-card-head">
        <div className="action-card-pill" style={{ background: accent }} data-testid="ad-card-sponsor-tag">
          SPONSORED
        </div>
        <div className="action-card-title" data-testid="ad-card-title">{camp.name}</div>
        {biz.name && <div className="action-card-biz" data-testid="ad-card-biz">{biz.name}</div>}
        {adData?.ad_pod?.route_opp_id && (
          <button type="button" className="why-this-ad-link"
            onClick={openWhy} data-testid="why-this-ad-link">
            <Info size={11} /> Why this ad?
          </button>
        )}
      </div>
      <div className="action-card-buttons">
        {(adData.action_cards || []).map((a) => (
          <button
            key={a.action_type}
            type="button"
            className="action-btn"
            onClick={() => handleAction(a)}
            disabled={busy === a.action_type}
            data-testid={`ad-action-${a.action_type}`}
            style={busy === a.action_type ? { opacity: 0.6 } : {}}
          >
            {busy === a.action_type ? <Loader2 className="spin-mini" size={14} /> : (ICON[a.action_type] || null)}
            <span>{a.label}</span>
          </button>
        ))}
      </div>
      {whyOpen && (
        <div className="why-this-ad-overlay" data-testid="why-this-ad-modal"
              onClick={() => setWhyOpen(false)}>
          <div className="why-this-ad-modal" onClick={(e) => e.stopPropagation()}>
            <div className="why-this-ad-head">
              <div>
                <div className="why-this-ad-eyebrow">WHY THIS AD?</div>
                <div className="why-this-ad-title">
                  {whyData?.campaign_title || "Loading…"}
                </div>
                {whyData?.sponsor_name && (
                  <div className="why-this-ad-sponsor">
                    Sponsored by {whyData.sponsor_name}
                  </div>
                )}
              </div>
              <button type="button" onClick={() => setWhyOpen(false)}
                        data-testid="why-this-ad-close"
                        className="why-this-ad-close" aria-label="Close">
                <X size={14} />
              </button>
            </div>
            {whyLoading ? (
              <div className="why-this-ad-loading">
                <Loader2 size={16} className="spin-mini" /> Loading…
              </div>
            ) : (
              <>
                <div className="why-this-ad-body">
                  We chose this because:
                </div>
                <ul className="why-this-ad-reasons"
                      data-testid="why-this-ad-reasons">
                  {(whyData?.reason_codes || []).map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <div className="why-this-ad-meta">
                  Kind: <span className="why-this-ad-pill">{whyData?.kind?.replace(/_/g, " ")}</span>
                  {whyData?.daypart && (
                    <>{" · "}Daypart: <span className="why-this-ad-pill">
                      {whyData.daypart.replace(/_/g, " ")}
                    </span></>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function _findOfferId(camp) { return (camp.offer_id) || null; }
function _findProductId(camp) { return (camp.product_id) || null; }
function _findGiveawayId(camp) { return (camp.giveaway_id) || null; }
