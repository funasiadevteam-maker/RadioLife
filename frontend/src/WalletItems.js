// Phase 23 Session 9 — listener Wallet items screen.
//
// Reads the new server-of-truth wallet_items collection via
// GET /api/wallet/items (from playApi.js — same-origin fetch).
// Coexists with the legacy /wallet route; new prizes saved through
// WinReveal land here.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { ChevronLeft, Wallet as WalletIcon, Loader2, Copy } from "lucide-react";
import { getWalletItems, PlayError } from "./components/playApi";

export default function WalletItems() {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getWalletItems();
        if (!cancelled) setItems(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof PlayError && err.code === "ERROR" &&
              /401/.test(err.message)) {
            navigate("/login");
            return;
          }
          setError(err.message || "Couldn't load wallet");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  const copy = async (code) => {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Code copied");
    } catch {
      toast.error("Couldn't copy");
    }
  };

  if (items === null && !error) {
    return (
      <div className="paw-loading" data-testid="wallet-items-loading">
        <Loader2 size={28} className="spin" />
      </div>
    );
  }

  return (
    <div className="game-player" data-testid="wallet-items-page"
            style={{ "--brand": "#F72585" }}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="game-player-header">
        <Link to="/wallet" className="paw-back" data-testid="wallet-items-back">
          <ChevronLeft size={14} /> wallet
        </Link>
        <div className="gp-title">
          <div className="mono sub">SAVED COUPONS</div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <WalletIcon size={22} /> Your wallet
          </h1>
        </div>
      </header>

      <main className="game-stage" style={{ paddingTop: 8 }}>
        {error && (
          <div data-testid="wallet-items-error"
                  style={{ color: "#ff6b6b", padding: 16 }}>{error}</div>
        )}
        {!error && items && items.length === 0 && (
          <div data-testid="wallet-items-empty"
                  style={{ textAlign: "center", color: "rgba(255,255,255,0.6)",
                                  padding: 32, fontSize: 14 }}>
            No saved prizes yet — play a game and tap Save to Wallet.
          </div>
        )}
        {!error && items && items.length > 0 && (
          <div data-testid="wallet-items-list"
                  style={{ display: "flex", flexDirection: "column", gap: 12,
                                  maxWidth: 480, margin: "0 auto", padding: 12 }}>
            {items.map((it) => (
              <article key={it.walletItemId}
                              data-testid={`wallet-item-${it.walletItemId}`}
                              style={{
                                background: "linear-gradient(135deg, #1c1029, #160b22)",
                                border: "1px solid rgba(247,37,133,0.25)",
                                borderRadius: 14, padding: 16,
                                display: "flex", flexDirection: "column", gap: 10,
                              }}>
                <div style={{ fontSize: 11, letterSpacing: 1.5,
                                            color: "#F72585", textTransform: "uppercase" }}>
                  {it.status === "redeemed" ? "Redeemed"
                    : it.status === "expired" ? "Expired"
                    : "Active"}
                </div>
                <div data-testid={`wallet-item-${it.walletItemId}-title`}
                        style={{ fontSize: 18, fontWeight: 800 }}>
                  {it.prizeTitle}
                </div>
                {it.code && (
                  <div onClick={() => copy(it.code)}
                          data-testid={`wallet-item-${it.walletItemId}-code`}
                          style={{
                            cursor: "pointer", display: "flex", alignItems: "center",
                            gap: 10, padding: "10px 14px", borderRadius: 10,
                            border: "1.5px dashed #F72585",
                            background: "rgba(247,37,133,0.08)",
                          }}>
                    <span style={{ fontFamily: "monospace", fontSize: 16,
                                                  letterSpacing: 2, fontWeight: 700 }}>
                      {it.code}
                    </span>
                    <Copy size={14} style={{ opacity: 0.6, marginLeft: "auto" }} />
                  </div>
                )}
                {it.redeemUrl && (
                  <a href={it.redeemUrl}
                        target="_blank" rel="noreferrer"
                        data-testid={`wallet-item-${it.walletItemId}-redeem`}
                        style={{ color: "rgba(255,255,255,0.7)",
                                        fontSize: 13, textDecoration: "underline" }}>
                    View &amp; redeem details →
                  </a>
                )}
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
                  Saved {new Date(it.savedAt).toLocaleDateString()}
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
