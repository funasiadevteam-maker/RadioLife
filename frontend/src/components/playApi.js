/* ============================================================================
   playApi.js — client integration for SERVER-RESOLVED Play & Win
   ----------------------------------------------------------------------------
   This replaces the demo pickWeighted() in the game components. The server
   decides the outcome and issues the coupon; the client only animates it.

   Usage in a game:
     const keyRef = useRef(crypto.randomUUID());   // stable for one play attempt
     const outcome = await resolvePlay("lucky_reels", keyRef.current);
     // outcome = { playId, won, prizeId, prizeTitle, coupon, balance, playedAt }

   The idempotencyKey must stay the SAME across retries of one attempt, so a
   network blip + retry never produces a second resolution or a second coupon.
   ============================================================================ */

const API_BASE = ""; // same-origin; set to your API URL if different

export class PlayError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "PlayError";
    this.code = code; // "AUTH" | "NO_BALANCE" | "INELIGIBLE" | "UNAVAILABLE" | "ERROR"
  }
}

export async function resolvePlay(gameId, idempotencyKey) {
  const key = idempotencyKey || crypto.randomUUID();
  let res;
  try {
    res = await fetch(`${API_BASE}/api/play/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include", // sends auth cookie/session — or add an Authorization header
      body: JSON.stringify({ gameId, idempotencyKey: key }),
    });
  } catch {
    // network failure — caller can retry with the SAME key, safely
    throw new PlayError("ERROR", "Network error — try again");
  }

  if (!res.ok) {
    const map = { 401: "AUTH", 402: "NO_BALANCE", 403: "INELIGIBLE", 404: "UNAVAILABLE", 429: "LIMIT" };
    let detail = "";
    try {
      const j = await res.json();
      detail = j.detail;
      if (detail && typeof detail === "object") detail = detail.message || detail.code || "";
    } catch { /* ignore */ }
    throw new PlayError(map[res.status] || "ERROR", detail || `Play failed (${res.status})`);
  }
  return res.json();
}

/* ---------------------------------------------------------------------------
   VISUAL MAPS — turn a server prizeId into how each game should LOOK.
   These are cosmetic only. The authoritative result + coupon come from the
   server response. Edit these to match your game's prize catalog.
   --------------------------------------------------------------------------- */

// SPIN WHEEL: prizeId -> index in your WHEEL array (which segment to land on)
export const WHEEL_SEGMENT = {
  coffee: 0,
  try_again: 1,
  merch: 2,
  // try_again maps to any losing segment; pick one
  concert: 4,
};
export function wheelSegment(outcome) {
  const i = WHEEL_SEGMENT[outcome.prizeId];
  return i == null ? 1 : i; // fallback to a losing segment
}

// SLOT MACHINE: prizeId -> the symbol index to show as three-of-a-kind on a win
const SLOT_SYMBOL_COUNT = 6;
export const SLOT_SYMBOL = {
  coffee: 0,
  merch: 1,
  concert: 4,
};
export function slotTargets(outcome) {
  if (outcome.won) {
    const s = SLOT_SYMBOL[outcome.prizeId] ?? 0;
    return [s, s, s]; // jackpot row
  }
  // losing visual generated locally (does NOT affect the already-decided result)
  let t;
  do {
    t = [0, 1, 2].map(() => Math.floor(Math.random() * SLOT_SYMBOL_COUNT));
  } while (t[0] === t[1] && t[1] === t[2]);
  return t;
}

// SCRATCH CARD & MYSTERY BOX: just show the server's prizeTitle / won flag.
// No mapping needed — render outcome.prizeTitle in the prize layer / chosen box.

/* ---------------------------------------------------------------------------
   Helper to render the coupon after a win (call with outcome.coupon).
   --------------------------------------------------------------------------- */
export function couponMessage(outcome) {
  if (!outcome.won) return null;
  if (outcome.coupon) {
    return `Your code: ${outcome.coupon.code}`;
  }
  return "Prize secured — check your Wallet";
}

/* ---------------------------------------------------------------------------
   Save a won prize to the listener's Wallet. Idempotent on the server, so a
   double-tap or retry won't create duplicate wallet items.
   Returns: { walletItemId, prizeTitle, code, redeemUrl, savedAt, status }
   --------------------------------------------------------------------------- */
export async function saveToWallet(playId, idempotencyKey) {
  const key = idempotencyKey || crypto.randomUUID();
  let res;
  try {
    res = await fetch(`${API_BASE}/api/wallet/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ playId, idempotencyKey: key }),
    });
  } catch {
    throw new PlayError("ERROR", "Network error — try again");
  }
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch { /* ignore */ }
    throw new PlayError("ERROR", detail || `Save failed (${res.status})`);
  }
  return res.json();
}

// List the listener's saved wallet items (for the Wallet screen).
export async function getWalletItems() {
  const res = await fetch(`${API_BASE}/api/wallet/items`, { credentials: "include" });
  if (!res.ok) throw new PlayError("ERROR", `Could not load wallet (${res.status})`);
  return res.json();
}
