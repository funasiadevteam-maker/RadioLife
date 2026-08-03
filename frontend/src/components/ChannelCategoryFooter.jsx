/**
 * Phase 41 Session 1.8 — Category-grouped channel discovery footer.
 *
 * Renders at the bottom of every "framed" listener route (Home, Radio,
 * Community, News, Wallet, Passport, Commute, Places). Mounted from
 * AppShell's main scroll area so it appears as the natural bottom of
 * the scrolled page, NOT a separate fixed footer.
 *
 * Self-gating via location: skips auth funnel, admin, advertiser,
 * checkout, billing, privacy, /r/{slug}, /radio/create — exactly the
 * same EXCLUDE set as PageFrame.jsx, plus a couple of marketing routes.
 *
 * Fetches ONCE per browser session and stores the response in a
 * module-level memo. After 5 min the next mount triggers a re-fetch.
 * Skeleton placeholder during the first fetch reserves height to avoid
 * layout shift.
 */
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { API } from "@/AuthContext";

// Same skip list as PageFrame.jsx — keep in sync.
const EXCLUDE = [
  /^\/login/, /^\/signup/, /^\/onboarding/, /^\/auth(\b|\/)/,
  /^\/admin/, /^\/advertiser/,
  /^\/checkout/, /^\/billing/, /^\/privacy/,
  /^\/r\//,                  // station detail keeps its own surface
  /^\/radio\/create/,
  /^\/dev\/styleguide/,
  /^\/about/, /^\/for-business/, /^\/for-advertisers/,
  /^\/pricing/, /^\/legal/,
];

// Module-scope session cache. 5 min TTL.
const SESSION_CACHE = { value: null, expires_at: 0 };
const CACHE_TTL_MS = 5 * 60 * 1000;

function deepLinkFor(ch) {
  if (ch.type === "community") return `/r/${ch.slug}`;
  return `/radio?channel=${encodeURIComponent(ch.slug)}`;
}

