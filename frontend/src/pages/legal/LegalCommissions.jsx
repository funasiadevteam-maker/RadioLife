// Phase SC.3 — Public commission-schedule page.  No auth required.
// Renders in both design variants.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Sparkles, ArrowLeft } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const CATEGORY_LABELS = {
  restaurant: "Restaurants",              cafe: "Cafés",
  grocery:      "Grocery",                      retail: "Retail",
  salon_spa:  "Salons & Spas",          medical_dental: "Medical & Dental",
  fitness:      "Fitness",                      entertainment: "Entertainment",
  movie_theater: "Movie Theaters", event_promoter: "Event Promoters",
  concert_promoter: "Concert Promoters", club_lounge: "Clubs & Lounges",
  radio_station: "Radio Stations", podcast_creator: "Podcast Creators",
  service_business: "Service Businesses", other: "Other",
};


export default function LegalCommissions() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    axios.get(`${API}/commissions/rates`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || e.message));
  }, []);

  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
                          : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="legal-commissions-page"
              data-variant={variant}>
      <div className="max-w-4xl mx-auto px-5 py-10">
        <Link to="/"
                  className={`inline-flex items-center gap-1.5 text-sm font-medium mb-8 ${
                    light ? "text-purple-700 hover:text-purple-900"
                              : "text-slate-400 hover:text-cyan-400"
                  }`}
                  data-testid="legal-commissions-back">
          <ArrowLeft size={16}/> Back to BigFM
        </Link>

        <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
          light ? "text-purple-600" : "text-cyan-400"
        }`}>Phase SC.3 · Public schedule</div>
        <h1 className={`text-4xl sm:text-5xl font-black tracking-tight mb-2 ${
          light ? "text-slate-900" : "text-white"
        }`}>Platform Commission Schedule</h1>
        <p className={light ? "text-slate-600 text-sm" : "text-slate-400 text-sm"}
              data-testid="legal-commissions-last-updated">
          Last updated: {data?.last_updated
                                            ? new Date(data.last_updated).toLocaleDateString(undefined, {
                                                    year: "numeric", month: "long", day: "numeric" })
                                            : "…"}
        </p>

        {err && (
          <div className={`mt-6 p-4 rounded-2xl ${
            light ? "bg-rose-50 border border-rose-200 text-rose-800"
                    : "bg-rose-500/10 border border-rose-500/30 text-rose-300"
          }`}>
            Failed to load: {String(err)}
          </div>
        )}

        {!data && !err && (
          <div className={`mt-6 text-sm ${light ? "text-slate-500" : "text-slate-500"}`}>
            Loading rates…
          </div>
        )}

        {data && (
          <>
            <div className="mt-8 space-y-4"
                      data-testid="legal-commissions-categories">
              {Object.entries(data.categories || {})
                .sort((a, b) =>
                  (CATEGORY_LABELS[a[0]] || a[0]).localeCompare(
                    CATEGORY_LABELS[b[0]] || b[0]))
                .map(([cat, rules]) => (
                <CategoryCard key={cat} light={light}
                                          category={cat}
                                          label={CATEGORY_LABELS[cat] || cat}
                                          rules={rules} />
              ))}
            </div>

            {data.fallback && (
              <div className={`mt-6 rounded-2xl p-5 ${
                light ? "bg-amber-50 border border-amber-200"
                        : "bg-amber-500/10 border border-amber-500/30"
              }`} data-testid="legal-commissions-fallback">
                <div className={`text-xs font-bold uppercase tracking-widest mb-1 ${
                  light ? "text-amber-700" : "text-amber-300"
                }`}>Everything else</div>
                <div className={light ? "text-slate-800 text-sm" : "text-slate-200 text-sm"}>
                  <b>{data.fallback.commission_percent.toFixed(2)}%</b> —
                  applies when no category-specific rule matches.
                </div>
              </div>
            )}

            <div className={`mt-10 rounded-2xl p-5 text-sm ${
              light ? "bg-purple-50 border border-purple-100 text-slate-700"
                      : "bg-slate-900 border border-slate-800 text-slate-300"
            }`}>
              <div className="flex items-start gap-2">
                <Sparkles size={16} className={light ? "text-purple-600 mt-0.5" : "text-cyan-400 mt-0.5"}/>
                <div>
                  Merchant-specific overrides may apply.  Enterprise pricing
                  and volume discounts are available — contact{" "}
                  <a href="mailto:partners@bigfm.dubai"
                        className={light ? "underline text-purple-700" : "underline text-cyan-400"}>
                    partners@bigfm.dubai
                  </a>{" "}for a custom deal.
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


function CategoryCard({ light, category, label, rules }) {
  return (
    <div className={`rounded-3xl overflow-hidden ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"
    }`} data-testid={`legal-commissions-category-${category}`}>
      <div className={`px-5 py-4 ${
        light ? "border-b border-slate-100" : "border-b border-slate-800"
      }`}>
        <h2 className={`text-xl font-extrabold tracking-tight ${
          light ? "text-slate-900" : "text-white"
        }`}>{label}</h2>
      </div>
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {rules.map((r) => (
          <div key={r.rule_id}
                    className="flex flex-wrap items-baseline gap-2 px-5 py-3.5"
                    data-testid={`legal-commissions-rule-${r.rule_id}`}>
            <div className={`flex-1 min-w-0 ${light ? "text-slate-800" : "text-slate-200"}`}>
              <div className="font-semibold text-sm">
                {(r.transaction_type || "").replace(/_/g, " ")}
              </div>
              {r.notes && (
                <div className={`text-xs mt-0.5 ${light ? "text-slate-500" : "text-slate-500"}`}>
                  {r.notes}
                </div>
              )}
            </div>
            <div className={`text-2xl font-black tabular-nums ${
              light ? "text-purple-700" : "text-cyan-400"
            }`}>
              {r.commission_percent.toFixed(1)}%
            </div>
            {r.fixed_fee_cents > 0 && (
              <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
                + {r.fixed_fee_cents}¢ fixed
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
