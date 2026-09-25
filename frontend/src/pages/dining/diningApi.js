// FUUSIC Premium Dining Club — shared web API client + brand tokens.
// Cookie-auth (withCredentials) against the shared FastAPI backend.
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const http = axios.create({ baseURL: API, withCredentials: true });

// Dining Club neon "Dubai club" palette (aligned to design_guidelines.json).
export const DINE = {
  bg: "#0a0c18",
  panel: "#12162a",
  card: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.10)",
  pink: "#ff2d95",
  cyan: "#00d9ff",
  gold: "#ffd700",
  text: "#f5f7ff",
  muted: "#9aa3c7",
};

export const money = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;

const unwrap = (p) => p.then((r) => r.data);

export const diningApi = {
  home: () => unwrap(http.get("/dining-club")),
  subscribe: (body) => unwrap(http.post("/dining-club/subscribe", { ...body, origin_url: window.location.origin })),
  subscribeStatus: (sid) => unwrap(http.get(`/dining-club/subscribe/status/${sid}`)),
  credits: () => unwrap(http.get("/dining-club/credits")),
  start: (body) => unwrap(http.post("/dining-club/selection/start", body)),
  view: (id) => unwrap(http.get(`/dining-club/selection/${id}`)),
  spin: (id) => unwrap(http.post(`/dining-club/selection/${id}/spin`)),
  surprise: (id) => unwrap(http.post(`/dining-club/selection/${id}/random`)),
  reroll: (id) => unwrap(http.post(`/dining-club/selection/${id}/reroll`)),
  accept: (id) => unwrap(http.post(`/dining-club/selection/${id}/accept`)),
  abandon: (id) => unwrap(http.post(`/dining-club/selection/${id}/abandon`)),
  checkout: (order_id) =>
    unwrap(http.post("/dining-club/checkout", { order_id, origin_url: window.location.origin })),
  checkoutStatus: (sid) => unwrap(http.get(`/dining-club/checkout/status/${sid}`)),
  pass: (orderId) => unwrap(http.get(`/dining-club/pass/${orderId}`)),

  // Roll-a-Dice promo
  diceStatus: () => unwrap(http.get("/dining-club/dice")),
  diceRoll: () => unwrap(http.post("/dining-club/dice/roll")),

  // Merchant
  merchantMe: () => unwrap(http.get("/merchant/dining-club/me")),
  merchantEnroll: (body) => unwrap(http.post("/merchant/dining-club/enroll", { ...body, origin_url: window.location.origin })),
  merchantConnectLink: () => unwrap(http.post("/merchant/dining-club/connect/link", { origin_url: window.location.origin })),
  merchantAddLocation: (body) => unwrap(http.post("/merchant/dining-club/locations", body)),
  merchantSetCapacity: (id, capacity) => unwrap(http.put(`/merchant/dining-club/locations/${id}/capacity`, { capacity })),
  merchantSetMeals: (id, meals) => unwrap(http.post(`/merchant/dining-club/locations/${id}/meals`, { meals })),
  merchantAnalytics: () => unwrap(http.get("/merchant/dining-club/analytics")),
  merchantWebhooks: () => unwrap(http.get("/merchant/dining-club/webhooks")),
  merchantAddWebhook: (body) => unwrap(http.post("/merchant/dining-club/webhooks", body)),
  merchantDeleteWebhook: (id) => unwrap(http.delete(`/merchant/dining-club/webhooks/${id}`)),
};

export function errCode(e) {
  return e?.response?.data?.detail?.code || e?.response?.data?.code || e?.message || "error";
}
