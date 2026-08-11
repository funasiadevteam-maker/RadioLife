// Gift Inbox — "Gifts received" section for the wallet. Aggregates gifted
// gift cards, packages, and memberships via /api/shop/gifts/received.
// Renders nothing when the user has no received gifts.
import { useState, useEffect } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Gift, ArrowRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const KIND_ICON = { giftcard: "💳", package: "📦", membership: "⭐" };

const cardStyle = {
  display: "flex", alignItems: "center", gap: 12, textDecoration: "none",
  background: "rgba(23,23,27,.9)", border: "1px solid rgba(255,255,255,.08)",
  borderRadius: 12, padding: "12px 14px",
};

export default function GiftInboxSection() {
  const [items, setItems] = useState([]);

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
        {items.map((g) => (
          <Link key={`${g.kind}-${g.id}`} to={g.route}
            data-testid={`gift-item-${g.id}`} style={cardStyle}>
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
        ))}
      </div>
    </section>
  );
}
