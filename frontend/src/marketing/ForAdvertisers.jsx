// Phase 15c — /for-advertisers
//
// Phase Π+3 (2026-07-24) — feature tiles now render the AI-generated
// hero images from `marketing_assets` (keys: audio_ads,
// sponsored_games, route_based_ads).  Icons remain as a corner badge.
import React from "react";
import { Link } from "react-router-dom";
import { Radio, Gamepad2, MapPin, BarChart3, ChevronRight } from "lucide-react";
import MarketingShell, { SEO } from "./MarketingShell";
import { Features, DashboardPreview } from "./ForBusiness";
import { useMarketingAssets } from "@/hooks/useMarketingAssets";

export default function ForAdvertisers() {
    const { urlFor } = useMarketingAssets();
    return (
        <MarketingShell>
            <SEO title="For Advertisers · AI-narrated audio + route-based offers"
                    description="Audio ads voiced by the AI host, sponsored games during your daypart, and route-based offers that turn listeners into walk-ins." />
            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-20 space-y-6"
                          data-testid="foradvertisers-hero">
                <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-text-secondary">For advertisers</div>
                <h1 className="font-display font-extrabold text-5xl lg:text-6xl
                                            tracking-display-tight">
                    Audio that <span className="text-accent-magenta">buys back</span>
                    <br /> its own airtime.
                </h1>
                <p className="text-text-secondary text-lg max-w-2xl">
                    The AI host reads your spot, in character, in the gap before
                    your music. Sponsor a game during your daypart. Hit listeners
                    on their drive home, within a kilometer of your store.
                </p>
                <Link to="/login" data-testid="foradvertisers-cta"
                          className="inline-flex items-center gap-2 px-6 h-12 rounded-full
                                          bg-white text-bg-base font-mono text-xs uppercase
                                          tracking-widest hover:bg-accent-magenta
                                          hover:text-white transition-colors duration-150">
                    Become an advertiser <ChevronRight size={14} />
                </Link>
            </section>

            <Features
                testId="foradvertisers-features"
                items={[
                    { icon: Radio,      title: "Audio ads",                  imageKey: "audio_ads",
                        body: "AI host reads your script, in-voice, in the gap before the song." },
                    { icon: Gamepad2,  title: "Sponsored games",       imageKey: "sponsored_games",
                        body: "Branded games unlock during your daypart. Track plays + redeems." },
                    { icon: MapPin,      title: "Route-based offers",  imageKey: "route_based_ads",
                        body: "Hit listeners commuting near your store. Geofence + daypart targeted." },
                    { icon: BarChart3, title: "Live reporting",          imageKey: "live_reporting",
                        body: "Impressions, engagements, redeems, walk-ins — measured end-to-end." },
                ]}
                urlFor={urlFor}
            />

            <DashboardPreview testId="foradvertisers-preview"
                                                label="Advertiser dashboard preview" />
        </MarketingShell>
    );
}
