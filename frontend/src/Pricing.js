// /pricing — BigFM Premium upgrade page. Free vs Premium comparison, currency
// auto-detected with `?currency=` override, test-mode banner when applicable.
//
// The pricing page is intentionally aspirational: gold accent on premium card,
// confident copy, "BILLED ANNUALLY" callout. CSS lives in pricing.css.

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, Check, Crown, Lock, Loader2, ShieldCheck, Sparkles, X, Zap,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API, useAuth } from "@/AuthContext";
import BigFmBrand from "@/components/BigFmBrand";
import "@/pricing.css";

const SUPPORTED_CURRENCIES = [
  { code: "USD", label: "USD · $" },
  { code: "AED", label: "AED · د.إ" },
  { code: "INR", label: "INR · ₹" },
];

// Frozen free-tier features (no API surface for these in Phase 3).
const FREE_FEATURES = [
  { copy: "6 skips per hour", premium: false },
  { copy: "8 standard channels", premium: false },
  { copy: "Solo + Duo AI RJs", premium: false },
  { copy: "Share-the-break links", premium: false },
];
const PREMIUM_HEADLINE_FEATURES = [
  { icon: Zap,         copy: "Unlimited skips" },
  { icon: Crown,       copy: "2 exclusive VIP channels" },
  { icon: ShieldCheck, copy: "Ad-free listening" },
  { icon: Sparkles,    copy: "VIP badge on your profile" },
];

