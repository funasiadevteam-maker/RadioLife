// Phase 9c — /wallet/coupons.  Listener's coupon wallet: Active /
// Redeemed / Expired tabs.  Each card shows the QR code, redemption
// code, expiry countdown, and Wallet buttons.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import QRCode from "react-qr-code";
import { ChevronLeft, Gift, Clock, X, ExternalLink,
          Loader2, ShoppingBag, Smartphone, ChevronRight } from "lucide-react";
import "@/PublicBusiness.css"; // shared commerce theme

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const TABS = [
  { id: "claimed",  label: "Active" },
  { id: "redeemed", label: "Redeemed" },
  { id: "expired",  label: "Expired" },
];

export default function Coupons() {
  const [tab, setTab] = useState("claimed");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showQR, setShowQR] = useState(null);

  const load = async (s) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/commerce/coupons/me`,
                                          { params: { status: s } });
      setItems(r.data.items || []);
    } catch (e) {
      toast.error("Couldn't load coupons");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(tab); }, [tab]);

  const addToGoogle = async (couponId) => {
    try {
      const r = await axios.post(
        `${API}/commerce/coupons/${couponId}/wallet_pass/google`);
      window.open(r.data.save_url, "_blank");
      if (r.data.pass_status === "stub") {
        toast.message("Wallet pass (stub)", {
          description: r.data.reason || "GOOGLE_WALLET_ISSUER_ID not configured"
        });
      } else {
        toast.success("Opening Google Wallet…");
      }
    } catch { toast.error("Couldn't mint Google Wallet pass"); }
  };

  const addToApple = async (couponId) => {
    try {
      const r = await axios.post(
        `${API}/commerce/coupons/${couponId}/wallet_pass/apple`);
      toast.message("Apple Wallet (stub)", {
        description: r.data.reason || "Apple Dev cert not configured yet" });
    } catch { toast.error("Apple Wallet stub failed"); }
  };

  return (
    <div className="biz-shell" data-testid="coupons-shell">
      <div className="coupons-header">
        <Link to="/" className="paw-back" data-testid="coupons-back">
          <ChevronLeft size={14} /> FUUSIC
        </Link>
        <h1>My Coupons</h1>
        <p className="dim small">Active claims, recently redeemed, and history</p>
      </div>

      <div className="coupons-tabs" data-testid="coupons-tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button"
                    className="coupon-tab"
                    data-active={tab === t.id}
                    onClick={() => setTab(t.id)}
                    data-testid={`coupons-tab-${t.id}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="coupons-body">
        {loading
          ? <div className="paw-loading"><Loader2 className="spin" /></div>
          : items.length === 0
            ? <div className="biz-empty" data-testid="coupons-empty">
                No {tab} coupons. <Link to="/" className="dim small">Browse offers →</Link>
              </div>
            : <div className="coupon-list">
                {items.map((c) => (
                  <CouponCard key={c.coupon_id} c={c}
                                tab={tab}
                                onShowQR={() => setShowQR(c)}
                                onAddGoogle={() => addToGoogle(c.coupon_id)}
                                onAddApple={() => addToApple(c.coupon_id)} />
                ))}
              </div>}
      </div>

      {showQR && (
        <div className="qr-overlay" data-testid="qr-modal"
              onClick={() => setShowQR(null)}>
          <div className="qr-modal" onClick={(e) => e.stopPropagation()}>
            <div className="qr-head">
              <div>
                <div className="dim small">SHOW TO REDEEM</div>
                <div className="qr-code-label mono">{showQR.redemption_code}</div>
              </div>
              <button type="button" onClick={() => setShowQR(null)}
                        data-testid="qr-modal-close"
                        className="why-this-ad-close"><X size={14}/></button>
            </div>
            <div className="qr-wrap">
              <QRCode value={showQR.qr_token || showQR.coupon_id}
                          fgColor="#ffffff" bgColor="#0a0d12" size={200}/>
            </div>
            <div className="dim small qr-foot">
              Expires {new Date(showQR.expires_at).toLocaleString()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CouponCard({ c, tab, onShowQR, onAddGoogle, onAddApple }) {
  const remainingMin = Math.max(0, Math.floor(
    (new Date(c.expires_at) - new Date()) / 60000));
  return (
    <div className="coupon-card" data-testid={`coupon-card-${c.coupon_id}`}>
      <div className="coupon-card-top">
        <ShoppingBag size={14} className="dim" />
        <span className="mono small">{c.redemption_code}</span>
        <span className="biz-chip" style={{ marginLeft: "auto" }}>
          {c.claim_source.replace(/_/g, " ")}
        </span>
      </div>
      <div className="coupon-id dim small">{c.offer_id}</div>
      <div className="coupon-meta">
        <span className="biz-chip">
          <Clock size={11} />{" "}
          {tab === "claimed" ? `${remainingMin}m left`
                                : new Date(c.expires_at).toLocaleDateString()}
        </span>
      </div>
      <div className="coupon-actions">
        {tab === "claimed" && (
          <>
            <button className="claim-btn" type="button"
                      onClick={onShowQR}
                      data-testid={`coupon-show-qr-${c.coupon_id}`}>
              Show QR
            </button>
            <button className="ghost-btn" type="button"
                      onClick={onAddGoogle}
                      data-testid={`coupon-google-wallet-${c.coupon_id}`}>
              <ExternalLink size={11} /> Google Wallet
            </button>
            <button className="ghost-btn" type="button"
                      onClick={onAddApple}
                      data-testid={`coupon-apple-wallet-${c.coupon_id}`}>
              <Smartphone size={11} /> Apple Wallet
            </button>
          </>
        )}
        {tab === "redeemed" && (
          <span className="biz-chip verified">Redeemed{c.redeemed_at ? " · " + new Date(c.redeemed_at).toLocaleDateString() : ""}</span>
        )}
        {tab === "expired" && (
          <span className="biz-chip dim">Expired</span>
        )}
      </div>
    </div>
  );
}
