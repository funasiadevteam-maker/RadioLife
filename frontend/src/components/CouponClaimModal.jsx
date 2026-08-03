/** Phase 41 Session 4.5.A — Coupon claim modal.
 *
 * Used by:
 *   - StationActiveCoupons.jsx  (listener-facing "Claim" button)
 *   - Wallet Coupons tab        (re-view a previously claimed code)
 *
 * Displays the coupon code, discount, QR (from `qr_payload`), terms,
 * and an "Add to wallet" copy CTA. Closes on backdrop click or X.
 */
import React, { useEffect } from "react";
import { X, Ticket, Copy, CheckCircle2 } from "lucide-react";
import QRCode from "react-qr-code";
import { toast } from "sonner";

function formatExpiresAt(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(undefined,
      { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return null; }
}

export default function CouponClaimModal({ open, redemption, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !redemption) return null;

  const expiresText = formatExpiresAt(redemption.expires_at);

  const discountLabel = redemption.discount_pct
    ? `${redemption.discount_pct}% OFF`
    : redemption.discount_amount_cents
      ? `$${(redemption.discount_amount_cents / 100).toFixed(2)} OFF`
      : "Reward";

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(redemption.coupon_code || "");
      toast.success("Code copied to clipboard");
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div data-testid="coupon-claim-modal"
         role="dialog" aria-modal="true"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
         style={{ position: "fixed", inset: 0, zIndex: 600,
                   background: "rgba(0,0,0,0.7)",
                   backdropFilter: "blur(8px)",
                   display: "grid", placeItems: "center",
                   padding: 16 }}>
      <div style={{ background: "#0f0f12",
                     border: "1px solid rgba(0,217,255,0.4)",
                     borderRadius: 16, padding: 24,
                     maxWidth: 380, width: "100%",
                     boxShadow: "0 30px 60px rgba(0,0,0,0.6)",
                     position: "relative" }}>
        <button data-testid="coupon-modal-close"
                onClick={onClose}
                style={{ position: "absolute", top: 12, right: 12,
                          background: "rgba(255,255,255,0.06)",
                          border: "1px solid rgba(255,255,255,0.1)",
                          color: "#cbd5e1", borderRadius: 999,
                          width: 32, height: 32, display: "grid",
                          placeItems: "center", cursor: "pointer" }}>
          <X size={14} />
        </button>

        <div style={{ display: "inline-flex", alignItems: "center", gap: 6,
                       background: "rgba(0,217,255,0.12)",
                       color: "#00d9ff", border: "1px solid rgba(0,217,255,0.4)",
                       padding: "4px 12px", borderRadius: 999,
                       fontSize: 11, fontWeight: 700,
                       letterSpacing: "0.06em", textTransform: "uppercase",
                       marginBottom: 14 }}>
          <Ticket size={11} /> Coupon claimed
        </div>

        <div data-testid="coupon-modal-discount"
             style={{ fontSize: 36, fontWeight: 800, color: "#fff",
                       lineHeight: 1, marginBottom: 4 }}>
          {discountLabel}
        </div>
        {redemption.station_name && (
          <div data-testid="coupon-modal-station"
               style={{ fontSize: 13, color: "#9aa3af", marginBottom: 18 }}>
            at {redemption.station_name}
          </div>
        )}

        {/* QR + Code */}
        <div style={{ background: "#fff", padding: 12,
                       borderRadius: 12, marginBottom: 14,
                       display: "grid", placeItems: "center" }}>
          <QRCode value={redemption.qr_payload || redemption.coupon_code || "BIGFM"}
                  size={180} fgColor="#0b0b0b" bgColor="#ffffff"
                  data-testid="coupon-modal-qr" />
        </div>

        <button data-testid="coupon-modal-copy-code"
                onClick={copyCode}
                style={{ width: "100%",
                          background: "rgba(0,217,255,0.08)",
                          border: "1px solid rgba(0,217,255,0.4)",
                          color: "#00d9ff",
                          padding: "10px 14px", borderRadius: 10,
                          display: "inline-flex", alignItems: "center",
                          justifyContent: "center", gap: 8,
                          fontFamily: "monospace", fontSize: 18,
                          fontWeight: 700, letterSpacing: "0.08em",
                          cursor: "pointer", marginBottom: 14 }}>
          {redemption.coupon_code} <Copy size={14} />
        </button>

        {redemption.terms && (
          <div style={{ fontSize: 11, color: "#9aa3af",
                          background: "rgba(255,255,255,0.03)",
                          border: "1px solid rgba(255,255,255,0.05)",
                          padding: 10, borderRadius: 8,
                          lineHeight: 1.5, marginBottom: 10 }}>
            {redemption.terms}
          </div>
        )}

        {expiresText && (
          <div style={{ fontSize: 11, color: "#9aa3af",
                          display: "inline-flex", alignItems: "center", gap: 4 }}>
            <CheckCircle2 size={11} /> Show this to redeem · expires {expiresText}
          </div>
        )}
      </div>
    </div>
  );
}
