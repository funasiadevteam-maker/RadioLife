// Phase 15c — /for-business
//
// Phase Π+3 (2026-07-24) — feature tiles now render the AI-generated
// hero images from `marketing_assets` (keys: live_trivia,
// game_campaigns, coupon_wallet).  Images are fetched via the
// `useMarketingAssets` hook, absolute-URL-resolved against
// `REACT_APP_BACKEND_URL`, and served through the Tigris fallback CDN
// so fresh prod containers can render them without a local disk copy.
// Icons stay as a small badge in the corner so the visual language
// carries over.
import React from "react";
import { Link } from "react-router-dom";
import { Brain, Gamepad2, Wallet, BarChart3, ChevronRight } from "lucide-react";
import MarketingShell, { SEO } from "./MarketingShell";
import { useMarketingAssets } from "@/hooks/useMarketingAssets";

export default function ForBusiness() {
    const { urlFor } = useMarketingAssets();
    return (
        <MarketingShell>
            <SEO title="For Business · Live Trivia, Games & Coupons"
                    description="Host live trivia, run game campaigns, drop coupons into nearby wallets. Real customers, real foot traffic, measured to the minute." />
            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-20 space-y-6"
                          data-testid="forbusiness-hero">
                <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-text-secondary">For business</div>
                <h1 className="font-display font-extrabold text-5xl lg:text-6xl
                                            tracking-display-tight">
                    Bring the <span className="text-accent-electric">neighborhood</span>
                    <br /> through your door.
                </h1>
                <p className="text-text-secondary text-lg max-w-2xl">
                    Host live trivia. Drop coupons into wallets within 1 km of your
                    store. Run branded games during your busiest hour. Measure every
                    step from listen to walk-in.
                </p>
                <Link to="/login" data-testid="forbusiness-cta"
                          className="inline-flex items-center gap-2 px-6 h-12 rounded-full
                                          bg-white text-bg-base font-mono text-xs uppercase
                                          tracking-widest hover:bg-accent-electric
                                          transition-colors duration-150">
                    Open a business account <ChevronRight size={14} />
                </Link>
            </section>

            <Features
                testId="forbusiness-features"
                items={[
                    { icon: Brain,          title: "Live trivia",           imageKey: "live_trivia",
                        body: "Branded quiz night, your venue, your prize pool. We run the room." },
                    { icon: Gamepad2,    title: "Game campaigns",   imageKey: "game_campaigns",
                        body: "Spin-the-wheel, lyric hunts, mystery boxes — yours to brand and time." },
                    { icon: Wallet,          title: "Coupon wallet",      imageKey: "coupon_wallet",
                        body: "Push offers into nearby BigPoints wallets. Redeem with a QR." },
                    { icon: BarChart3,   title: "Live analytics",
                        body: "Listens, plays, walk-ins, redeems — all in one dashboard." },
                ]}
                urlFor={urlFor}
            />

            <DashboardPreview testId="forbusiness-preview" />
        </MarketingShell>
    );
}

/**
 * Feature cards used by /for-business AND /for-advertisers.
 *
 * Props:
 *    items[] : { icon, title, body, imageKey? }
 *    urlFor  : (key) => absolute HTTPS URL from useMarketingAssets(), OR undefined
 *
 * When `imageKey` is present AND `urlFor(imageKey)` resolves to a URL,
 * the card renders that image as a subtle background with a gradient
 * scrim so the copy stays legible.  Otherwise it falls back to the
 * legacy icon-only card.
 */
export function Features({ items, testId, urlFor }) {
    const resolve = urlFor || (() => "");
    return (
        <section data-testid={testId}
                      className="max-w-6xl mx-auto px-6 lg:px-10 py-12
                                          border-t border-white/[0.06]">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                {items.map(({ icon: Icon, title, body, imageKey }) => {
                    const imgUrl = imageKey ? resolve(imageKey) : "";
                    return (
                        <div key={title}
                                  data-testid={`feature-card-${(imageKey || title)
                                                          .toLowerCase().replace(/\s+/g, "-")}`}
                                  className="relative overflow-hidden rounded-token-card
                                                  border border-white/[0.06] bg-bg-elevated
                                                  min-h-[240px] flex flex-col justify-end">
                            {imgUrl ? (
                                <>
                                    <img
                                        src={imgUrl}
                                        alt={title}
                                        loading="lazy"
                                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                                        className="absolute inset-0 w-full h-full object-cover
                                                          opacity-90"
                                        data-testid={`feature-card-img-${imageKey}`} />
                                    <div className="absolute inset-0
                                                                    bg-gradient-to-t
                                                                    from-bg-elevated via-bg-elevated/70
                                                                    to-bg-elevated/10" />
                                </>
                            ) : null}
                            <div className="relative p-6">
                                <div className="w-10 h-10 rounded-token-md grid place-items-center
                                                        bg-accent-electric/25 text-accent-electric
                                                        backdrop-blur-sm">
                                    <Icon size={18} />
                                </div>
                                <div className="mt-4 font-display font-bold text-lg
                                                        tracking-display-tight">{title}</div>
                                <div className="mt-1 text-sm text-text-secondary">{body}</div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </section>
    );
}

export function DashboardPreview({ testId, label = "Business dashboard preview" }) {
    return (
        <section data-testid={testId}
                      className="max-w-6xl mx-auto px-6 lg:px-10 py-12
                                          border-t border-white/[0.06]">
            <div className="relative h-80 rounded-token-card overflow-hidden
                                        border border-white/[0.06] bg-bg-elevated"
                        data-placeholder="true">
                <div className="absolute inset-0"
                            style={{
                                background: "radial-gradient(ellipse at 20% 30%, rgba(0,212,255,0.22), transparent 55%)," +
                                                        "radial-gradient(ellipse at 80% 70%, rgba(255,180,0,0.22), transparent 55%)",
                            }} />
                <div className="absolute inset-x-10 bottom-8 text-xs font-mono
                                            text-text-secondary uppercase tracking-widest">
                    {label} · coming soon
                </div>
            </div>
        </section>
    );
}
