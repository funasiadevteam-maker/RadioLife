// Phase 9c — Partner Portal at /partner.  Lists my businesses, lets
// partner edit profile, create / submit / pause / resume / end offers,
// scaffold POS connect, view redemptions.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "@/AuthContext";
import { ChevronLeft, Plus, Loader2, Briefcase, Tag, Settings,
          BarChart3, Pause, Play, X, ShoppingBag, Upload, Check } from "lucide-react";
import "@/PublicBusiness.css";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function PartnerDashboard() {
  const { user } = useAuth();
  const [businesses, setBusinesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedBiz, setSelectedBiz] = useState(null);
  const [tab, setTab] = useState("offers");
  const [showClaim, setShowClaim] = useState(false);
  const [showCreateOffer, setShowCreateOffer] = useState(false);
  const [upgrading, setUpgrading] = useState(false);

  const isPartner = ["business_partner", "admin", "moderator"].includes(user?.role);

  const loadBusinesses = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/partner/businesses/me`);
      setBusinesses(r.data.items || []);
      if (r.data.items?.length && !selectedBiz) {
        setSelectedBiz(r.data.items[0]);
      }
    } catch (e) {
      if (e.response?.status === 403) {
        // Need partner upgrade
      } else toast.error("Couldn't load businesses");
    } finally { setLoading(false); }
  };

  useEffect(() => { if (isPartner) loadBusinesses(); else setLoading(false); }, [isPartner]);

  const upgradeToPartner = async () => {
    setUpgrading(true);
    try {
      await axios.post(`${API}/auth/partner/upgrade`,
                             { accept_terms: true });
      toast.success("Partner upgrade complete — reload to continue");
      setTimeout(() => window.location.reload(), 700);
    } catch (e) { toast.error("Upgrade failed"); }
    finally { setUpgrading(false); }
  };

  if (loading) {
    return <div className="biz-shell"><div className="paw-loading">
      <Loader2 className="spin" /></div></div>;
  }

  if (!isPartner) {
    return (
      <div className="biz-shell" data-testid="partner-upgrade-shell">
        <div className="coupons-header">
          <Link to="/" className="paw-back"><ChevronLeft size={14}/> BigFM</Link>
          <h1>Become a BigFM Partner</h1>
          <p className="dim small">List your business, post offers, and reach drivers in real time.</p>
        </div>
        <div className="biz-body" style={{ padding: 40 }}>
          <div className="partner-upgrade-card">
            <Briefcase size={28} style={{ color: "#ff2d95" }} />
            <h2>Sign up as a partner</h2>
            <p className="dim">By upgrading, you accept the BigFM Partner Terms:
            you're responsible for honouring claimed offers in-store, you'll be
            verified by our team before going live, and POS integrations are
            opt-in.</p>
            <button className="claim-btn" type="button"
                      onClick={upgradeToPartner} disabled={upgrading}
                      data-testid="partner-upgrade-btn">
              {upgrading ? <Loader2 className="spin-mini" size={13}/> : <Check size={13}/>}
              Accept &amp; upgrade
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="biz-shell" data-testid="partner-shell">
      <div className="coupons-header">
        <Link to="/" className="paw-back"><ChevronLeft size={14}/> BigFM</Link>
        <h1>Partner Portal</h1>
        <p className="dim small">Manage your businesses + offers</p>
      </div>

      <div className="partner-grid">
        <aside className="partner-aside" data-testid="partner-aside">
          <div className="panel-toolbar">
            <h3><Briefcase size={13}/> My Businesses</h3>
            <button className="ghost-btn" type="button"
                      onClick={() => setShowClaim(true)}
                      data-testid="partner-claim-business-btn">
              <Plus size={11}/> Claim
            </button>
          </div>
          <div className="saved-loc-list">
            {businesses.length === 0 && (
              <div className="biz-empty">No businesses yet. Claim one to start.</div>
            )}
            {businesses.map((b) => (
              <button key={b.business_id} type="button"
                        className="biz-side-row"
                        data-active={selectedBiz?.business_id === b.business_id}
                        onClick={() => setSelectedBiz(b)}
                        data-testid={`partner-biz-row-${b.business_id}`}>
                <span className="biz-side-name">{b.name}</span>
                <span className="biz-side-status" data-status={b.partner_status}>
                  {b.partner_status || "draft"}
                </span>
              </button>
            ))}
          </div>
        </aside>

        <main className="partner-main">
          {selectedBiz ? (
            <>
              <div className="partner-bizhead">
                <div>
                  <h2 data-testid="partner-selected-biz">{selectedBiz.name}</h2>
                  {selectedBiz.slug && (
                    <Link to={`/business/${selectedBiz.slug}`}
                            className="dim small" target="_blank"
                            data-testid="partner-public-link">
                      /business/{selectedBiz.slug} ↗
                    </Link>
                  )}
                </div>
                <div className="partner-tabs" data-testid="partner-tabs">
                  {[
                    {id: "offers", label: "Offers", Icon: Tag},
                    {id: "redemptions", label: "Redemptions", Icon: ShoppingBag},
                    {id: "settings", label: "Settings", Icon: Settings},
                  ].map(({id, label, Icon}) => (
                    <button key={id} type="button"
                              className="coupon-tab"
                              data-active={tab === id}
                              onClick={() => setTab(id)}
                              data-testid={`partner-tab-${id}`}>
                      <Icon size={12}/> {label}
                    </button>
                  ))}
                </div>
              </div>
              {tab === "offers" && (
                <OffersTab biz={selectedBiz}
                              onNewOffer={() => setShowCreateOffer(true)} />
              )}
              {tab === "redemptions" && (
                <RedemptionsTab biz={selectedBiz} />
              )}
              {tab === "settings" && (
                <SettingsTab biz={selectedBiz} onReload={loadBusinesses} />
              )}
            </>
          ) : (
            <div className="biz-empty">Select or claim a business to begin.</div>
          )}
        </main>
      </div>

      {showClaim && <ClaimBusinessModal
                          onClose={() => setShowClaim(false)}
                          onClaimed={() => { setShowClaim(false); loadBusinesses(); }}/>}
      {showCreateOffer && selectedBiz && (
        <CreateOfferModal biz={selectedBiz}
                                 onClose={() => setShowCreateOffer(false)}
                                 onCreated={() => { setShowCreateOffer(false); }}/>)}
    </div>
  );
}

function OffersTab({ biz, onNewOffer }) {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/partner/businesses/${biz.business_id}/offers`);
      setOffers(r.data.items || []);
    } catch { toast.error("Couldn't load offers"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [biz.business_id]);

  const transition = async (off, action) => {
    try {
      await axios.post(
        `${API}/partner/businesses/${biz.business_id}/offers/${off.offer_id}/${action}`);
      toast.success(`${action} OK`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || `${action} failed`);
    }
  };

  // Phase 9c.1 — Partner acknowledges rejection reason and re-opens
  // the offer back to draft for editing + re-submission.
  const revise = async (off) => {
    try {
      await axios.post(
        `${API}/partner/businesses/${biz.business_id}/offers/${off.offer_id}/revise`,
        { acknowledge_rejection_reason: true });
      toast.success("Re-opened for editing. Update and re-submit.");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "revise failed");
    }
  };

  return (
    <div className="partner-section">
      <div className="panel-toolbar">
        <h3>Offers</h3>
        <button className="claim-btn" type="button"
                  onClick={onNewOffer}
                  data-testid="partner-new-offer-btn">
          <Plus size={11}/> New offer
        </button>
      </div>
      {loading
        ? <div className="paw-loading"><Loader2 className="spin"/></div>
        : offers.length === 0
          ? <div className="biz-empty">No offers yet.</div>
          : <div className="offer-list" data-testid="partner-offers-list">
              {offers.map((o) => (
                <div className="offer-card" key={o.offer_id}
                      data-testid={`partner-offer-${o.offer_id}`}>
                  <div className="offer-body">
                    <div className="offer-title">{o.title}</div>
                    <div className="offer-chips">
                      <span className="biz-chip" data-status={o.status}>
                        {o.status}
                      </span>
                      <span className="biz-chip">{o.offer_type.replace(/_/g, " ")}</span>
                      <span className="biz-chip">
                        {o.inventory_remaining ?? 0} / {o.max_redemptions_total ?? 0} left
                      </span>
                    </div>
                    {o.description && (
                      <div className="offer-desc dim small">{o.description}</div>
                    )}
                    {o.status === "rejected" && o.rejection_reason && (
                      <div className="offer-reject-banner"
                            data-testid={`partner-offer-reject-reason-${o.offer_id}`}
                            style={{
                              marginTop: 8, padding: "8px 10px",
                              borderRadius: 8,
                              background: "rgba(255,80,80,.08)",
                              border: "1px solid rgba(255,80,80,.25)",
                              color: "#ffb3b3", fontSize: 12, lineHeight: 1.4,
                            }}>
                        <strong style={{color: "#ff8a8a"}}>Rejected:</strong>{" "}
                        {o.rejection_reason}
                      </div>
                    )}
                    <div className="offer-actions">
                      {o.status === "draft" && (
                        <button className="claim-btn small"
                                  data-testid={`partner-offer-submit-${o.offer_id}`}
                                  onClick={() => transition(o, "submit_for_approval")}>
                          <Upload size={11}/> Submit
                        </button>
                      )}
                      {o.status === "rejected" && (
                        <button className="claim-btn small"
                                  data-testid={`partner-offer-revise-${o.offer_id}`}
                                  onClick={() => revise(o)}>
                          <Upload size={11}/> Revise &amp; Re-submit
                        </button>
                      )}
                      {o.status === "active" && (
                        <button className="ghost-btn"
                                  data-testid={`partner-offer-pause-${o.offer_id}`}
                                  onClick={() => transition(o, "pause")}>
                          <Pause size={11}/> Pause
                        </button>
                      )}
                      {o.status === "paused" && (
                        <button className="ghost-btn"
                                  data-testid={`partner-offer-resume-${o.offer_id}`}
                                  onClick={() => transition(o, "resume")}>
                          <Play size={11}/> Resume
                        </button>
                      )}
                      {(o.status === "active" || o.status === "paused") && (
                        <button className="ghost-btn danger"
                                  data-testid={`partner-offer-end-${o.offer_id}`}
                                  onClick={() => transition(o, "end")}>
                          <X size={11}/> End
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>}
    </div>
  );
}

function RedemptionsTab({ biz }) {
  const [redemptions, setRedemptions] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        // Fetch all offers + sum coupons.  Simpler: query the audit.
        const r = await axios.get(
          `${API}/admin/offer_redemptions_audit`,
          { params: { business_id: biz.business_id, limit: 50 } });
        setRedemptions(r.data.items || []);
      } catch { /* admin-gated; partners see empty */ }
    })();
  }, [biz.business_id]);
  return (
    <div className="partner-section">
      <div className="panel-toolbar"><h3>Recent Redemptions</h3></div>
      {redemptions.length === 0 ? (
        <div className="biz-empty">No redemptions yet (or admin-only view).</div>
      ) : (
        <div className="saved-loc-list">
          {redemptions.map((r) => (
            <div className="saved-loc-row" key={r.audit_id}>
              <div className="sl-info">
                <div className="sl-label">{r.outcome}</div>
                <div className="dim small mono">{r.coupon_id || "-"} · {r.ip || "-"}</div>
              </div>
              <span className="dim small">{new Date(r.ts).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SettingsTab({ biz, onReload }) {
  const [form, setForm] = useState({
    name: biz.name || "",
    tagline: biz.tagline || "",
    description: biz.description || "",
    logo_url: biz.logo_url || "",
    phone: biz.phone || "",
  });
  const [posProvider, setPosProvider] = useState(
    biz.pos_integration?.provider || "none");
  const [posMid, setPosMid] = useState(
    biz.pos_integration?.merchant_id || "");
  const [saving, setSaving] = useState(false);
  const [posSaving, setPosSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await axios.patch(`${API}/partner/businesses/${biz.business_id}`, form);
      toast.success("Profile saved");
      onReload();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const connectPos = async () => {
    setPosSaving(true);
    try {
      await axios.post(
        `${API}/partner/businesses/${biz.business_id}/pos/connect`,
        { provider: posProvider, external_merchant_id: posMid });
      toast.success(`POS ${posProvider} connected (scaffold)`);
      onReload();
    } catch (e) { toast.error(e.response?.data?.detail || "POS connect failed"); }
    finally { setPosSaving(false); }
  };

  return (
    <div className="partner-section" data-testid="partner-settings">
      <div className="panel-toolbar"><h3>Profile</h3></div>
      {["name", "tagline", "description", "logo_url", "phone"].map((k) => (
        <div className="cf-row" key={k}>
          <label className="meta-label">{k.toUpperCase()}</label>
          <input className="lead-input"
                  value={form[k]}
                  onChange={(e) => setForm({...form, [k]: e.target.value})}
                  data-testid={`partner-edit-${k}`} />
        </div>
      ))}
      <button className="claim-btn" type="button" onClick={save}
                disabled={saving}
                data-testid="partner-save-profile-btn">
        {saving ? <Loader2 className="spin-mini" size={13}/> : <Check size={13}/>} Save
      </button>

      <div className="panel-toolbar" style={{ marginTop: 30 }}>
        <h3>POS Integration <span className="dim small">(scaffold)</span></h3>
      </div>
      <div className="cf-row">
        <label className="meta-label">PROVIDER</label>
        <select className="leads-filter" value={posProvider}
                  onChange={(e) => setPosProvider(e.target.value)}
                  data-testid="partner-pos-provider">
          {["none", "square", "toast", "clover", "lightspeed"].map((p) =>
            <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      {posProvider !== "none" && (
        <div className="cf-row">
          <label className="meta-label">EXTERNAL MERCHANT ID</label>
          <input className="lead-input"
                  value={posMid}
                  onChange={(e) => setPosMid(e.target.value)}
                  data-testid="partner-pos-mid" />
        </div>
      )}
      <button className="ghost-btn" type="button" onClick={connectPos}
                disabled={posSaving}
                data-testid="partner-pos-connect-btn">
        {posSaving ? <Loader2 className="spin-mini" size={13}/> : <Settings size={11}/>}
        Connect
      </button>
      <div className="dim small" style={{ marginTop: 10 }}>
        Note: Phase 9c stores config only. Live POS API calls (Square/Toast/Clover/Lightspeed) ship later.
      </div>
    </div>
  );
}

function ClaimBusinessModal({ onClose, onClaimed }) {
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [city, setCity] = useState("dubai");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/partner/businesses/claim`, {
        manual_business: { name, lat: Number(lat)||0, lng: Number(lng)||0, city },
      });
      toast.success("Claimed — admin verification pending");
      onClaimed();
    } catch (e) { toast.error(e.response?.data?.detail || "Claim failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className="qr-overlay" onClick={onClose}>
      <div className="qr-modal" onClick={(e) => e.stopPropagation()}
              data-testid="partner-claim-modal">
        <div className="qr-head">
          <div className="qr-code-label">Claim a business</div>
          <button type="button" onClick={onClose}
                    data-testid="partner-claim-close"
                    className="why-this-ad-close"><X size={14}/></button>
        </div>
        <div className="cf-row"><label className="meta-label">NAME</label>
          <input className="lead-input" value={name}
                  onChange={(e) => setName(e.target.value)}
                  data-testid="partner-claim-name"/></div>
        <div className="cf-row-inline">
          <input className="lead-input" placeholder="lat"
                  value={lat} onChange={(e) => setLat(e.target.value)}
                  data-testid="partner-claim-lat"/>
          <input className="lead-input" placeholder="lng"
                  value={lng} onChange={(e) => setLng(e.target.value)}
                  data-testid="partner-claim-lng"/>
        </div>
        <div className="cf-row"><label className="meta-label">CITY</label>
          <select className="leads-filter" value={city}
                    onChange={(e) => setCity(e.target.value)}
                    data-testid="partner-claim-city">
            <option value="dubai">Dubai</option>
            <option value="dfw">DFW</option>
          </select></div>
        <button className="claim-btn" type="button" onClick={submit}
                  disabled={busy || !name}
                  data-testid="partner-claim-submit">
          {busy ? <Loader2 className="spin-mini" size={13}/> : <Check size={13}/>}
          Submit
        </button>
      </div>
    </div>
  );
}

function CreateOfferModal({ biz, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    title: "", description: "", offer_type: "percent_off",
    value_amount: 20, value_currency: "AED",
    terms_text: "", max_redemptions_total: 100,
    max_per_user: 1, redeem_window_seconds: 3600,
    redemption_method: "qr_code",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/partner/businesses/${biz.business_id}/offers`, form);
      toast.success("Draft created");
      await axios.post(
        `${API}/partner/businesses/${biz.business_id}/offers/${r.data.offer_id}/submit_for_approval`);
      toast.success("Submitted for approval");
      onCreated();
    } catch (e) { toast.error(e.response?.data?.detail || "Create failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className="qr-overlay" onClick={onClose}>
      <div className="qr-modal" style={{maxWidth: 460}}
              onClick={(e) => e.stopPropagation()}
              data-testid="create-offer-modal">
        <div className="qr-head">
          <div className="qr-code-label">New offer · step {step}/3</div>
          <button type="button" onClick={onClose}
                    className="why-this-ad-close" data-testid="create-offer-close">
            <X size={14}/></button>
        </div>
        {step === 1 && (
          <>
            <div className="cf-row"><label className="meta-label">TITLE</label>
              <input className="lead-input" value={form.title}
                      onChange={(e) => setForm({...form, title: e.target.value})}
                      data-testid="offer-title-input"/></div>
            <div className="cf-row"><label className="meta-label">DESCRIPTION</label>
              <input className="lead-input" value={form.description}
                      onChange={(e) => setForm({...form, description: e.target.value})}
                      data-testid="offer-desc-input"/></div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="cf-row"><label className="meta-label">OFFER TYPE</label>
              <select className="leads-filter" value={form.offer_type}
                        onChange={(e) => setForm({...form, offer_type: e.target.value})}
                        data-testid="offer-type-select">
                {["percent_off","flat_discount","buy_one_get_one","free_item","happy_hour","prepaid_credit","sampler","sponsored_meal"].map((t) =>
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select></div>
            <div className="cf-row-inline">
              <input className="lead-input" type="number" placeholder="value"
                      value={form.value_amount}
                      onChange={(e) => setForm({...form, value_amount: Number(e.target.value)})}
                      data-testid="offer-value-input"/>
              <input className="lead-input" type="number" placeholder="inventory"
                      value={form.max_redemptions_total}
                      onChange={(e) => setForm({...form, max_redemptions_total: Number(e.target.value)})}
                      data-testid="offer-inventory-input"/>
            </div>
          </>
        )}
        {step === 3 && (
          <>
            <div className="cf-row"><label className="meta-label">TERMS</label>
              <textarea className="lead-input"
                          value={form.terms_text}
                          onChange={(e) => setForm({...form, terms_text: e.target.value})}
                          data-testid="offer-terms-input"
                          style={{minHeight: 80}}/></div>
            <div className="cf-row-inline">
              <input className="lead-input" type="number" placeholder="redeem window (s)"
                      value={form.redeem_window_seconds}
                      onChange={(e) => setForm({...form, redeem_window_seconds: Number(e.target.value)})}
                      data-testid="offer-window-input"/>
              <input className="lead-input" type="number" placeholder="max per user"
                      value={form.max_per_user}
                      onChange={(e) => setForm({...form, max_per_user: Number(e.target.value)})}
                      data-testid="offer-mpu-input"/>
            </div>
          </>
        )}
        <div className="ac-actions">
          {step > 1 && (
            <button className="ghost-btn" onClick={() => setStep(step-1)}
                      data-testid="offer-step-back">Back</button>
          )}
          {step < 3
            ? <button className="claim-btn" onClick={() => setStep(step+1)}
                          disabled={step===1 && !form.title}
                          data-testid="offer-step-next">Next</button>
            : <button className="claim-btn" onClick={submit} disabled={busy}
                          data-testid="offer-submit-btn">
                {busy ? <Loader2 className="spin-mini" size={13}/> : <Check size={13}/>}
                Submit for approval
              </button>}
        </div>
      </div>
    </div>
  );
}
