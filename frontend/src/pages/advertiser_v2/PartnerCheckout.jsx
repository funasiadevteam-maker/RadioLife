// Advertiser dashboard — "API Checkout" console.
// Buy sponsorships (Trivia, AI-RJ read) and marketplace promotions (Promoted
// rail, Category Spotlight) through the Partner API, and watch checkout status
// flip to paid/active — no curl. Cookie-authed via /api/partner/commerce/*.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Rocket, Sparkles, Radio, Store, Loader2, ExternalLink, RefreshCw,
  Play, BarChart3, CheckCircle2, KeyRound, Star, Clock, Wallet,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

function EnvToggle({ env, setEnv }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-300 overflow-hidden" data-testid="pc-env-toggle">
      {["sandbox", "live"].map((e) => (
        <button key={e} onClick={() => setEnv(e)} data-testid={`pc-env-${e}`}
          className={`px-3 py-1.5 text-xs font-black ${env === e ? (e === "live" ? "bg-green-600 text-white" : "bg-slate-900 text-white") : "bg-white text-slate-500"}`}>
          {e === "live" ? "LIVE" : "SANDBOX"}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="flex-1 min-w-[140px]">
      <label className="block text-[11px] font-bold text-slate-400 mb-1">{label}</label>
      {children}
    </div>
  );
}
const inputCls = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";

function StatusBadge({ status }) {
  if (!status) return null;
  const good = ["active", "credited", "paid"].includes(status);
  const warn = ["pending_review", "pending_payment", "pending_moderation", "rendering"].includes(status);
  const cls = good ? "bg-green-100 text-green-700" : warn ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500";
  return <span data-testid="pc-status-badge" className={`text-[11px] font-black px-2.5 py-1 rounded-full ${cls}`}>{status}</span>;
}

// Renders a checkout result: sandbox → activated; live → open link + poll.
function CheckoutResult({ result, onCheck, checking, testid }) {
  if (!result) return null;
  if (result.sandbox || result.checkout_required === false) {
    return (
      <div className="mt-3 flex items-center gap-2 text-sm font-bold text-green-700" data-testid={`${testid}-sandbox`}>
        <CheckCircle2 className="w-4 h-4" /> Activated instantly (sandbox) — <StatusBadge status={result.status || "active"} />
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3" data-testid={`${testid}-live`}>
      <div className="flex flex-wrap items-center gap-2">
        {result.checkout_url && (
          <a href={result.checkout_url} target="_blank" rel="noreferrer" data-testid={`${testid}-open`}
            className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm">
            <ExternalLink className="w-4 h-4" /> Open Stripe Checkout ({money(result.amount_cents)})
          </a>
        )}
        <button onClick={onCheck} disabled={checking} data-testid={`${testid}-check`}
          className="inline-flex items-center gap-1.5 bg-slate-900 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
          {checking ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} I&apos;ve paid — check status
        </button>
        <StatusBadge status={result.status} />
      </div>
      <p className="text-[11px] text-slate-400 mt-2">Pay on the Stripe page (test card 4242 4242 4242 4242), then tap “check status”.</p>
    </div>
  );
}

function SectionCard({ icon: Icon, title, desc, children, testid }) {
  return (
    <section className="rounded-2xl border border-slate-200 p-5 mb-4" data-testid={testid}>
      <div className="flex items-center gap-2"><Icon className="w-5 h-5 text-slate-800" /><h2 className="font-black text-slate-900">{title}</h2></div>
      <p className="text-xs text-slate-500 mt-0.5 mb-3">{desc}</p>
      {children}
    </section>
  );
}

export default function PartnerCheckout() {
  const [env, setEnv] = useState("sandbox");
  const [loading, setLoading] = useState(true);
  const [hasAccount, setHasAccount] = useState(true);
  const [catalog, setCatalog] = useState({ tiers: [], categories: [], businesses: [], personas: [] });
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [favPersona, setFavPersona] = useState(null);

  // flow state
  const [promo, setPromo] = useState({ business_id: "", tier: "spotlight_7", busy: false, result: null, checking: false, report: null });
  const [spot, setSpot] = useState({ business_id: "", category: "", bid: 25, budget: 2000, busy: false, result: null, checking: false });
  const [triv, setTriv] = useState({ display_name: "Brand Trivia Night", points: 500, busy: false, sponsorship_id: null, advertiser_id: null, result: null, checking: false });
  const [rjr, setRjr] = useState({ persona_id: "", product_name: "Acme Cola", key_message: "Crisp & refreshing", cta: "Try one today", plays: 20, cpp: 8, busy: false, sponsorship_id: null, advertiser_id: null, result: null, checking: false, previewId: null, previewUrl: null });

  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const loadSummary = useCallback(async () => {
    try { const r = await axios.get(`${API}/partner/commerce/analytics/summary`); setSummary(r.data); } catch { /* ignore */ }
  }, []);
  const loadHistory = useCallback(async () => {
    setHistoryBusy(true);
    try { const r = await axios.get(`${API}/partner/commerce/history`); setHistory(r.data.items || []); }
    catch { /* ignore */ } finally { setHistoryBusy(false); }
  }, []);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/partner/commerce/catalog`);
      setCatalog(r.data);
      setHasAccount(true);
      const fav = r.data.favourite_persona_id || null;
      setFavPersona(fav);
      setPromo((s) => ({ ...s, business_id: s.business_id || r.data.businesses?.[0]?.business_id || "" }));
      setSpot((s) => ({ ...s, business_id: s.business_id || r.data.businesses?.[0]?.business_id || "", category: s.category || r.data.categories?.[0]?.key || "" }));
      setRjr((s) => ({ ...s, persona_id: s.persona_id || fav || r.data.personas?.[0]?.id || "" }));
      loadSummary();
      loadHistory();
    } catch (e) {
      if (e?.response?.status === 400) setHasAccount(false);
      else toast.error("Could not load catalog");
    } finally { setLoading(false); }
  }, [loadSummary, loadHistory]);
  useEffect(() => { loadCatalog(); }, [loadCatalog]);

  const afterBuy = () => { loadSummary(); loadHistory(); };

  const toggleFav = async (personaId) => {
    const next = favPersona === personaId ? null : personaId;
    setFavPersona(next);
    if (next) setRjr((s) => ({ ...s, persona_id: next }));
    try { await axios.post(`${API}/partner/commerce/voice-favourite`, { persona_id: next }); toast.success(next ? "Favourite voice saved" : "Favourite cleared"); }
    catch { toast.error("Could not save favourite"); }
  };

  // ── Promotion ──
  const buyPromo = async () => {
    setPromo((s) => ({ ...s, busy: true, result: null, report: null }));
    try {
      const r = await axios.post(`${API}/partner/commerce/promotion/checkout`,
        { business_id: promo.business_id, tier: promo.tier, environment: env, origin_url: origin });
      setPromo((s) => ({ ...s, result: r.data }));
      if (r.data.sandbox) toast.success("Promotion live (sandbox)");
    } catch { toast.error("Checkout failed"); }
    finally { setPromo((s) => ({ ...s, busy: false })); afterBuy(); }
  };
  const checkPromo = async () => {
    if (!promo.result?.promotion_id) return;
    setPromo((s) => ({ ...s, checking: true }));
    try {
      const r = await axios.get(`${API}/partner/commerce/promotion/${promo.result.promotion_id}/status`, { params: { environment: env } });
      setPromo((s) => ({ ...s, result: { ...s.result, status: r.data.status } }));
      toast[r.data.paid ? "success" : "info"](r.data.paid ? `Paid — ${r.data.status}` : "Not paid yet");
    } catch { toast.error("Status check failed"); }
    finally { setPromo((s) => ({ ...s, checking: false })); }
  };
  const loadReport = async () => {
    if (!promo.result?.promotion_id) return;
    try {
      const r = await axios.get(`${API}/partner/commerce/promotion/${promo.result.promotion_id}/report`, { params: { environment: env } });
      setPromo((s) => ({ ...s, report: r.data }));
    } catch { toast.error("No report yet"); }
  };

  // ── Spotlight ──
  const buySpot = async () => {
    setSpot((s) => ({ ...s, busy: true, result: null }));
    try {
      const r = await axios.post(`${API}/partner/commerce/spotlight/checkout`,
        { business_id: spot.business_id, category: spot.category, bid_cents: Number(spot.bid), amount_cents: Number(spot.budget), environment: env, origin_url: origin });
      setSpot((s) => ({ ...s, result: r.data }));
      if (r.data.sandbox) toast.success("Spotlight funded (sandbox)");
    } catch { toast.error("Checkout failed"); }
    finally { setSpot((s) => ({ ...s, busy: false })); afterBuy(); }
  };
  const checkSpot = async () => {
    if (!spot.result?.session_id) return;
    setSpot((s) => ({ ...s, checking: true }));
    try {
      const r = await axios.get(`${API}/partner/commerce/spotlight/${spot.result.session_id}/status`, { params: { environment: env } });
      setSpot((s) => ({ ...s, result: { ...s.result, status: r.data.status } }));
      toast[r.data.status === "credited" ? "success" : "info"](r.data.status === "credited" ? `Funded ${money(r.data.budget_cents)}` : "Not paid yet");
    } catch { toast.error("Status check failed"); }
    finally { setSpot((s) => ({ ...s, checking: false })); }
  };

  // ── Trivia ──
  const buyTriv = async () => {
    setTriv((s) => ({ ...s, busy: true, result: null }));
    try {
      const c = await axios.post(`${API}/partner/commerce/sponsorships`, {
        type: "trivia", environment: env, display_name: triv.display_name,
        sponsor_target_type: "any", winner_selection: "top_n",
        prize_pool: [{ rank: 1, points_reward: Number(triv.points), currency: "bc", quantity: 1 }],
        start_at: new Date(Date.now() + 12e4).toISOString(), end_at: new Date(Date.now() + 30 * 864e5).toISOString(),
      });
      const sid = c.data.sponsorship_id, aid = c.data.advertiser_id;
      if (env === "sandbox") { setTriv((s) => ({ ...s, sponsorship_id: sid, advertiser_id: aid, result: { sandbox: true, status: "active" } })); toast.success("Trivia live (sandbox)"); return; }
      const k = await axios.post(`${API}/partner/commerce/sponsorships/${sid}/checkout`, { type: "trivia", advertiser_id: aid, environment: env, origin_url: origin });
      setTriv((s) => ({ ...s, sponsorship_id: sid, advertiser_id: aid, result: k.data }));
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Booking failed"); }
    finally { setTriv((s) => ({ ...s, busy: false })); afterBuy(); }
  };
  const checkTriv = async () => {
    if (!triv.sponsorship_id) return;
    setTriv((s) => ({ ...s, checking: true }));
    try {
      const r = await axios.get(`${API}/partner/commerce/sponsorships/${triv.sponsorship_id}/checkout/status`, { params: { type: "trivia", advertiser_id: triv.advertiser_id, environment: env } });
      setTriv((s) => ({ ...s, result: { ...s.result, status: r.data.status } }));
      toast[r.data.paid ? "success" : "info"](r.data.paid ? `Paid — ${r.data.status}` : "Not paid yet");
    } catch { toast.error("Status check failed"); }
    finally { setTriv((s) => ({ ...s, checking: false })); }
  };

  // ── AI-RJ read ──
  const previewVoice = async (personaId) => {
    setRjr((s) => ({ ...s, previewId: personaId, previewUrl: null }));
    try {
      const r = await axios.post(`${API}/partner/commerce/personas/${personaId}/preview`);
      setRjr((s) => ({ ...s, previewUrl: r.data.audio_url }));
      const a = new Audio(r.data.audio_url); a.play().catch(() => {});
      toast.success(r.data.cached ? "Playing sample" : "Generated & playing");
    } catch (e) { toast.error(e?.response?.data?.detail?.code === "elevenlabs_api_key_missing" ? "Voice not configured" : "Preview failed"); }
    finally { setRjr((s) => ({ ...s, previewId: null })); }
  };
  const buyRjr = async () => {
    setRjr((s) => ({ ...s, busy: true, result: null }));
    try {
      const c = await axios.post(`${API}/partner/commerce/sponsorships`, {
        type: "rj_read", environment: env, persona_id: rjr.persona_id, any_station: true,
        disclosure_prefix: "Sponsored by", plays_target: Number(rjr.plays), cost_per_play_cents: Number(rjr.cpp),
        product_name: rjr.product_name, key_message: rjr.key_message, cta: rjr.cta, script_body: "auto",
        start_at: new Date(Date.now() + 12e4).toISOString(), end_at: new Date(Date.now() + 30 * 864e5).toISOString(),
      });
      const sid = c.data.sponsorship_id, aid = c.data.advertiser_id;
      if (env === "sandbox") { setRjr((s) => ({ ...s, sponsorship_id: sid, advertiser_id: aid, result: { sandbox: true, status: "active" } })); toast.success("Read booked (sandbox)"); return; }
      await axios.post(`${API}/partner/commerce/sponsorships/${sid}/submit`, {
        type: "rj_read", advertiser_id: aid, environment: env,
        final_script: `Sponsored by ${rjr.product_name}. ${rjr.key_message} — ${rjr.cta}, only on FUUSIC.`,
      });
      const k = await axios.post(`${API}/partner/commerce/sponsorships/${sid}/checkout`, { type: "rj_read", advertiser_id: aid, environment: env, origin_url: origin });
      setRjr((s) => ({ ...s, sponsorship_id: sid, advertiser_id: aid, result: k.data }));
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Booking failed"); }
    finally { setRjr((s) => ({ ...s, busy: false })); afterBuy(); }
  };
  const checkRjr = async () => {
    if (!rjr.sponsorship_id) return;
    setRjr((s) => ({ ...s, checking: true }));
    try {
      const r = await axios.get(`${API}/partner/commerce/sponsorships/${rjr.sponsorship_id}/checkout/status`, { params: { type: "rj_read", advertiser_id: rjr.advertiser_id, environment: env } });
      setRjr((s) => ({ ...s, result: { ...s.result, status: r.data.status } }));
      toast[r.data.paid ? "success" : "info"](r.data.paid ? `Paid — ${r.data.status}` : "Not paid yet");
    } catch { toast.error("Status check failed"); }
    finally { setRjr((s) => ({ ...s, checking: false })); }
  };

  if (loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin inline" /></div>;

  if (!hasAccount) return (
    <div className="max-w-2xl rounded-2xl border border-slate-200 p-6 text-center" data-testid="pc-no-account">
      <KeyRound className="w-8 h-8 text-slate-400 mx-auto mb-2" />
      <h1 className="text-xl font-black text-slate-900">Set up your developer account first</h1>
      <p className="text-sm text-slate-500 mt-1">Create your Partner account on the “API &amp; Keys” page, then come back here to buy programmatically.</p>
      <a href="/advertiser/dashboard/api" className="inline-block mt-3 bg-orange-600 text-white font-black rounded-lg px-5 py-2.5 text-sm">Go to API &amp; Keys</a>
    </div>
  );

  const bizOptions = (catalog.businesses || []);

  return (
    <div className="max-w-3xl" data-testid="partner-checkout-page">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Rocket className="w-6 h-6 text-slate-900" />
          <h1 className="text-2xl font-black text-slate-900">API Checkout</h1>
        </div>
        <EnvToggle env={env} setEnv={setEnv} />
      </div>
      <p className="text-sm text-slate-500 mb-5">Buy sponsorships &amp; marketplace promotions programmatically and watch checkout status — no code. Sandbox activates instantly; Live opens a real Stripe checkout.</p>

      {summary && (
        <section className="rounded-2xl border border-slate-200 p-4 mb-4" data-testid="pc-summary">
          <div className="flex items-center gap-1.5 mb-2"><Wallet className="w-4 h-4 text-slate-700" /><h2 className="font-black text-slate-900 text-sm">Spend &amp; performance (all promotions)</h2></div>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {[["Promotions", summary.promotions], ["Active", summary.active_promotions], ["Pending", summary.pending_promotions], ["Impressions", summary.impressions], ["Orders", summary.orders], ["Revenue", money(summary.revenue_cents)], ["Placement", money(summary.placement_spend_cents)], ["Spotlight", money(summary.spotlight_spend_cents)], ["Total spend", money(summary.total_spend_cents)]].map(([l, v]) => (
              <div key={l} className="rounded-lg bg-slate-50 border border-slate-100 p-2"><div className="text-[10px] font-bold text-slate-400">{l}</div><div className="text-sm font-black text-slate-900">{v ?? 0}</div></div>
            ))}
          </div>
        </section>
      )}

      {/* Marketplace Promotion */}
      <SectionCard icon={Store} title="Promoted-rail placement" testid="pc-promo-card"
        desc="Boost a listed shop in Shop search + the Promoted rail. Live buys enter admin review before going live.">
        <div className="flex flex-wrap gap-2 items-end">
          <Field label="Business">
            <select value={promo.business_id} onChange={(e) => setPromo((s) => ({ ...s, business_id: e.target.value }))} data-testid="pc-promo-biz" className={inputCls}>
              {bizOptions.map((b) => <option key={b.business_id} value={b.business_id}>{b.public_name || b.business_id}</option>)}
            </select>
          </Field>
          <Field label="Tier">
            <select value={promo.tier} onChange={(e) => setPromo((s) => ({ ...s, tier: e.target.value }))} data-testid="pc-promo-tier" className={inputCls}>
              {(catalog.tiers || []).map((t) => <option key={t.tier} value={t.tier}>{t.name} · {t.days}d · {money(t.price_cents)}</option>)}
            </select>
          </Field>
          <button onClick={buyPromo} disabled={promo.busy || !promo.business_id} data-testid="pc-promo-buy"
            className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
            {promo.busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />} Buy placement
          </button>
        </div>
        <CheckoutResult result={promo.result} onCheck={checkPromo} checking={promo.checking} testid="pc-promo-result" />
        {promo.result && (promo.result.status === "active" || promo.result.status === "pending_review" || promo.result.sandbox) && (
          <div className="mt-3">
            <button onClick={loadReport} data-testid="pc-promo-report-btn" className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-700 hover:text-slate-900"><BarChart3 className="w-4 h-4" /> View analytics</button>
            {promo.report && (
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-2" data-testid="pc-promo-report">
                {[["Impr.", promo.report.impressions], ["Views", promo.report.views], ["Orders", promo.report.orders], ["Revenue", money(promo.report.revenue_cents)], ["Spend", money(promo.report.total_spend_cents)], ["Spotlight impr.", promo.report.spotlight_impressions]].map(([l, v]) => (
                  <div key={l} className="rounded-lg bg-slate-50 border border-slate-100 p-2"><div className="text-[10px] font-bold text-slate-400">{l}</div><div className="text-sm font-black text-slate-900">{v ?? 0}</div></div>
                ))}
              </div>
            )}
          </div>
        )}
      </SectionCard>

      {/* Category Spotlight */}
      <SectionCard icon={Sparkles} title="Category Spotlight" testid="pc-spot-card"
        desc="Bid per impression to top a category. Prepay a budget; billed as it serves.">
        <div className="flex flex-wrap gap-2 items-end">
          <Field label="Business">
            <select value={spot.business_id} onChange={(e) => setSpot((s) => ({ ...s, business_id: e.target.value }))} data-testid="pc-spot-biz" className={inputCls}>
              {bizOptions.map((b) => <option key={b.business_id} value={b.business_id}>{b.public_name || b.business_id}</option>)}
            </select>
          </Field>
          <Field label="Category">
            <select value={spot.category} onChange={(e) => setSpot((s) => ({ ...s, category: e.target.value }))} data-testid="pc-spot-cat" className={inputCls}>
              {(catalog.categories || []).map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Bid (¢/impr)"><input type="number" value={spot.bid} onChange={(e) => setSpot((s) => ({ ...s, bid: e.target.value }))} data-testid="pc-spot-bid" className={inputCls} /></Field>
          <Field label="Budget (¢)"><input type="number" value={spot.budget} onChange={(e) => setSpot((s) => ({ ...s, budget: e.target.value }))} data-testid="pc-spot-budget" className={inputCls} /></Field>
          <button onClick={buySpot} disabled={spot.busy || !spot.business_id} data-testid="pc-spot-buy"
            className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
            {spot.busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} Fund spotlight
          </button>
        </div>
        <CheckoutResult result={spot.result} onCheck={checkSpot} checking={spot.checking} testid="pc-spot-result" />
      </SectionCard>

      {/* Trivia */}
      <SectionCard icon={Sparkles} title="Trivia Sponsorship" testid="pc-trivia-card"
        desc="Sponsor a trivia round and fund a winner prize pool.">
        <div className="flex flex-wrap gap-2 items-end">
          <Field label="Display name"><input value={triv.display_name} onChange={(e) => setTriv((s) => ({ ...s, display_name: e.target.value }))} data-testid="pc-trivia-name" className={inputCls} /></Field>
          <Field label="Prize (points)"><input type="number" value={triv.points} onChange={(e) => setTriv((s) => ({ ...s, points: e.target.value }))} data-testid="pc-trivia-points" className={inputCls} /></Field>
          <button onClick={buyTriv} disabled={triv.busy} data-testid="pc-trivia-buy"
            className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
            {triv.busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} {env === "live" ? "Book & pay" : "Book"}
          </button>
        </div>
        <CheckoutResult result={triv.result} onCheck={checkTriv} checking={triv.checking} testid="pc-trivia-result" />
      </SectionCard>

      {/* AI-RJ read + voice picker */}
      <SectionCard icon={Radio} title="AI-RJ Sponsored Read" testid="pc-rj-card"
        desc="A host-read audio mention between songs. Pick a voice, preview it, then book.">
        <div>
          <label className="block text-[11px] font-bold text-slate-400 mb-1">Host voice</label>
          <div className="grid sm:grid-cols-3 gap-2" data-testid="pc-rj-personas">
            {(catalog.personas || []).map((p) => (
              <div key={p.id} onClick={() => setRjr((s) => ({ ...s, persona_id: p.id }))} data-testid={`pc-rj-persona-${p.id}`}
                className={`rounded-xl border p-3 cursor-pointer ${rjr.persona_id === p.id ? "border-orange-500 bg-orange-50" : "border-slate-200"}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <button onClick={(ev) => { ev.stopPropagation(); toggleFav(p.id); }} data-testid={`pc-rj-fav-${p.id}`} title="Favourite voice">
                      <Star className={`w-4 h-4 ${favPersona === p.id ? "text-amber-500 fill-amber-500" : "text-slate-300"}`} />
                    </button>
                    <div className="font-black text-sm text-slate-900">{p.name}</div>
                  </div>
                  <button onClick={(ev) => { ev.stopPropagation(); previewVoice(p.id); }} data-testid={`pc-rj-preview-${p.id}`}
                    className="p-1.5 rounded-full bg-slate-900 text-white">
                    {rjr.previewId === p.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{p.tagline || p.personality || "Host voice"}</div>
              </div>
            ))}
            {(catalog.personas || []).length === 0 && <div className="text-sm text-slate-400">No host voices available.</div>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 items-end mt-3">
          <Field label="Product"><input value={rjr.product_name} onChange={(e) => setRjr((s) => ({ ...s, product_name: e.target.value }))} data-testid="pc-rj-product" className={inputCls} /></Field>
          <Field label="Message"><input value={rjr.key_message} onChange={(e) => setRjr((s) => ({ ...s, key_message: e.target.value }))} data-testid="pc-rj-message" className={inputCls} /></Field>
          <Field label="CTA"><input value={rjr.cta} onChange={(e) => setRjr((s) => ({ ...s, cta: e.target.value }))} data-testid="pc-rj-cta" className={inputCls} /></Field>
          <Field label="Plays"><input type="number" value={rjr.plays} onChange={(e) => setRjr((s) => ({ ...s, plays: e.target.value }))} data-testid="pc-rj-plays" className={inputCls} /></Field>
          <Field label="¢/play"><input type="number" value={rjr.cpp} onChange={(e) => setRjr((s) => ({ ...s, cpp: e.target.value }))} data-testid="pc-rj-cpp" className={inputCls} /></Field>
          <button onClick={buyRjr} disabled={rjr.busy || !rjr.persona_id} data-testid="pc-rj-buy"
            className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
            {rjr.busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radio className="w-4 h-4" />} {env === "live" ? "Book & pay" : "Book"}
          </button>
        </div>
        <CheckoutResult result={rjr.result} onCheck={checkRjr} checking={rjr.checking} testid="pc-rj-result" />
      </SectionCard>

      {/* Purchase history */}
      <SectionCard icon={Clock} title="Purchase history" testid="pc-history-card"
        desc="Everything you've bought through the console. Refresh to re-check live status.">
        <div className="flex justify-end mb-2">
          <button onClick={loadHistory} disabled={historyBusy} data-testid="pc-history-refresh"
            className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-700 hover:text-slate-900">
            <RefreshCw className={`w-4 h-4 ${historyBusy ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
        {history.length === 0 ? (
          <div className="text-sm text-slate-400" data-testid="pc-history-empty">No purchases yet.</div>
        ) : (
          <div className="divide-y divide-slate-100" data-testid="pc-history-list">
            {history.map((h) => (
              <div key={`${h.kind}-${h.id}`} className="flex items-center justify-between py-2.5" data-testid={`pc-history-${h.id}`}>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 uppercase">{h.kind}</span>
                    <span className="font-bold text-sm text-slate-900 truncate">{h.name}</span>
                  </div>
                  <div className="text-[11px] text-slate-400 truncate">{h.detail} · {money(h.amount_cents)} · {h.environment || "—"}</div>
                </div>
                <StatusBadge status={h.status} />
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
