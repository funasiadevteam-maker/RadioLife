/** Phase 41 Session 4.5.A — Listener-facing active coupons strip.
 *
 * Renders ABOVE the station feed on `/r/:slug`. Lists every active
 * announcement that has a `coupon` attached and surfaces a prominent
 * 🎟 Claim button per row. Tapping Claim:
 *   - generates/loads the anonymous device fingerprint
 *   - POST /api/announcements/{id}/redeem
 *   - opens `<CouponClaimModal>` with the QR + code
 *
 * Auto-hides cleanly when no coupon-bearing announcements exist.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Ticket, Loader2 } from "lucide-react";
import CouponClaimModal from "@/components/CouponClaimModal";
import { getDeviceFingerprint } from "@/lib/deviceFingerprint";
import { API } from "@/AuthContext";

export default function StationActiveCoupons({ slug }) {
  const [items, setItems]   = useState([]);
  const [loading, setLoad]  = useState(false);
  const [claiming, setClaim] = useState(null);
  const [modalRow, setModalRow] = useState(null);

  const load = useCallback(async () => {
    setLoad(true);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/announcements`);
      const withCoupons = (r.data?.items || []).filter(
        (x) => x.active && x.coupon && x.coupon.code);
      setItems(withCoupons);
    } catch (e) {
      // Silent — coupon strip is optional surface.
      setItems([]);
    } finally {
      setLoad(false);
    }
  }, [slug]);

  useEffect(() => {
    let cancel = false;
    Promise.resolve().then(() => { if (!cancel) load(); });
    return () => { cancel = true; };
  }, [load]);

  const onClaim = async (ann) => {
    setClaim(ann.id);
    try {
      const device = await getDeviceFingerprint();
      const r = await axios.post(
        `${API}/announcements/${encodeURIComponent(ann.id)}/redeem`,
        { device_fingerprint: device });
      setModalRow(r.data);
      // Bump remaining counter in place so the badge updates.
      setItems((xs) => xs.map((x) => x.id === ann.id ? {
        ...x,
        coupon: x.coupon && (x.coupon.max_redemptions != null) ? {
          ...x.coupon,
          redemptions_count: (x.coupon.redemptions_count || 0)
            + (r.data?.already_redeemed ? 0 : 1),
          remaining: Math.max(0, (x.coupon.remaining ?? 0)
            - (r.data?.already_redeemed ? 0 : 1)),
        } : x.coupon,
      } : x));
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code === "redemption_cap_reached") {
        toast.error("All coupons have been claimed");
      } else if (code === "expired") {
        toast.error("This coupon has expired");
      } else if (code === "no_coupon") {
        toast.error("Coupon was removed by the owner");
      } else {
        toast.error("Could not claim coupon");
      }
    } finally {
      setClaim(null);
    }
  };

  if (loading && items.length === 0) return null;
  if (!items.length) return null;

  return (
    <div data-testid="station-active-coupons"
         style={{ marginTop: 18,
                   padding: 16, borderRadius: 14,
                   background: "linear-gradient(135deg, rgba(0,217,255,0.06), rgba(255,46,150,0.04))",
                   border: "1px solid rgba(0,217,255,0.18)" }}>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 8,
                     marginBottom: 10 }}>
        <Ticket size={14} color="#00d9ff" />
        <div style={{ fontSize: 12, fontWeight: 700,
                       color: "#cbd5e1", letterSpacing: "0.06em",
                       textTransform: "uppercase" }}>
          Active offers
        </div>
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        {items.map((a) => (
          <CouponRow key={a.id} a={a}
                      onClaim={() => onClaim(a)}
                      claiming={claiming === a.id} />
        ))}
      </div>
      <CouponClaimModal open={!!modalRow}
                          redemption={modalRow}
                          onClose={() => setModalRow(null)} />
    </div>
  );
}

function CouponRow({ a, onClaim, claiming }) {
  const c = a.coupon || {};
  const discount = c.discount_pct
    ? `${c.discount_pct}% OFF`
    : c.discount_amount_cents
      ? `$${(c.discount_amount_cents / 100).toFixed(2)} OFF`
      : "Reward";
  const remaining = c.remaining;
  const remainingText = (typeof remaining === "number")
    ? (remaining <= 0 ? "Sold out" : `${remaining} left`)
    : null;
  const soldOut = (typeof remaining === "number") && remaining <= 0;
  return (
    <div data-testid={`active-coupon-${a.id}`}
         style={{ display: "grid",
                   gridTemplateColumns: "1fr auto",
                   gap: 12, alignItems: "center", padding: 12,
                   borderRadius: 10,
                   background: "rgba(0,0,0,0.35)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8,
                       marginBottom: 4 }}>
          <span data-testid={`active-coupon-discount-${a.id}`}
                style={{ fontSize: 18, fontWeight: 800, color: "#fff" }}>
            {discount}
          </span>
          <span style={{ fontFamily: "monospace", fontSize: 12,
                          color: "#00d9ff",
                          background: "rgba(0,217,255,0.08)",
                          padding: "2px 8px", borderRadius: 4,
                          border: "1px solid rgba(0,217,255,0.3)",
                          letterSpacing: "0.06em" }}>
            {c.code}
          </span>
          {remainingText && (
            <span data-testid={`active-coupon-remaining-${a.id}`}
                  style={{ fontSize: 10, color: soldOut ? "#fb7185" : "#9aa3af",
                            fontWeight: 600,
                            background: "rgba(255,255,255,0.04)",
                            padding: "2px 6px", borderRadius: 4,
                            border: "1px solid rgba(255,255,255,0.06)" }}>
              {remainingText}
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: "#cbd5e1",
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}>
          {a.message}
        </div>
      </div>
      <button data-testid={`active-coupon-claim-${a.id}`}
              onClick={onClaim}
              disabled={claiming || soldOut}
              style={{ display: "inline-flex", alignItems: "center", gap: 6,
                        background: soldOut
                          ? "rgba(255,255,255,0.04)"
                          : "linear-gradient(135deg, #00d9ff, #0099bb)",
                        color: soldOut ? "#6b7280" : "#0b0b0b",
                        border: "none",
                        padding: "10px 16px", borderRadius: 8,
                        fontSize: 13, fontWeight: 700,
                        cursor: soldOut ? "not-allowed" : "pointer",
                        opacity: claiming ? 0.6 : 1 }}>
        {claiming
          ? <><Loader2 size={13} className="spin" /> Claiming…</>
          : (soldOut ? "Sold out" : <><Ticket size={13} /> Claim</>)}
      </button>
    </div>
  );
}