export default function Pricing() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [redirecting, setRedirecting] = useState(false);
  const [currency, setCurrency] = useState(params.get("currency") || null);

  const isPremium = !!user?.is_premium;
  const cancelled = params.get("cancelled") === "1";

  const fetchConfig = async (cur) => {
    setLoading(true);
    try {
      const q = cur ? `?currency=${cur}` : "";
      const r = await axios.get(`${API}/billing/config${q}`);
      setConfig(r.data);
      setCurrency(r.data.currency);
    } catch (e) {
      toast.error("Could not load pricing");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig(params.get("currency"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (cancelled) toast.info("Checkout cancelled. Try again whenever.");
  }, [cancelled]);

  const onCurrencyChange = (c) => {
    setCurrency(c);
    setParams({ currency: c });
    fetchConfig(c);
  };

  const premiumPlan = useMemo(
    () => config?.plans?.find((p) => p.plan_id === "premium_annual"),
    [config],
  );

  const onCheckout = async () => {
    if (!user) {
      toast.info("Sign in first to upgrade");
      navigate("/login?next=/pricing");
      return;
    }
    if (isPremium) {
      toast.success("You're already Premium!");
      return;
    }
    setRedirecting(true);
    try {
      const r = await axios.post(`${API}/billing/checkout`, {
        plan_id: "premium_annual",
        currency: currency || "USD",
        origin_url: window.location.origin,
      });
      // Hand off to Stripe-hosted checkout page
      window.location.href = r.data.url;
    } catch (e) {
      setRedirecting(false);
      toast.error(e?.response?.data?.detail || "Could not start checkout");
    }
  };

  return (
    <div className="pricing-shell" data-testid="pricing-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="pricing-head">
        <Link to="/" className="back-link mono" data-testid="pricing-back-link">
          <ArrowLeft size={14} /> BACK TO RADIO
        </Link>
        <div className="auth-brand">
          <span className="brand-dot" />
          <BigFmBrand variant="inline" testId="pricing-brand" />
        </div>
        <div className="currency-picker" data-testid="currency-picker">
          {SUPPORTED_CURRENCIES.map((c) => (
            <button
              key={c.code}
              type="button"
              className={`cur-btn mono ${currency === c.code ? "is-on" : ""}`}
              onClick={() => onCurrencyChange(c.code)}
              data-testid={`currency-btn-${c.code}`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </header>

      {config?.test_banner && (
        <div className="test-banner mono" data-testid="test-banner">
          <Sparkles size={12} /> {config.test_banner}
        </div>
      )}

      <section className="pricing-hero">
        <div className="hero-eyebrow mono">PHASE 3 · BIGFM PREMIUM</div>
        <h1 className="hero-h1">
          Skip without limits.<br/>
          <span className="hero-accent">Mehfil, on gold standard.</span>
        </h1>
        <p className="hero-sub">
          One annual pass. Two VIP channels you can't get on free. Every skip on the house.
        </p>
      </section>

      {loading || !premiumPlan ? (
        <div className="pricing-loading"><Loader2 className="spin" size={32} /></div>
      ) : (
        <section className="plan-grid" data-testid="plan-grid">
          {/* FREE column */}
          <div className="plan-card plan-free" data-testid="plan-card-free">
            <div className="plan-tier mono">FREE</div>
            <div className="plan-price">
              <div className="amount">{currency === "INR" ? "₹0" : currency === "AED" ? "AED 0" : "$0"}</div>
              <div className="cadence mono">FOREVER</div>
            </div>
            <p className="plan-desc">All the music. Some friction. Hinglish hooks all day.</p>
            <ul className="plan-list">
              {FREE_FEATURES.map((f) => (
                <li key={f.copy}>
                  <Check size={14} /> <span>{f.copy}</span>
                </li>
              ))}
              <li className="plan-missing">
                <X size={14} /> <span>Skip cap (6/hour)</span>
              </li>
              <li className="plan-missing">
                <X size={14} /> <span>VIP channels locked</span>
              </li>
              <li className="plan-missing">
                <X size={14} /> <span>No VIP badge</span>
              </li>
            </ul>
            <button
              type="button"
              className="plan-cta plan-cta-free"
              onClick={() => navigate("/")}
              data-testid="plan-cta-free"
            >
              CONTINUE FREE
            </button>
          </div>

          {/* PREMIUM column */}
          <div className="plan-card plan-premium" data-testid="plan-card-premium">
            <div className="plan-tier-banner mono">
              <Crown size={12} /> PREMIUM · BILLED ANNUALLY
            </div>
            <div className="plan-price">
              <div className="amount" data-testid="plan-price-amount">
                {premiumPlan.amount_display}
              </div>
              <div className="cadence mono">/YEAR · {premiumPlan.currency}</div>
            </div>
            <p className="plan-desc">{premiumPlan.description}</p>
            <ul className="plan-list">
              {premiumPlan.features.map((f) => (
                <li key={f}>
                  <Check size={14} /> <span>{f}</span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className={`plan-cta plan-cta-premium ${redirecting ? "is-loading" : ""}`}
              onClick={onCheckout}
              disabled={redirecting || isPremium}
              data-testid="plan-cta-premium"
            >
              {redirecting
                ? <><Loader2 className="spin" size={16} /> REDIRECTING TO CHECKOUT…</>
                : isPremium
                  ? <><Crown size={16} /> YOU'RE PREMIUM</>
                  : <><Crown size={16} /> GO PREMIUM · {premiumPlan.amount_display}</>}
            </button>
            <div className="plan-fine-print mono">
              No auto-renew · Cancel anytime · Test mode in Phase 3
            </div>
          </div>
        </section>
      )}

      <section className="pricing-headlines" data-testid="pricing-headlines">
        <div className="headlines-eyebrow mono">WHAT YOU UNLOCK</div>
        <div className="headlines-grid">
          {PREMIUM_HEADLINE_FEATURES.map((f) => (
            <div key={f.copy} className="headline-tile">
              <f.icon size={20} />
              <span>{f.copy}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="pricing-faq" data-testid="pricing-faq">
        <h2>Frequently asked</h2>
        <dl>
          <dt>Can I cancel anytime?</dt>
          <dd>Yes. You keep Premium until the period ends. No partial refunds.</dd>
          <dt>What's a VIP channel?</dt>
          <dd>VIP Lounge (mellow, late-night) and Premium Mehfil (deep Bollywood cuts) — only premium can tune in.</dd>
          <dt>Does premium remove ads?</dt>
          <dd>Yes, the ad-free flag is set on your account. (Phase 4 adds the actual ad inventory.)</dd>
          <dt>Is this billing in test mode?</dt>
          <dd>{config?.mode === "test" ? "Yes — no real cards will be charged during Phase 3 testing." : "We are live. Real charges apply."}</dd>
        </dl>
      </section>

      <footer className="pricing-foot">
        <span>BIGFM · PHASE 3 · BILLING</span>
        <span>Stripe-secured · {config?.mode?.toUpperCase()} MODE</span>
      </footer>
    </div>
  );
}
