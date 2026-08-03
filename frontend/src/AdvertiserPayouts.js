// AdvertiserPayouts.js — Phase 4.5: Stripe Connect Express dashboard.
import { useEffect, useState, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, ArrowRight, ExternalLink, CheckCircle2, AlertTriangle,
  Banknote, Wallet, ShieldCheck, ChevronLeft,
} from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

function StatTile({ label, value, sub, accent = "#4ade80", testid }) {
  return (
    <div className="img-station-card" data-testid={testid} style={{ padding: 18, gap: 8 }}>
      <div className="meta-label" style={{ fontSize: 10 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: accent, lineHeight: 1.0 }}>{value}</div>
      {sub && <div className="asset-slug" style={{ fontSize: 11, color: "#888892" }}>{sub}</div>}
    </div>
  );
}

export default function AdvertiserPayouts() {
  const [searchParams] = useSearchParams();
  const [businesses, setBusinesses] = useState([]);
  const [selectedBiz, setSelectedBiz] = useState(null);
  const [status, setStatus] = useState(null);
  const [payouts, setPayouts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  const loadBusinesses = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/advertiser/businesses`);
      const items = r.data.items || [];
      setBusinesses(items);
      if (items.length && !selectedBiz) setSelectedBiz(items[0].business_id);
    } catch (e) {
      toast.error("Failed to load businesses");
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadStatus = useCallback(async (bizId) => {
    if (!bizId) return;
    try {
      const [s, p] = await Promise.all([
        axios.get(`${API}/advertiser/stripe/account_status?business_id=${bizId}`),
        axios.get(`${API}/advertiser/stripe/payouts?business_id=${bizId}`),
      ]);
      setStatus(s.data); setPayouts(p.data);
    } catch (e) {
      setStatus({ connected: false }); setPayouts({});
    }
  }, []);

  useEffect(() => { loadBusinesses(); }, [loadBusinesses]);
  useEffect(() => { if (selectedBiz) loadStatus(selectedBiz); }, [selectedBiz, loadStatus]);

  useEffect(() => {
    if (searchParams.get("return") === "1") toast.success("Welcome back! Refreshing Stripe Connect status...");
    if (searchParams.get("refresh") === "1") toast.info("Continue your Stripe onboarding below");
  }, [searchParams]);

  const startConnect = async () => {
    if (!selectedBiz) return toast.error("Pick a business first");
    setConnecting(true);
    try {
      const r = await axios.post(`${API}/advertiser/stripe/connect_account`, { business_id: selectedBiz });
      if (r.data.onboarding_url) window.location.href = r.data.onboarding_url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Stripe Connect failed");
    } finally { setConnecting(false); }
  };

  const refreshLink = async () => {
    setConnecting(true);
    try {
      const r = await axios.post(`${API}/advertiser/stripe/refresh_account_link?business_id=${selectedBiz}`);
      if (r.data.onboarding_url) window.location.href = r.data.onboarding_url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Refresh failed");
    } finally { setConnecting(false); }
  };

  if (loading) return <div className="admin-img-wrap"><Loader2 className="spin" size={28} /></div>;

  return (
    <div className="admin-img-wrap" data-testid="advertiser-payouts">
      <header className="admin-img-header">
        <div>
          <Link to="/advertiser" style={{ color: "#888892", fontSize: 12, textDecoration: "none" }} data-testid="back-to-advertiser">
            <ChevronLeft size={11} style={{ verticalAlign: "-1px" }} /> back to advertiser
          </Link>
          <h1><Banknote size={24} style={{ verticalAlign: "-4px", marginRight: 8 }} />Payouts &amp; Stripe Connect</h1>
          <p>Onboard your business to Stripe Express to receive direct payouts from Action Card purchases. Platform fee 10%.</p>
        </div>
      </header>

      {businesses.length === 0 ? (
        <div className="img-station-card" data-testid="no-businesses-msg">
          <p>You don't have any businesses yet. <Link to="/advertiser" style={{ color: "#ff2d95" }}>Create one</Link> first.</p>
        </div>
      ) : (
        <>
          <section style={{ marginBottom: 16 }}>
            <label className="meta-label">SELECT BUSINESS</label>
            <select className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%", maxWidth: 480 }}
              value={selectedBiz || ""} onChange={(e) => setSelectedBiz(e.target.value)}
              data-testid="biz-select">
              {businesses.map((b) => (
                <option key={b.business_id} value={b.business_id}>
                  {b.name} ({b.market === "dfw" ? "DFW" : "Dubai"})
                </option>
              ))}
            </select>
          </section>

          {status && !status.connected && (
            <section className="img-station-card" data-testid="connect-cta" style={{ borderColor: "#ff2d95" }}>
              <div className="meta-label" style={{ fontSize: 11 }}><ShieldCheck size={11} /> NOT CONNECTED</div>
              <h2 style={{ fontSize: 18, color: "#fff", marginTop: 8 }}>Get paid out from BigFM Action Cards</h2>
              <p style={{ color: "#aaa", fontSize: 13, lineHeight: 1.6, marginTop: 8 }}>
                Connect a Stripe Express account so when a listener taps "Buy now" on your sponsor read,
                we route payment directly to your bank with a 10% platform fee. Onboarding takes ~5 minutes
                — KYC and bank account info handled by Stripe directly.
              </p>
              <button className="img-regenerate-btn" onClick={startConnect} disabled={connecting}
                style={{ marginTop: 14 }} data-testid="connect-stripe-btn">
                {connecting ? <Loader2 className="spin" size={14} /> : <ArrowRight size={14} />}
                {connecting ? " Redirecting..." : " Start Stripe Connect onboarding"}
              </button>
            </section>
          )}

          {status && status.connected && !status.charges_enabled && (
            <section className="img-station-card" data-testid="onboarding-incomplete" style={{ borderColor: "#fdb756" }}>
              <div className="meta-label" style={{ color: "#fdb756" }}><AlertTriangle size={11} /> ONBOARDING INCOMPLETE</div>
              <p style={{ color: "#aaa", fontSize: 13, lineHeight: 1.6, marginTop: 8 }}>
                Stripe needs more info before payouts can start. Pending requirements:
              </p>
              <ul style={{ color: "#fff", fontSize: 12, paddingLeft: 18, marginTop: 6 }}>
                {(status.requirements || []).map((r) => (<li key={r}>{r}</li>))}
                {(status.requirements || []).length === 0 && <li>review pending — check Stripe dashboard</li>}
              </ul>
              <button className="img-regenerate-btn" onClick={refreshLink} disabled={connecting}
                style={{ marginTop: 14 }} data-testid="refresh-onboarding-btn">
                {connecting ? <Loader2 className="spin" size={14} /> : <ExternalLink size={14} />}
                {connecting ? " ..." : " Continue Stripe onboarding"}
              </button>
            </section>
          )}

          {status && status.connected && status.charges_enabled && (
            <>
              <section className="img-station-card" data-testid="connected-banner" style={{ borderColor: "#4ade80" }}>
                <div className="meta-label" style={{ color: "#4ade80" }}>
                  <CheckCircle2 size={11} /> CONNECTED · CHARGES ENABLED
                  {status.payouts_enabled ? " · PAYOUTS ENABLED" : " · PAYOUTS PENDING"}
                </div>
                <div style={{ color: "#aaa", fontSize: 12, marginTop: 6 }}>
                  Stripe Account · <code style={{ color: "#fff" }}>{status.stripe_account_id}</code>
                </div>
              </section>

              <section className="img-stations-grid" style={{ marginTop: 16 }} data-testid="balance-tiles">
                <StatTile testid="tile-available" label="AVAILABLE BALANCE"
                  value={`$${(((payouts?.available?.[0]?.amount) || 0) / 100).toFixed(2)}`}
                  sub="ready to pay out" accent="#4ade80" />
                <StatTile testid="tile-pending" label="PENDING BALANCE"
                  value={`$${(((payouts?.pending?.[0]?.amount) || 0) / 100).toFixed(2)}`}
                  sub="not yet cleared" accent="#fdb756" />
                <StatTile testid="tile-platform-fee" label="PLATFORM FEE" value="10%"
                  sub="taken from each Action Card sale" accent="#7BD3F7" />
                <StatTile testid="tile-payout-cycle" label="PAYOUT SCHEDULE"
                  value={status.payouts_enabled ? "Daily" : "Pending"}
                  sub="set in Stripe dashboard" accent="#ff8a3d" />
              </section>

              <section className="img-station-card" style={{ marginTop: 16 }} data-testid="recent-payouts">
                <div className="meta-label"><Wallet size={11} /> RECENT PAYOUTS</div>
                {(payouts?.payouts || []).length === 0 ? (
                  <p style={{ color: "#888", fontSize: 12, marginTop: 8 }}>
                    No payouts yet. They will appear here once a listener completes a "Buy now" or "Buy tickets" Action Card.
                  </p>
                ) : (
                  payouts.payouts.map((p) => (
                    <div key={p.id} className="asset-meta-row" style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #25252f" }}>
                      <span style={{ fontSize: 12, color: "#fff" }}>{p.id}</span>
                      <span style={{ color: "#aaa", fontSize: 11 }}>
                        ${(p.amount / 100).toFixed(2)} {(p.currency || "usd").toUpperCase()} · <b style={{ color: p.status === "paid" ? "#4ade80" : "#fdb756" }}>{p.status}</b>
                      </span>
                    </div>
                  ))
                )}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