function CategoryColumn({ category }) {
  return (
    <div
      data-testid={`channel-footer-category-${category.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")}`}
      className="min-w-0"
    >
      <h4 className="text-text-primary text-sm font-semibold uppercase
                     tracking-wide mb-3 pb-2 border-b border-white/[0.08]">
        {category.name}
        <span className="ml-2 text-text-secondary text-xs font-normal
                         normal-case tracking-normal">
          {category.channels.length}
        </span>
      </h4>
      <ul className="space-y-1.5">
        {category.channels.map((ch) => (
          <li key={`${ch.type}:${ch.slug}`}>
            <Link
              to={deepLinkFor(ch)}
              data-testid={`channel-footer-link-${ch.slug}`}
              className="text-text-secondary hover:text-accent-electric
                         text-[13px] leading-snug transition-colors
                         duration-150 inline-flex items-center gap-1.5"
            >
              {ch.name}
              {ch.type === "community" && (
                <span
                  data-testid="channel-footer-badge-community"
                  className="text-[10px] uppercase tracking-wide
                             text-accent-electric/80 bg-accent-electric/10
                             px-1.5 py-[1px] rounded"
                >
                  community
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MobileAccordion({ categories }) {
  return (
    <div className="md:hidden">
      {categories.map((c, idx) => (
        <details
          key={c.name}
          data-testid={`channel-footer-accordion-${c.name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")}`}
          className={`border-b border-white/[0.06] ${
            idx === 0 ? "border-t" : ""
          }`}
        >
          <summary
            className="py-3 px-1 cursor-pointer list-none flex items-center
                       justify-between text-text-primary text-sm font-semibold
                       uppercase tracking-wide"
          >
            <span>
              {c.name}
              <span className="ml-2 text-text-secondary text-xs font-normal
                               normal-case tracking-normal">
                {c.channels.length}
              </span>
            </span>
            <span className="text-text-secondary text-base leading-none">
              <span className="block group-open:hidden">+</span>
            </span>
          </summary>
          <ul className="pb-3 pl-1 space-y-2">
            {c.channels.map((ch) => (
              <li key={`${ch.type}:${ch.slug}`}>
                <Link
                  to={deepLinkFor(ch)}
                  data-testid={`channel-footer-link-mobile-${ch.slug}`}
                  className="text-text-secondary hover:text-accent-electric
                             text-sm leading-snug inline-flex items-center
                             gap-1.5"
                >
                  {ch.name}
                  {ch.type === "community" && (
                    <span className="text-[10px] uppercase tracking-wide
                                     text-accent-electric/80
                                     bg-accent-electric/10 px-1.5 py-[1px]
                                     rounded">
                      community
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

function Skeleton() {
  return (
    <div
      data-testid="channel-footer-skeleton"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8"
    >
      {[0, 1, 2, 3].map((i) => (
        <div key={i}>
          <div className="h-3 w-24 bg-white/[0.06] rounded mb-4" />
          <div className="space-y-2">
            <div className="h-3 w-32 bg-white/[0.04] rounded" />
            <div className="h-3 w-28 bg-white/[0.04] rounded" />
            <div className="h-3 w-36 bg-white/[0.04] rounded" />
            <div className="h-3 w-24 bg-white/[0.04] rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ChannelCategoryFooter() {
  const { pathname } = useLocation();
  const excluded = useMemo(
    () => EXCLUDE.some((rx) => rx.test(pathname)),
    [pathname]
  );

  // Lazy initializer — when the session cache is warm, the very first
  // render is already in the resolved state (no skeleton flash, no
  // sync setState inside useEffect).
  const [state, setState] = useState(() => {
    if (SESSION_CACHE.value && SESSION_CACHE.expires_at > Date.now()) {
      return {
        categories: SESSION_CACHE.value.categories || [],
        loading: false,
        error: null,
      };
    }
    return { categories: null, loading: true, error: null };
  });

  useEffect(() => {
    if (excluded) return undefined;
    // Cache hit — state was initialized warm via the lazy initializer
    // above; effect doesn't need to touch state at all.
    if (SESSION_CACHE.value && SESSION_CACHE.expires_at > Date.now()) {
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/channels/by_category`);
        if (cancelled) return;
        SESSION_CACHE.value = r.data;
        SESSION_CACHE.expires_at = Date.now() + CACHE_TTL_MS;
        setState({
          categories: r.data.categories || [],
          loading: false,
          error: null,
        });
      } catch (e) {
        if (cancelled) return;
        setState((s) => ({ ...s, loading: false, error: e }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [excluded]);

  const { categories, loading, error } = state;

  if (excluded) return null;

  // Hide entirely on error or empty payload — don't leave a dead block.
  if (!loading && (error || !categories || categories.length === 0)) {
    return null;
  }

  return (
    <section
      data-testid="channel-category-footer"
      className="mt-12 pt-8 pb-10 border-t border-white/[0.06]"
      aria-label="Browse all radio channels by category"
    >
      <div className="mb-5 flex items-end justify-between gap-3">
        <div>
          <h3 className="text-text-primary text-base font-semibold
                         tracking-tight">
            Browse all radio channels
          </h3>
          <p className="text-text-secondary text-xs mt-1">
            Hand-curated by BigFM &amp; community-built stations, grouped
            by genre.
          </p>
        </div>
        {/* Phase 41 S1.8 stretch — discovery CTA to nudge listeners
            into the create-radio wizard at the bottom-of-page intent
            moment. ~10 lines, no API impact. */}
        <Link
          to="/radio/create"
          data-testid="channel-footer-create-cta"
          className="shrink-0 inline-flex items-center gap-1.5 text-xs
                     font-medium text-accent-electric border
                     border-accent-electric/40 hover:border-accent-electric
                     hover:bg-accent-electric/10 rounded-full
                     px-3 py-1.5 transition-colors duration-150
                     whitespace-nowrap"
        >
          <span aria-hidden>🎙</span>
          Create my radio
          <span aria-hidden>→</span>
        </Link>
      </div>

      {loading ? (
        <Skeleton />
      ) : (
        <>
          {/* Desktop / tablet: multi-column grid. */}
          <div
            data-testid="channel-footer-grid"
            className="hidden md:grid grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-8"
          >
            {categories.map((c) => (
              <CategoryColumn key={c.name} category={c} />
            ))}
          </div>

          {/* Mobile: accordion. */}
          <MobileAccordion categories={categories} />
        </>
      )}
    </section>
  );
}
