// Gift Inbox — "Gifts received" section for the wallet. Aggregates gifted
// gift cards, packages, and memberships via /api/shop/gifts/received.
// Gifts arrive WRAPPED — tap to unwrap with a little reveal animation.
// Renders nothing when the user has no received gifts.
import { useState, useEffect } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Gift, ArrowRight, Sparkles } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const KIND_ICON = { giftcard: "💳", package: "📦", membership: "⭐" };

const KEYFRAMES = `
@keyframes giftWobble {0%,100%{transform:rotate(0)}25%{transform:rotate(-6deg)}75%{transform:rotate(6deg)}}
@keyframes giftPop {0%{transform:scale(.9);opacity:0}60%{transform:scale(1.03)}100%{transform:scale(1);opacity:1}}
`;

const cardStyle = {
  display: "flex", alignItems: "center", gap: 12, textDecoration: "none",
  background: "rgba(23,23,27,.9)", border: "1px solid rgba(255,255,255,.08)",
  borderRadius: 12, padding: "12px 14px",
};

export default function GiftInboxSection() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState({});

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/shop/gifts/received`, { withCredentials: true });
        if (!cancel) setItems(r.data?.items || []);
      } catch { if (!cancel) setItems([]); }
    })();
    return () => { cancel = true; };
  }, []);

  if (!items.length) return null;

  return (
    <section data-testid="gift-inbox"
      style={{
        margin: "16px 0",
        background: "linear-gradient(135deg,rgba(234,88,12,.14),rgba(234,88,12,.03))",
        border: "1px solid rgba(234,88,12,.32)", borderRadius: 16, padding: 16,
      }}>
      <style>{KEYFRAMES}</style>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Gift size={16} color="#fb923c" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: ".02em" }}>
          Gifts received
        </h3>
        <span data-testid="gift-inbox-count"
          style={{
            background: "#ea580c", color: "#fff", fontSize: 11, fontWeight: 800,
            borderRadius: 999, padding: "1px 8px",
          }}>{items.length}</span>
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        {items.map((g) => {
          const key = `${g.kind}-${g.id}`;
          const revealed = !!open[key];
          if (!revealed) {
            return (
              <button key={key} type="button"
                onClick={() => setOpen((s) => ({ ...s, [key]: true }))}
                data-testid={`gift-wrapped-${g.id}`}
                style={{
                  ...cardStyle, cursor: "pointer", width: "100%", textAlign: "left",
                  border: "1px dashed rgba(234,88,12,.5)",
                  background: "linear-gradient(135deg,rgba(234,88,12,.18),rgba(23,23,27,.9))",
                }}>
                <div style={{ fontSize: 26, animation: "giftWobble 1.6s ease-in-out infinite" }}>🎁</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 800, color: "#fff", fontSize: 15 }}>A gift from {g.from_name}</div>
                  <div style={{ fontSize: 12, color: "#fdba74", display: "flex", alignItems: "center", gap: 4 }}>
                    <Sparkles size={12} /> Tap to unwrap
                  </div>
                </div>
              </button>
            );
          }
          return (
            <Link key={key} to={g.route}
              data-testid={`gift-item-${g.id}`}
              style={{ ...cardStyle, animation: "giftPop .45s cubic-bezier(.34,1.56,.64,1)" }}>
              <div style={{ fontSize: 22 }}>{KIND_ICON[g.kind] || "🎁"}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 800, color: "#fff", fontSize: 15 }}>{g.title}</div>
                {g.subtitle ? <div style={{ fontSize: 12, color: "#b4b4bb" }}>{g.subtitle}</div> : null}
                <div style={{ fontSize: 11, color: "#fb923c", marginTop: 2 }}>From {g.from_name}</div>
                {g.message ? (
                  <div style={{ fontSize: 12, color: "#d4d4d8", fontStyle: "italic", marginTop: 4 }}>
                    “{g.message}”
                  </div>
                ) : null}
              </div>
              <div style={{ color: "#fb923c", display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
                {g.action}<ArrowRight size={13} />
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
