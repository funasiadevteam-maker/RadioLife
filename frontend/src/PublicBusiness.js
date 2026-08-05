// Phase 9c — Public business profile (/business/:slug).  Works logged-
// out; claim CTA reveals when there's a session, otherwise redirects
// to /login first.
import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, Marker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "@/AuthContext";
import { MapPin, Clock, Phone, Tag, ChevronRight,
          ExternalLink, Loader2, Gift, Share2 } from "lucide-react";
import "@/PublicBusiness.css";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function pinIcon() {
  return L.divIcon({
    className: "leaflet-divicon-wrap",
    html: '<div class="leaflet-pin" style="background:#ff2d95"></div>',
  });
}

export default function PublicBusiness() {
  const { slug } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [biz, setBiz] = useState(null);
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [claimingId, setClaimingId] = useState(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [b, o] = await Promise.all([
          axios.get(`${API}/public/businesses/${slug}`),
          axios.get(`${API}/public/businesses/${slug}/offers`),
        ]);
        if (!mounted) return;
        setBiz(b.data);
        setOffers(o.data.items || []);
      } catch (e) {
        toast.error("Couldn't load business");
      } finally { if (mounted) setLoading(false); }
    })();
    return () => { mounted = false; };
  }, [slug]);

  const claim = async (offerId) => {
    if (!user) {
      navigate(`/login?next=/business/${slug}`);
      return;
    }
    setClaimingId(offerId);
    try {
      const r = await axios.post(
        `${API}/commerce/offers/${offerId}/claim`,
        { claim_source: "public_page" });
      toast.success(`Claimed! Code: ${r.data.redemption_code}`);
      navigate("/wallet/coupons");
    } catch (e) {
      const msg = e.response?.data?.detail || "Couldn't claim";
      toast.error(msg);
    } finally { setClaimingId(null); }
  };

  const share = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ title: biz.name, url }); } catch {}
    } else {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    }
  };

  const hours = useMemo(() => {
    const h = biz?.hours_json || {};
    return Object.entries(h);
  }, [biz]);

  if (loading) {
    return (
      <div className="biz-shell"><div className="paw-loading">
        <Loader2 className="spin" /></div></div>
    );
  }
  if (!biz) {
    return <div className="biz-shell"><div className="paw-loading">Business not found</div></div>;
  }

  return (
    <div className="biz-shell" data-testid="public-business-shell">
      <div className="biz-cover" style={{
        backgroundImage: biz.cover_image_url
          ? `linear-gradient(180deg, rgba(0,0,0,0.20) 0%, #0a0d12 100%), url(${biz.cover_image_url})`
          : `linear-gradient(135deg, rgba(255,45,149,0.35), rgba(216,37,255,0.20)), #0a0d12`,
      }}>
        <Link to="/" className="biz-back" data-testid="biz-back-link">
          <ChevronRight size={14} style={{ transform: "rotate(180deg)" }} /> RadioLife
        </Link>
        <button type="button" onClick={share} className="biz-share-btn"
                  data-testid="biz-share-btn">
          <Share2 size={14} /> Share
        </button>
      </div>
      <div className="biz-body">
        <div className="biz-head">
          {biz.logo_url
            ? <img src={biz.logo_url} alt="" className="biz-logo" />
            : <div className="biz-logo placeholder">
                {(biz.name || "?").slice(0,1).toUpperCase()}
              </div>}
          <div className="biz-head-text">
            <h1 data-testid="biz-name">{biz.name}</h1>
            {biz.tagline && <div className="biz-tagline">{biz.tagline}</div>}
            <div className="biz-meta">
              {biz.category && <span className="biz-chip"><Tag size={11}/> {biz.category}</span>}
              {biz.rating != null && <span className="biz-chip">★ {biz.rating}</span>}
              {biz.partner_status === "verified" && (
                <span className="biz-chip verified" data-testid="biz-verified-chip">
                  Verified Partner
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="biz-grid">
          <section className="biz-section">
            <h3>About</h3>
            <p className="biz-desc">
              {biz.description || (
                <span className="dim">No description yet.</span>)}
            </p>
            {biz.address && (
              <div className="biz-info-row">
                <MapPin size={14} /> <span>{biz.address}</span>
              </div>
            )}
            {biz.phone && (
              <div className="biz-info-row">
                <Phone size={14} /> <span>{biz.phone}</span>
              </div>
            )}
            {hours.length > 0 && (
              <div className="biz-hours">
                <div className="biz-hours-head"><Clock size={13} /> Hours</div>
                {hours.map(([day, val]) => (
                  <div key={day} className="biz-hours-row">
                    <span className="dim small">{day}</span>
                    <span className="mono small">
                      {typeof val === "string" ? val : (val?.open ? `${val.open}-${val.close}` : "closed")}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="biz-section">
            <h3>Live Offers
              {offers.length > 0 && (
                <span className="biz-count-pill" data-testid="offers-count-pill">
                  {offers.length}
                </span>
              )}
            </h3>
            {offers.length === 0 ? (
              <div className="biz-empty">No active offers right now. Check back later.</div>
            ) : (
              <div className="offer-list">
                {offers.map((o) => (
                  <div className="offer-card" key={o.offer_id}
                        data-testid={`offer-card-${o.offer_id}`}>
                    {o.image_url && (
                      <img src={o.image_url} alt="" className="offer-img" />
                    )}
                    <div className="offer-body">
                      <div className="offer-title">{o.title}</div>
                      {o.description && (
                        <div className="offer-desc dim small">{o.description}</div>
                      )}
                      <div className="offer-chips">
                        <span className="biz-chip"><Gift size={11}/> {o.offer_type.replace(/_/g, " ")}</span>
                        {o.value_amount > 0 && (
                          <span className="biz-chip">
                            {o.offer_type === "percent_off"
                              ? `${o.value_amount}% off`
                              : `${o.value_amount} ${o.value_currency || "AED"}`}
                          </span>
                        )}
                        {o.inventory_remaining != null && (
                          <span className="biz-chip">
                            {o.inventory_remaining} left
                          </span>
                        )}
                      </div>
                      {o.terms_text && (
                        <div className="offer-terms dim small">{o.terms_text}</div>
                      )}
                      <button className="claim-btn"
                                onClick={() => claim(o.offer_id)}
                                disabled={claimingId === o.offer_id}
                                data-testid={`offer-claim-${o.offer_id}`}>
                        {claimingId === o.offer_id
                          ? <Loader2 size={13} className="spin-mini" />
                          : <Gift size={13} />}
                        Claim coupon
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="biz-section biz-map-section">
            <h3>Where</h3>
            {biz.lat != null && biz.lng != null && (
              <MapContainer center={[biz.lat, biz.lng]} zoom={15}
                                scrollWheelZoom={false}
                                className="biz-leaflet">
                <TileLayer
                  attribution="© OSM"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <Marker position={[biz.lat, biz.lng]} icon={pinIcon()} />
              </MapContainer>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
